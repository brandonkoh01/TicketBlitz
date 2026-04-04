import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple

import stripe
from flask import Flask, jsonify, request
from flask_cors import CORS
from postgrest.exceptions import APIError as PostgrestAPIError

from shared.db import db_configured, get_db
from shared.mq import publish_json, rabbitmq_configured

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

POLICY_WINDOW_HOURS = 48
MAX_REFUND_ATTEMPTS = 3
REFUND_SUCCESS_RATIO = Decimal("0.90")
REFUND_PENDING_STALE_SECONDS = int(
    os.getenv("REFUND_PENDING_STALE_SECONDS", "300"))
WEBHOOK_RECEIVED_STALE_SECONDS = int(
    os.getenv("WEBHOOK_RECEIVED_STALE_SECONDS", "120"))
INTERNAL_AUTH_HEADER = "X-Internal-Token"
PAYMENT_IDEMPOTENCY_PREFIX = "payment-initiate"


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ValidationError(ApiError):
    def __init__(self, message: str):
        super().__init__(message, 400)


class NotFoundError(ApiError):
    def __init__(self, message: str):
        super().__init__(message, 404)


class ConflictError(ApiError):
    def __init__(self, message: str):
        super().__init__(message, 409)


class DependencyError(ApiError):
    def __init__(self, message: str):
        super().__init__(message, 503)


class ExternalServiceError(ApiError):
    def __init__(self, message: str):
        super().__init__(message, 502)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utcnow().isoformat()


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None
    return None


def _clean_currency(value: Any) -> str:
    currency = str(value or "SGD").strip().upper()
    if len(currency) != 3:
        raise ValidationError("currency must be a three-letter ISO code")
    return currency


def _as_uuid(value: Any, field_name: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except Exception as error:
        raise ValidationError(f"{field_name} must be a valid UUID") from error


def _as_decimal(value: Any, field_name: str) -> Decimal:
    try:
        decimal_value = Decimal(str(value)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, TypeError) as error:
        raise ValidationError(
            f"{field_name} must be a numeric value") from error

    if decimal_value <= 0:
        raise ValidationError(f"{field_name} must be greater than 0")
    return decimal_value


def _to_minor_units(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _as_minor_units(value: Any, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{field_name} must be an integer") from error

    if parsed < 0:
        raise ValidationError(f"{field_name} must be greater than or equal to 0")

    return parsed


def _validate_payment_intent_amount_and_currency(
    payment_intent: Dict[str, Any], transaction: Dict[str, Any]
) -> None:
    expected_amount = _to_minor_units(_as_decimal(transaction.get("amount"), "transaction amount"))
    received_amount = _as_minor_units(
        payment_intent.get("amount_received"), "payment_intent.amount_received"
    )
    if received_amount != expected_amount:
        raise ConflictError("payment_intent amount does not match transaction amount")

    expected_currency = _clean_currency(transaction.get("currency"))
    received_currency = _clean_currency(payment_intent.get("currency"))
    if received_currency != expected_currency:
        raise ConflictError("payment_intent currency does not match transaction currency")


def _decimal_to_str(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _stripe_object_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    return dict(value)


def _get_json_payload() -> Dict[str, Any]:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValidationError("JSON body must be an object")
    return payload


def _require_supabase() -> None:
    if not db_configured():
        raise DependencyError("Supabase is not configured")


def _require_stripe() -> None:
    if not os.getenv("STRIPE_SECRET_KEY"):
        raise DependencyError("Stripe is not configured")


def _require_internal_auth() -> None:
    token = os.getenv("PAYMENT_INTERNAL_TOKEN")
    if not token:
        return

    if request.headers.get(INTERNAL_AUTH_HEADER) != token:
        raise ApiError("Unauthorized", 401)


def _extract_postgrest_error_code(error: Exception) -> Optional[str]:
    if isinstance(error, PostgrestAPIError) and error.args:
        payload = error.args[0]
        if isinstance(payload, dict):
            code = payload.get("code")
            return str(code) if code is not None else None
    return None


def _is_duplicate_webhook_event_error(error: Exception) -> bool:
    if _extract_postgrest_error_code(error) == "23505":
        return True

    message = str(error).lower()
    return (
        ("duplicate key" in message or "unique constraint" in message)
        and "payment_webhook_events" in message
        and "webhook_event_id" in message
    )


def _is_recent_timestamp(value: Any, threshold_seconds: int) -> bool:
    parsed = _parse_datetime(value)
    if not parsed:
        return False
    elapsed = (_utcnow() - parsed).total_seconds()
    return elapsed <= threshold_seconds


def _safe_db_select_one(table: str, filters: Dict[str, Any], columns: str = "*") -> Optional[Dict[str, Any]]:
    query = get_db().table(table).select(columns)
    for key, value in filters.items():
        query = query.eq(key, value)
    response = query.limit(1).execute()
    rows = response.data or []
    return rows[0] if rows else None


def _safe_db_select_many(
    table: str,
    filters: Dict[str, Any],
    columns: str = "*",
    order_by: Optional[str] = None,
    desc: bool = False,
    limit: Optional[int] = None,
) -> list[Dict[str, Any]]:
    query = get_db().table(table).select(columns)
    for key, value in filters.items():
        query = query.eq(key, value)
    if order_by:
        query = query.order(order_by, desc=desc)
    if limit is not None:
        query = query.limit(limit)
    response = query.execute()
    return response.data or []


def _fetch_hold(hold_id: str) -> Dict[str, Any]:
    hold = _safe_db_select_one(
        "seat_holds",
        {"hold_id": hold_id},
        (
            "hold_id,seat_id,event_id,category_id,user_id,hold_expires_at,status,"
            "amount,currency,correlation_id,from_waitlist"
        ),
    )
    if not hold:
        raise NotFoundError("Seat hold not found")
    return hold


def _fetch_user_email(user_id: str) -> str:
    user = _safe_db_select_one("users", {"user_id": user_id}, "user_id,email")
    if not user:
        raise NotFoundError("User not found")
    email = str(user.get("email") or "").strip()
    if not email:
        raise ValidationError("User email is missing")
    return email


def _resolve_waitlist_id_for_hold(hold_id: str) -> Optional[str]:
    rows = _safe_db_select_many(
        "waitlist_entries",
        {"hold_id": hold_id},
        "waitlist_id,status,hold_id,updated_at",
        order_by="updated_at",
        desc=True,
        limit=1,
    )
    if not rows:
        return None

    row = rows[0]

    waitlist_id = row.get("waitlist_id")
    if not waitlist_id:
        return None

    return str(waitlist_id)


def _fetch_transaction_by_intent(payment_intent_id: str) -> Optional[Dict[str, Any]]:
    return _safe_db_select_one(
        "transactions",
        {"stripe_payment_intent_id": payment_intent_id},
        (
            "transaction_id,hold_id,event_id,user_id,amount,currency,status,"
            "failure_reason,refund_amount,refund_status,stripe_payment_intent_id,"
            "stripe_charge_id,correlation_id,provider_response,created_at,updated_at"
        ),
    )


def _fetch_latest_transaction_for_hold(hold_id: str) -> Optional[Dict[str, Any]]:
    transactions = _safe_db_select_many(
        "transactions",
        {"hold_id": hold_id},
        (
            "transaction_id,hold_id,event_id,user_id,amount,currency,status,"
            "failure_reason,refund_amount,refund_status,stripe_payment_intent_id,"
            "stripe_charge_id,correlation_id,provider_response,created_at,updated_at"
        ),
        order_by="created_at",
        desc=True,
        limit=1,
    )
    return transactions[0] if transactions else None


def _fetch_transaction_by_transaction_id(transaction_id: str) -> Optional[Dict[str, Any]]:
    return _safe_db_select_one(
        "transactions",
        {"transaction_id": transaction_id},
        (
            "transaction_id,hold_id,event_id,user_id,amount,currency,status,"
            "failure_reason,refund_amount,refund_status,stripe_payment_intent_id,"
            "stripe_charge_id,correlation_id,provider_response,created_at,updated_at"
        ),
    )


def _resolve_booking_transaction(booking_id: str) -> Tuple[Dict[str, Any], str]:
    parsed_id = _as_uuid(booking_id, "bookingID")
    transaction = _fetch_transaction_by_transaction_id(parsed_id)
    if transaction:
        return transaction, "transaction_id"

    transaction = _fetch_latest_transaction_for_hold(parsed_id)
    if transaction:
        return transaction, "hold_id"

    raise NotFoundError("Booking transaction not found")


def _fetch_event(event_id: str) -> Dict[str, Any]:
    event = _safe_db_select_one(
        "events", {"event_id": event_id}, "event_id,event_date")
    if not event:
        raise NotFoundError("Event not found")
    return event


def _compute_policy(transaction: Dict[str, Any]) -> Dict[str, Any]:
    event = _fetch_event(transaction["event_id"])
    event_date = _parse_datetime(event.get("event_date"))
    if not event_date:
        raise ValidationError("Event date is invalid")

    purchase_date = _parse_datetime(transaction.get("created_at"))
    if not purchase_date:
        purchase_date = _utcnow()

    cutoff = event_date - timedelta(hours=POLICY_WINDOW_HOURS)
    now = _utcnow()
    within_policy = now <= cutoff
    base_amount = _as_decimal(transaction["amount"], "transaction amount")
    eligible_refund_amount = (base_amount * REFUND_SUCCESS_RATIO).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return {
        "eventDate": event_date.isoformat(),
        "purchaseDate": purchase_date.isoformat(),
        "policyCutoffAt": cutoff.isoformat(),
        "withinPolicy": within_policy,
        "eligibleRefundAmount": _decimal_to_str(eligible_refund_amount),
        "feePercentage": "10.00",
    }


def _create_cancellation_or_update(
    transaction: Dict[str, Any],
    status: str,
    policy_context: Dict[str, Any],
    reason: Optional[str] = None,
    attempt_increment: int = 0,
) -> Dict[str, Any]:
    existing_rows = _safe_db_select_many(
        "cancellation_requests",
        {"hold_id": transaction["hold_id"]},
        (
            "cancellation_request_id,hold_id,transaction_id,event_id,user_id,status,"
            "attempt_count,last_attempt_at,resolved_at"
        ),
        order_by="requested_at",
        desc=True,
        limit=1,
    )
    now_iso = _iso_now()
    refund_amount = _decimal_to_str(_as_decimal(
        policy_context["eligibleRefundAmount"], "refund amount"))
    payload = {
        "status": status,
        "policy_cutoff_at": policy_context["policyCutoffAt"],
        "is_policy_eligible": bool(policy_context["withinPolicy"]),
        "refund_amount": refund_amount,
        "updated_at": now_iso,
    }
    if reason:
        payload["reason"] = reason
    if attempt_increment > 0:
        payload["attempt_count"] = attempt_increment
        payload["last_attempt_at"] = now_iso
    if status in {"COMPLETED", "REJECTED"}:
        payload["resolved_at"] = now_iso

    if existing_rows:
        existing = existing_rows[0]
        next_attempt_count = int(existing.get(
            "attempt_count") or 0) + max(attempt_increment, 0)
        if attempt_increment > 0:
            payload["attempt_count"] = next_attempt_count
        result = (
            get_db()
            .table("cancellation_requests")
            .update(payload)
            .eq("cancellation_request_id", existing["cancellation_request_id"])
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else existing

    insert_payload = {
        "hold_id": transaction["hold_id"],
        "transaction_id": transaction["transaction_id"],
        "event_id": transaction["event_id"],
        "user_id": transaction["user_id"],
        "policy_cutoff_at": policy_context["policyCutoffAt"],
        "is_policy_eligible": bool(policy_context["withinPolicy"]),
        "status": status,
        "refund_amount": refund_amount,
        "reason": reason,
        "attempt_count": max(attempt_increment, 0),
        "last_attempt_at": now_iso if attempt_increment > 0 else None,
        "resolved_at": now_iso if status in {"COMPLETED", "REJECTED"} else None,
    }
    result = get_db().table("cancellation_requests").insert(insert_payload).execute()
    rows = result.data or []
    return rows[0] if rows else insert_payload


def _update_transaction(transaction_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload["updated_at"] = _iso_now()
    result = (
        get_db()
        .table("transactions")
        .update(payload)
        .eq("transaction_id", transaction_id)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else payload


def _record_webhook_event(
    event_id: str,
    payment_intent_id: Optional[str],
    hold_id: Optional[str],
    event_type: str,
    payload: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool]:
    insert_payload = {
        "webhook_event_id": event_id,
        "payment_intent_id": payment_intent_id,
        "hold_id": hold_id,
        "event_type": event_type,
        "payload": payload,
        "processing_status": "RECEIVED",
    }

    try:
        result = get_db().table("payment_webhook_events").insert(insert_payload).execute()
        rows = result.data or []
        return (rows[0] if rows else insert_payload), False
    except Exception as error:
        if not _is_duplicate_webhook_event_error(error):
            raise

        existing = _safe_db_select_one(
            "payment_webhook_events",
            {"webhook_event_id": event_id},
            "webhook_event_id,processing_status,received_at,processed_at",
        )
        if not existing:
            raise
        return existing, True


def _update_webhook_status(event_id: str, status: str, error_message: Optional[str] = None) -> None:
    update_payload = {
        "processing_status": status,
        "processed_at": _iso_now(),
        "error_message": error_message,
    }
    (
        get_db()
        .table("payment_webhook_events")
        .update(update_payload)
        .eq("webhook_event_id", event_id)
        .execute()
    )


def _extract_hold_id_from_metadata(payment_intent: Dict[str, Any]) -> Optional[str]:
    metadata = payment_intent.get("metadata") or {}
    hold_id = metadata.get("hold_id") or metadata.get("holdID")
    if not hold_id:
        return None
    try:
        return _as_uuid(hold_id, "holdID")
    except ValidationError:
        return None


def _publish_booking_confirmed(transaction: Dict[str, Any], payment_intent_id: str) -> None:
    email = _fetch_user_email(transaction["user_id"])
    waitlist_id = None
    try:
        waitlist_id = _resolve_waitlist_id_for_hold(transaction["hold_id"])
    except Exception as error:
        logger.warning(
            "Unable to resolve waitlist_id for hold_id=%s while publishing booking.confirmed: %s",
            transaction["hold_id"],
            error,
        )

    payload = {
        "holdID": transaction["hold_id"],
        "userID": transaction["user_id"],
        "eventID": transaction["event_id"],
        "email": email,
        "correlationID": transaction.get("correlation_id"),
        "paymentIntentID": payment_intent_id,
        "amount": str(transaction.get("amount")),
        "currency": _clean_currency(transaction.get("currency")),
        "waitlistID": waitlist_id,
    }
    publish_json("booking.confirmed", payload)


def _publish_refund_event(routing_key: str, payload: Dict[str, Any]) -> None:
    publish_json(routing_key, payload)


def _handle_payment_intent_succeeded(payment_intent: Dict[str, Any]) -> Dict[str, Any]:
    payment_intent_id = payment_intent.get("id")
    if not payment_intent_id:
        raise ValidationError("payment_intent.succeeded missing intent ID")

    transaction = _fetch_transaction_by_intent(payment_intent_id)
    if not transaction:
        raise NotFoundError("No transaction found for payment intent")

    _validate_payment_intent_amount_and_currency(payment_intent, transaction)

    update_payload = {
        "status": "SUCCEEDED",
        "failure_reason": None,
        "stripe_charge_id": payment_intent.get("latest_charge")
        or transaction.get("stripe_charge_id"),
        "provider_response": {
            "webhookType": "payment_intent.succeeded",
            "paymentIntent": {
                "id": payment_intent_id,
                "status": payment_intent.get("status"),
                "amount_received": payment_intent.get("amount_received"),
            },
        },
    }
    _update_transaction(transaction["transaction_id"], update_payload)

    transaction = _fetch_transaction_by_transaction_id(
        transaction["transaction_id"])
    if not transaction:
        raise NotFoundError(
            "Transaction disappeared during webhook processing")

    _publish_booking_confirmed(transaction, payment_intent_id)
    return transaction


def _handle_payment_intent_failed(payment_intent: Dict[str, Any]) -> Dict[str, Any]:
    payment_intent_id = payment_intent.get("id")
    if not payment_intent_id:
        raise ValidationError(
            "payment_intent.payment_failed missing intent ID")

    transaction = _fetch_transaction_by_intent(payment_intent_id)
    if not transaction:
        raise NotFoundError("No transaction found for payment intent")

    error_info = payment_intent.get("last_payment_error") or {}
    failure_reason = error_info.get("message") or "Payment failed"

    update_payload = {
        "status": "FAILED",
        "failure_reason": failure_reason,
        "provider_response": {
            "webhookType": "payment_intent.payment_failed",
            "paymentIntent": {
                "id": payment_intent_id,
                "status": payment_intent.get("status"),
                "last_payment_error": error_info,
            },
        },
    }
    _update_transaction(transaction["transaction_id"], update_payload)

    updated = _fetch_transaction_by_transaction_id(
        transaction["transaction_id"])
    if not updated:
        raise NotFoundError(
            "Transaction disappeared during failed webhook processing")
    return updated


def _normalize_status(value: str) -> str:
    normalized = str(value or "").strip().upper().replace(" ", "_")
    aliases = {
        "REFUND_SUCCESSFUL": "REFUND_SUCCEEDED",
        "SUCCESSFUL": "REFUND_SUCCEEDED",
        "SUCCESS": "REFUND_SUCCEEDED",
        "PAYMENT_MADE": "SUCCEEDED",
        "PROCESSING": "PROCESSING_REFUND",
        "REFUND_PENDING": "PROCESSING_REFUND",
        "IN_PROGRESS": "CANCELLATION_IN_PROGRESS",
    }
    return aliases.get(normalized, normalized)


def _apply_status_update(
    transaction: Dict[str, Any],
    requested_status: str,
    refund_amount: Optional[Decimal],
    reason: Optional[str],
    cancellation_override: Optional[str] = None,
) -> Dict[str, Any]:
    status = _normalize_status(requested_status)
    now_iso = _iso_now()
    transaction_update: Dict[str, Any] = {}
    cancellation_status: Optional[str] = cancellation_override

    if status == "PROCESSING_REFUND":
        transaction_update.update(
            {
                "status": "REFUND_PENDING",
                "refund_status": "PENDING",
                "refund_requested_at": now_iso,
            }
        )
        cancellation_status = cancellation_status or "PROCESSING_REFUND"
    elif status == "REFUND_SUCCEEDED":
        transaction_update.update(
            {
                "status": "REFUND_SUCCEEDED",
                "refund_status": "SUCCEEDED",
                "refunded_at": now_iso,
                "refund_amount": _decimal_to_str(refund_amount or _as_decimal(transaction["amount"], "amount")),
                "failure_reason": None,
            }
        )
        cancellation_status = cancellation_status or "REFUND_SUCCEEDED"
    elif status == "REFUND_FAILED":
        transaction_update.update(
            {
                "status": "REFUND_FAILED",
                "refund_status": "FAILED",
                "failure_reason": reason or transaction.get("failure_reason") or "Refund failed",
            }
        )
        cancellation_status = cancellation_status or "REFUND_FAILED"
    elif status == "SUCCEEDED":
        transaction_update.update(
            {
                "status": "SUCCEEDED",
                "failure_reason": None,
            }
        )
    elif status == "FAILED":
        transaction_update.update(
            {
                "status": "FAILED",
                "failure_reason": reason or "Payment failed",
            }
        )
    elif status == "PENDING":
        transaction_update.update({"status": "PENDING"})
    elif status in {"ELIGIBLE", "REJECTED", "CANCELLATION_IN_PROGRESS"}:
        cancellation_status = status
    else:
        raise ValidationError("Unsupported status value")

    if transaction_update:
        _update_transaction(transaction["transaction_id"], transaction_update)

    latest = _fetch_transaction_by_transaction_id(
        transaction["transaction_id"])
    if not latest:
        raise NotFoundError("Transaction not found after status update")

    if cancellation_status:
        policy = _compute_policy(latest)
        resolved_status = "COMPLETED" if cancellation_status == "REFUND_SUCCEEDED" else cancellation_status
        _create_cancellation_or_update(
            latest,
            resolved_status,
            policy,
            reason=reason,
        )

    return latest


def _create_refund_attempt(
    cancellation_request_id: str,
    transaction_id: str,
    attempt_no: int,
) -> Dict[str, Any]:
    payload = {
        "cancellation_request_id": cancellation_request_id,
        "transaction_id": transaction_id,
        "attempt_no": attempt_no,
        "status": "PENDING",
        "attempted_at": _iso_now(),
    }
    result = get_db().table("refund_attempts").insert(payload).execute()
    rows = result.data or []
    return rows[0] if rows else payload


def _get_latest_refund_attempt_no(cancellation_request_id: str) -> int:
    attempts = _safe_db_select_many(
        "refund_attempts",
        {"cancellation_request_id": cancellation_request_id},
        "attempt_no",
        order_by="attempt_no",
        desc=True,
        limit=1,
    )
    if not attempts:
        return 0
    return int(attempts[0].get("attempt_no") or 0)


def _fetch_pending_refund_attempt(cancellation_request_id: str) -> Optional[Dict[str, Any]]:
    attempts = _safe_db_select_many(
        "refund_attempts",
        {
            "cancellation_request_id": cancellation_request_id,
            "status": "PENDING",
        },
        "refund_attempt_id,attempt_no,attempted_at,status",
        order_by="attempted_at",
        desc=True,
        limit=1,
    )
    return attempts[0] if attempts else None


def _update_refund_attempt(refund_attempt_id: str, payload: Dict[str, Any]) -> None:
    payload["completed_at"] = _iso_now()
    (
        get_db()
        .table("refund_attempts")
        .update(payload)
        .eq("refund_attempt_id", refund_attempt_id)
        .execute()
    )


def _execute_refund(
    transaction: Dict[str, Any],
    requested_refund_amount: Optional[Decimal],
    reason: Optional[str],
) -> Dict[str, Any]:
    current_status = str(transaction.get("status") or "").upper()

    latest_cancellation_rows = _safe_db_select_many(
        "cancellation_requests",
        {"hold_id": transaction["hold_id"]},
        "cancellation_request_id,status",
        order_by="requested_at",
        desc=True,
        limit=1,
    )
    latest_cancellation = latest_cancellation_rows[0] if latest_cancellation_rows else None

    if current_status == "REFUND_PENDING":
        if latest_cancellation:
            pending_attempt = _fetch_pending_refund_attempt(
                latest_cancellation["cancellation_request_id"]
            )
            if pending_attempt and _is_recent_timestamp(
                pending_attempt.get("attempted_at"),
                REFUND_PENDING_STALE_SECONDS,
            ):
                raise ConflictError("Refund is already in progress")

            if pending_attempt:
                _update_refund_attempt(
                    pending_attempt["refund_attempt_id"],
                    {
                        "status": "FAILED",
                        "error_code": "STALE_PENDING",
                        "error_message": "Stale pending refund attempt recovered",
                        "provider_payload": {
                            "recovery": "stale_pending_recovered",
                            "attempt_no": pending_attempt.get("attempt_no"),
                        },
                    },
                )

    if current_status not in {
        "SUCCEEDED",
        "REFUND_FAILED",
        "REFUND_SUCCEEDED",
        "REFUND_PENDING",
    }:
        raise ConflictError("Only successful payments can be refunded")

    policy = _compute_policy(transaction)
    if not policy["withinPolicy"]:
        _create_cancellation_or_update(
            transaction,
            "REJECTED",
            policy,
            reason="Not eligible under 48-hour cancellation policy",
        )
        raise ConflictError("Booking is not eligible for refund under policy")

    eligible_amount = _as_decimal(
        policy["eligibleRefundAmount"], "eligible refund amount")
    refund_amount = requested_refund_amount or eligible_amount
    if refund_amount > _as_decimal(transaction["amount"], "transaction amount"):
        raise ValidationError("refundAmount cannot exceed transaction amount")

    if current_status == "REFUND_SUCCEEDED":
        return {
            "status": "already_refunded",
            "transactionID": transaction["transaction_id"],
            "refundAmount": str(transaction.get("refund_amount") or _decimal_to_str(refund_amount)),
            "attempts": 0,
        }

    _apply_status_update(transaction, "PROCESSING_REFUND",
                         refund_amount, reason)
    latest_transaction = _fetch_transaction_by_transaction_id(
        transaction["transaction_id"])
    if not latest_transaction:
        raise NotFoundError("Transaction not found before refund execution")

    cancellation_request = _create_cancellation_or_update(
        latest_transaction,
        "PROCESSING_REFUND",
        policy,
        reason=reason,
    )
    cancellation_request_id = cancellation_request["cancellation_request_id"]
    attempt_start = _get_latest_refund_attempt_no(cancellation_request_id) + 1

    if not latest_transaction.get("stripe_payment_intent_id"):
        raise ValidationError(
            "Transaction does not contain a Stripe payment intent ID")

    last_error_message = "Unknown refund failure"
    last_attempt_no = attempt_start - 1
    for attempt_offset in range(MAX_REFUND_ATTEMPTS):
        attempt_no = attempt_start + attempt_offset
        last_attempt_no = attempt_no
        refund_attempt = _create_refund_attempt(
            cancellation_request_id,
            latest_transaction["transaction_id"],
            attempt_no,
        )

        try:
            refund = stripe.Refund.create(
                payment_intent=latest_transaction["stripe_payment_intent_id"],
                amount=_to_minor_units(refund_amount),
                metadata={
                    "transaction_id": latest_transaction["transaction_id"],
                    "hold_id": latest_transaction["hold_id"],
                    "attempt_no": str(attempt_no),
                },
                idempotency_key=(
                    f"refund:{latest_transaction['transaction_id']}:{attempt_no}"
                ),
            )
            refund_data = _stripe_object_to_dict(refund)
            _update_refund_attempt(
                refund_attempt["refund_attempt_id"],
                {
                    "status": "SUCCEEDED",
                    "provider_reference": refund_data.get("id"),
                    "provider_payload": refund_data,
                    "error_code": None,
                    "error_message": None,
                },
            )

            updated_transaction = _apply_status_update(
                latest_transaction,
                "REFUND_SUCCEEDED",
                refund_amount,
                reason,
            )
            _create_cancellation_or_update(
                updated_transaction,
                "COMPLETED",
                policy,
                reason=reason,
            )

            email = _fetch_user_email(updated_transaction["user_id"])
            _publish_refund_event(
                "refund.successful",
                {
                    "bookingID": updated_transaction["transaction_id"],
                    "transactionID": updated_transaction["transaction_id"],
                    "holdID": updated_transaction["hold_id"],
                    "userID": updated_transaction["user_id"],
                    "eventID": updated_transaction["event_id"],
                    "email": email,
                    "refundAmount": _decimal_to_str(refund_amount),
                    "currency": _clean_currency(updated_transaction.get("currency")),
                    "correlationID": updated_transaction.get("correlation_id"),
                },
            )

            return {
                "status": "success",
                "transactionID": updated_transaction["transaction_id"],
                "refundAmount": _decimal_to_str(refund_amount),
                "attempts": attempt_no,
            }
        except stripe.error.StripeError as error:
            last_error_message = str(error)
            logger.warning(
                "Stripe refund attempt %s failed for transaction %s: %s",
                attempt_no,
                latest_transaction["transaction_id"],
                error,
            )
            _update_refund_attempt(
                refund_attempt["refund_attempt_id"],
                {
                    "status": "FAILED",
                    "error_code": getattr(error, "code", None),
                    "error_message": str(error),
                    "provider_payload": {
                        "errorType": error.__class__.__name__,
                        "message": str(error),
                    },
                },
            )

    failed_transaction = _apply_status_update(
        latest_transaction,
        "REFUND_FAILED",
        refund_amount,
        last_error_message,
        cancellation_override="CANCELLATION_IN_PROGRESS",
    )
    _create_cancellation_or_update(
        failed_transaction,
        "CANCELLATION_IN_PROGRESS",
        policy,
        reason=last_error_message,
        attempt_increment=MAX_REFUND_ATTEMPTS,
    )

    email = _fetch_user_email(failed_transaction["user_id"])
    _publish_refund_event(
        "refund.error",
        {
            "bookingID": failed_transaction["transaction_id"],
            "transactionID": failed_transaction["transaction_id"],
            "holdID": failed_transaction["hold_id"],
            "userID": failed_transaction["user_id"],
            "eventID": failed_transaction["event_id"],
            "email": email,
            "errorDetail": last_error_message,
            "retryCount": last_attempt_no,
            "nextSteps": "Cancellation remains in progress. Manual follow-up required.",
            "correlationID": failed_transaction.get("correlation_id"),
        },
    )

    raise ExternalServiceError("Refund failed after maximum retry attempts")


def _api_response(payload: Dict[str, Any], status_code: int = 200):
    return jsonify(payload), status_code


def _handle_api_error(error: ApiError):
    return jsonify({"error": error.message}), error.status_code


def _build_openapi_spec() -> Dict[str, Any]:
    internal_token_header = {
        "name": INTERNAL_AUTH_HEADER,
        "in": "header",
        "required": False,
        "description": "Required when PAYMENT_INTERNAL_TOKEN is configured.",
        "schema": {"type": "string"},
    }
    stripe_signature_header = {
        "name": "Stripe-Signature",
        "in": "header",
        "required": True,
        "description": "Stripe signature used for webhook verification.",
        "schema": {"type": "string"},
    }
    error_response = {
        "description": "Error response",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
            }
        },
    }

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "TicketBlitz Payment Service API",
            "version": "1.0.0",
            "description": "Payment, webhook, verification, and refund endpoints for TicketBlitz.",
        },
        "servers": [{"url": os.getenv("OPENAPI_SERVER_URL", "/")}],
        "tags": [
            {"name": "Health", "description": "Service health and readiness checks."},
            {"name": "Payments", "description": "Payment lifecycle and state transitions."},
            {"name": "Refunds", "description": "Refund orchestration and cancellation flow."},
            {"name": "Webhooks", "description": "Stripe webhook ingestion and processing."},
            {"name": "Docs", "description": "OpenAPI and Swagger documentation endpoints."},
        ],
        "components": {
            "securitySchemes": {
                "InternalTokenAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": INTERNAL_AUTH_HEADER,
                    "description": "Used for internal endpoints when PAYMENT_INTERNAL_TOKEN is set.",
                },
                "StripeSignatureAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Stripe-Signature",
                    "description": "Stripe webhook signature header.",
                },
            },
            "schemas": {
                "ErrorResponse": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {"error": {"type": "string"}},
                },
                "HealthResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "ok"},
                        "service": {"type": "string", "example": "payment-service"},
                        "supabaseConfigured": {"type": "boolean"},
                        "rabbitmqConfigured": {"type": "boolean"},
                        "stripeConfigured": {"type": "boolean"},
                    },
                },
                "PaymentInitiateRequest": {
                    "type": "object",
                    "required": ["holdID", "userID", "amount"],
                    "properties": {
                        "holdID": {"type": "string", "format": "uuid"},
                        "userID": {"type": "string", "format": "uuid"},
                        "amount": {"type": "number", "format": "decimal"},
                        "idempotencyKey": {"type": "string"},
                    },
                },
                "PaymentInitiateResponse": {
                    "type": "object",
                    "properties": {
                        "holdID": {"type": "string", "format": "uuid"},
                        "paymentIntentID": {"type": "string"},
                        "clientSecret": {"type": "string"},
                        "amount": {"type": "string", "example": "10.00"},
                        "currency": {"type": "string", "example": "SGD"},
                        "status": {"type": "string"},
                        "holdExpiry": {"type": "string", "format": "date-time"},
                        "transactionID": {"type": ["string", "null"], "format": "uuid"},
                    },
                },
                "PaymentHoldResponse": {
                    "type": "object",
                    "properties": {
                        "holdID": {"type": "string", "format": "uuid"},
                        "transactionID": {"type": ["string", "null"], "format": "uuid"},
                        "paymentIntentID": {"type": ["string", "null"]},
                        "paymentStatus": {"type": "string"},
                        "amount": {"type": "string"},
                        "currency": {"type": "string"},
                        "failureReason": {"type": ["string", "null"]},
                        "createdAt": {"type": ["string", "null"], "format": "date-time"},
                        "updatedAt": {"type": ["string", "null"], "format": "date-time"},
                    },
                },
                "WebhookAcceptedResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "accepted"},
                        "eventType": {"type": "string"},
                        "idempotent": {"type": "boolean"},
                    },
                },
                "VerifyPaymentResponse": {
                    "type": "object",
                    "properties": {
                        "bookingID": {"type": "string", "format": "uuid"},
                        "resolvedBy": {"type": "string", "enum": ["transaction_id", "hold_id"]},
                        "transactionID": {"type": "string", "format": "uuid"},
                        "holdID": {"type": "string", "format": "uuid"},
                        "userID": {"type": "string", "format": "uuid"},
                        "eventID": {"type": "string", "format": "uuid"},
                        "paymentStatus": {"type": "string"},
                        "purchaseDate": {"type": "string", "format": "date-time"},
                        "eventDate": {"type": "string", "format": "date-time"},
                        "policyCutoffAt": {"type": "string", "format": "date-time"},
                        "withinPolicy": {"type": "boolean"},
                        "eligibleRefundAmount": {"type": "string"},
                        "feePercentage": {"type": "string", "example": "10.00"},
                    },
                },
                "VerifyPolicyResponse": {
                    "type": "object",
                    "properties": {
                        "bookingID": {"type": "string", "format": "uuid"},
                        "resolvedBy": {"type": "string", "enum": ["transaction_id", "hold_id"]},
                        "transactionID": {"type": "string", "format": "uuid"},
                        "eligible": {"type": "boolean"},
                        "withinPolicy": {"type": "boolean"},
                        "reason": {"type": "string"},
                        "policyCutoffAt": {"type": "string", "format": "date-time"},
                        "eventDate": {"type": "string", "format": "date-time"},
                        "purchaseDate": {"type": "string", "format": "date-time"},
                    },
                },
                "UpdateStatusRequest": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "refundAmount": {"type": "number", "format": "decimal"},
                        "reason": {"type": "string"},
                        "cancellationStatus": {"type": "string"},
                    },
                },
                "UpdateStatusResponse": {
                    "type": "object",
                    "properties": {
                        "updated": {"type": "boolean"},
                        "bookingID": {"type": "string"},
                        "transactionID": {"type": ["string", "null"], "format": "uuid"},
                        "status": {"type": "string"},
                        "refundStatus": {"type": ["string", "null"]},
                        "refundAmount": {"type": ["string", "null"]},
                    },
                },
                "PaymentCreateRequest": {
                    "type": "object",
                    "required": ["userID", "amount"],
                    "properties": {
                        "holdID": {"type": "string", "format": "uuid"},
                        "ticketID": {"type": "string", "format": "uuid"},
                        "userID": {"type": "string", "format": "uuid"},
                        "amount": {"type": "number", "format": "decimal"},
                        "idempotencyKey": {"type": "string"},
                    },
                },
                "RefundRequest": {
                    "type": "object",
                    "properties": {
                        "refundAmount": {"type": "number", "format": "decimal"},
                        "reason": {"type": "string"},
                    },
                },
                "RefundResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "success"},
                        "transactionID": {"type": "string", "format": "uuid"},
                        "refundAmount": {"type": "string", "example": "90.00"},
                        "attempts": {"type": "integer", "minimum": 0},
                    },
                },
                "FailStatusRequest": {
                    "type": "object",
                    "properties": {
                        "bookingID": {"type": "string", "format": "uuid"},
                        "bookingId": {"type": "string", "format": "uuid"},
                        "transactionID": {"type": "string", "format": "uuid"},
                        "transactionId": {"type": "string", "format": "uuid"},
                        "holdID": {"type": "string", "format": "uuid"},
                        "holdId": {"type": "string", "format": "uuid"},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
        "paths": {
            "/health": {
                "get": {
                    "tags": ["Health"],
                    "summary": "Service health check",
                    "responses": {
                        "200": {
                            "description": "Service status and dependency flags",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/openapi.json": {
                "get": {
                    "tags": ["Docs"],
                    "summary": "OpenAPI specification",
                    "responses": {
                        "200": {
                            "description": "OpenAPI document",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            },
                        }
                    },
                }
            },
            "/payment/initiate": {
                "post": {
                    "tags": ["Payments"],
                    "summary": "Initiate payment for a seat hold",
                    "parameters": [internal_token_header],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/PaymentInitiateRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Existing pending payment intent returned",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PaymentInitiateResponse"}
                                }
                            },
                        },
                        "201": {
                            "description": "Payment intent created",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PaymentInitiateResponse"}
                                }
                            },
                        },
                        "400": error_response,
                        "401": error_response,
                        "409": error_response,
                        "502": error_response,
                        "503": error_response,
                    },
                }
            },
            "/payment/hold/{hold_id}": {
                "get": {
                    "tags": ["Payments"],
                    "summary": "Get payment status by hold ID",
                    "parameters": [
                        {
                            "name": "hold_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Payment status for hold",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PaymentHoldResponse"}
                                }
                            },
                        },
                        "404": error_response,
                        "503": error_response,
                    },
                }
            },
            "/payment/webhook": {
                "post": {
                    "tags": ["Webhooks"],
                    "summary": "Stripe webhook receiver",
                    "description": "Verifies Stripe signature, records webhook event, and updates transactions.",
                    "parameters": [stripe_signature_header],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Webhook accepted",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/WebhookAcceptedResponse"}
                                }
                            },
                        },
                        "400": error_response,
                        "503": error_response,
                    },
                }
            },
            "/payments/verify/{booking_id}": {
                "get": {
                    "tags": ["Payments"],
                    "summary": "Verify booking payment and refund eligibility context",
                    "parameters": [
                        {
                            "name": "booking_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Booking payment verification data",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/VerifyPaymentResponse"}
                                }
                            },
                        },
                        "404": error_response,
                        "503": error_response,
                    },
                }
            },
            "/payments/verify-policy/{booking_id}": {
                "get": {
                    "tags": ["Payments"],
                    "summary": "Verify cancellation policy for booking",
                    "parameters": [
                        {
                            "name": "booking_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Cancellation policy evaluation",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/VerifyPolicyResponse"}
                                }
                            },
                        },
                        "404": error_response,
                        "503": error_response,
                    },
                }
            },
            "/payments/status/{booking_id}": {
                "put": {
                    "tags": ["Payments"],
                    "summary": "Update payment/refund status",
                    "parameters": [
                        {
                            "name": "booking_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        internal_token_header,
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/UpdateStatusRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Status update result",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/UpdateStatusResponse"}
                                }
                            },
                        },
                        "400": error_response,
                        "401": error_response,
                        "404": error_response,
                    },
                }
            },
            "/payments/update/{booking_id}": {
                "put": {
                    "tags": ["Payments"],
                    "summary": "Alias for /payments/status/{booking_id}",
                    "parameters": [
                        {
                            "name": "booking_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        internal_token_header,
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/UpdateStatusRequest"}
                            }
                        },
                    },
                    "responses": {"200": {"description": "Alias response"}, "400": error_response, "401": error_response},
                }
            },
            "/payments/processing/{booking_id}": {
                "put": {
                    "tags": ["Payments"],
                    "summary": "Mark booking as processing refund",
                    "parameters": [
                        {
                            "name": "booking_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        internal_token_header,
                    ],
                    "responses": {
                        "200": {
                            "description": "Processing status updated",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/UpdateStatusResponse"}
                                }
                            },
                        },
                        "401": error_response,
                        "404": error_response,
                    },
                }
            },
            "/payments/success/{booking_id}": {
                "put": {
                    "tags": ["Payments"],
                    "summary": "Mark booking refund as succeeded",
                    "parameters": [
                        {
                            "name": "booking_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        internal_token_header,
                    ],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/RefundRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Success status updated",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/UpdateStatusResponse"}
                                }
                            },
                        },
                        "401": error_response,
                        "404": error_response,
                    },
                }
            },
            "/payments/status/fail": {
                "put": {
                    "tags": ["Payments"],
                    "summary": "Mark booking refund as failed",
                    "parameters": [internal_token_header],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/FailStatusRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Failure status updated",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/UpdateStatusResponse"}
                                }
                            },
                        },
                        "400": error_response,
                        "401": error_response,
                    },
                }
            },
            "/payments/create": {
                "post": {
                    "tags": ["Payments"],
                    "summary": "Alias payment creation endpoint",
                    "parameters": [internal_token_header],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/PaymentCreateRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Existing payment returned",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PaymentInitiateResponse"}
                                }
                            },
                        },
                        "201": {
                            "description": "Payment created",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PaymentInitiateResponse"}
                                }
                            },
                        },
                        "400": error_response,
                        "401": error_response,
                    },
                }
            },
            "/payments/refund/{booking_id}": {
                "post": {
                    "tags": ["Refunds"],
                    "summary": "Execute refund for booking",
                    "parameters": [
                        {
                            "name": "booking_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        internal_token_header,
                    ],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/RefundRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Refund processing result",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/RefundResponse"}
                                }
                            },
                        },
                        "400": error_response,
                        "401": error_response,
                        "404": error_response,
                        "409": error_response,
                        "502": error_response,
                    },
                }
            },
            "/payments/refund": {
                "post": {
                    "tags": ["Refunds"],
                    "summary": "Alias for /payments/refund/{booking_id}",
                    "parameters": [internal_token_header],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/FailStatusRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Refund processing result",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/RefundResponse"}
                                }
                            },
                        },
                        "400": error_response,
                        "401": error_response,
                    },
                }
            },
        },
    }


def _process_payment_initiation(
    hold_id: str,
    user_id: str,
    requested_amount: Decimal,
    idempotency_key: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    _require_supabase()
    _require_stripe()

    hold = _fetch_hold(hold_id)
    if hold["user_id"] != user_id:
        raise ConflictError("holdID does not belong to userID")

    if hold["status"] != "HELD":
        raise ConflictError("Seat hold is not in HELD status")

    hold_expiry = _parse_datetime(hold.get("hold_expires_at"))
    if hold_expiry and hold_expiry <= _utcnow():
        raise ConflictError("Seat hold has expired")

    hold_amount = _as_decimal(hold["amount"], "hold amount")
    if requested_amount != hold_amount:
        raise ConflictError("amount does not match hold amount")

    latest_transaction = _fetch_latest_transaction_for_hold(hold_id)
    if latest_transaction and latest_transaction.get("status") == "SUCCEEDED":
        raise ConflictError("Payment already completed for this hold")

    if latest_transaction and latest_transaction.get("status") == "PENDING":
        provider_response = latest_transaction.get("provider_response") or {}
        payment_data = provider_response.get("paymentIntent") or {}
        client_secret = payment_data.get("client_secret")
        if client_secret and latest_transaction.get("stripe_payment_intent_id"):
            return (
                {
                    "holdID": hold_id,
                    "paymentIntentID": latest_transaction["stripe_payment_intent_id"],
                    "clientSecret": client_secret,
                    "amount": _decimal_to_str(hold_amount),
                    "currency": _clean_currency(hold.get("currency")),
                    "status": latest_transaction["status"],
                    "holdExpiry": hold.get("hold_expires_at"),
                    "transactionID": latest_transaction.get("transaction_id"),
                },
                200,
            )

    currency = _clean_currency(hold.get("currency"))
    correlation_id = hold.get("correlation_id") or str(uuid.uuid4())
    resolved_idempotency_key = idempotency_key or f"{PAYMENT_IDEMPOTENCY_PREFIX}:{hold_id}"

    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=_to_minor_units(hold_amount),
            currency=currency.lower(),
            metadata={
                "hold_id": hold_id,
                "user_id": user_id,
                "event_id": hold["event_id"],
                "correlation_id": correlation_id,
            },
            automatic_payment_methods={"enabled": True},
            idempotency_key=str(resolved_idempotency_key),
        )
    except stripe.error.StripeError as error:
        logger.exception(
            "Stripe PaymentIntent creation failed for hold %s: %s", hold_id, error)
        raise ExternalServiceError(
            "Payment provider request failed") from error

    payment_intent_data = _stripe_object_to_dict(payment_intent)

    insert_payload = {
        "hold_id": hold_id,
        "event_id": hold["event_id"],
        "user_id": user_id,
        "amount": _decimal_to_str(hold_amount),
        "currency": currency,
        "stripe_payment_intent_id": payment_intent_data.get("id"),
        "status": "PENDING",
        "idempotency_key": str(resolved_idempotency_key),
        "correlation_id": correlation_id,
        "provider_response": {
            "paymentIntent": {
                "id": payment_intent_data.get("id"),
                "status": payment_intent_data.get("status"),
                "client_secret": payment_intent_data.get("client_secret"),
            }
        },
        "metadata": {
            "source": "payment-service",
            "fromWaitlist": bool(hold.get("from_waitlist")),
        },
    }

    try:
        insert_result = get_db().table("transactions").insert(insert_payload).execute()
        inserted_rows = insert_result.data or []
        transaction_id = inserted_rows[0]["transaction_id"] if inserted_rows else None
    except Exception as error:
        logger.exception("Failed to insert transaction record: %s", error)
        raise ExternalServiceError(
            "Failed to persist transaction record") from error

    return (
        {
            "holdID": hold_id,
            "paymentIntentID": payment_intent_data.get("id"),
            "clientSecret": payment_intent_data.get("client_secret"),
            "amount": _decimal_to_str(hold_amount),
            "currency": currency,
            "status": "PENDING",
            "holdExpiry": hold.get("hold_expires_at"),
            "transactionID": transaction_id,
        },
        201,
    )


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

    swagger_url = os.getenv("SWAGGER_URL", "/docs")
    openapi_url = os.getenv("OPENAPI_URL", "/openapi.json")

    @app.get(openapi_url)
    def openapi_spec():
        return jsonify(_build_openapi_spec())

    try:
        from flask_swagger_ui import get_swaggerui_blueprint

        swagger_blueprint = get_swaggerui_blueprint(
            swagger_url,
            openapi_url,
            config={"app_name": "TicketBlitz Payment Service"},
        )
        app.register_blueprint(swagger_blueprint, url_prefix=swagger_url)
    except Exception as error:
        logger.warning("Swagger UI dependency unavailable: %s", error)

        @app.get(swagger_url)
        def swagger_ui_fallback():
            html = f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <title>TicketBlitz Payment API Docs</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui.css\" />
  </head>
  <body>
    <div id=\"swagger-ui\"></div>
    <script src=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js\"></script>
    <script>
      window.ui = SwaggerUIBundle({{
        url: '{openapi_url}',
        dom_id: '#swagger-ui',
      }});
    </script>
  </body>
</html>
"""
            return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.get("/health")
    def health():
        return (
            jsonify(
                {
                    "status": "ok",
                    "service": os.getenv("SERVICE_NAME", "payment-service"),
                    "supabaseConfigured": db_configured(),
                    "rabbitmqConfigured": rabbitmq_configured(),
                    "stripeConfigured": bool(os.getenv("STRIPE_SECRET_KEY")),
                }
            ),
            200,
        )

    @app.post("/payment/initiate")
    def payment_initiate():
        try:
            _require_internal_auth()

            payload = _get_json_payload()
            hold_id = _as_uuid(payload.get("holdID")
                               or payload.get("hold_id"), "holdID")
            user_id = _as_uuid(payload.get("userID")
                               or payload.get("user_id"), "userID")
            requested_amount = _as_decimal(payload.get("amount"), "amount")
            idempotency_key = (
                payload.get("idempotencyKey")
                or payload.get("idempotency_key")
                or request.headers.get("Idempotency-Key")
                or f"{PAYMENT_IDEMPOTENCY_PREFIX}:{hold_id}"
            )

            response_payload, status_code = _process_payment_initiation(
                hold_id,
                user_id,
                requested_amount,
                idempotency_key=idempotency_key,
            )
            return _api_response(response_payload, status_code)
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error while initiating payment: %s", error)
            return _api_response({"error": "Failed to initiate payment"}, 500)

    @app.get("/payment/hold/<hold_id>")
    def payment_hold_status(hold_id: str):
        try:
            _require_supabase()
            hold_uuid = _as_uuid(hold_id, "holdID")
            transaction = _fetch_latest_transaction_for_hold(hold_uuid)
            if not transaction:
                raise NotFoundError("No transaction found for hold")

            return _api_response(
                {
                    "holdID": hold_uuid,
                    "transactionID": transaction.get("transaction_id"),
                    "paymentIntentID": transaction.get("stripe_payment_intent_id"),
                    "paymentStatus": transaction.get("status"),
                    "amount": str(transaction.get("amount")),
                    "currency": _clean_currency(transaction.get("currency")),
                    "failureReason": transaction.get("failure_reason"),
                    "createdAt": transaction.get("created_at"),
                    "updatedAt": transaction.get("updated_at"),
                }
            )
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error while loading payment hold status: %s", error)
            return _api_response({"error": "Failed to load payment hold status"}, 500)

    @app.post("/payment/webhook")
    def payment_webhook():
        try:
            _require_supabase()
            _require_stripe()

            payload = request.get_data()
            signature = request.headers.get("Stripe-Signature")
            webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
            if not webhook_secret:
                raise DependencyError(
                    "STRIPE_WEBHOOK_SECRET is not configured")
            if not signature:
                raise ValidationError("Missing Stripe-Signature header")

            try:
                event = stripe.Webhook.construct_event(
                    payload, signature, webhook_secret)
            except ValueError as error:
                raise ValidationError("Invalid payload") from error
            except stripe.error.SignatureVerificationError as error:
                raise ValidationError("Invalid signature") from error

            event_data = _stripe_object_to_dict(event)
            event_id = event_data.get("id")
            event_type = event_data.get("type") or "unknown"
            payment_intent = (event_data.get("data") or {}).get("object") or {}
            payment_intent_id = payment_intent.get("id")
            hold_id = _extract_hold_id_from_metadata(payment_intent)

            if not event_id:
                raise ValidationError("Webhook event ID is missing")

            existing_record, already_exists = _record_webhook_event(
                event_id,
                payment_intent_id,
                hold_id,
                event_type,
                event_data,
            )

            if already_exists and existing_record.get("processing_status") in {
                "PROCESSED",
                "IGNORED",
            }:
                return _api_response(
                    {
                        "status": "accepted",
                        "eventType": event_type,
                        "idempotent": True,
                    },
                    200,
                )

            if (
                already_exists
                and existing_record.get("processing_status") == "RECEIVED"
                and _is_recent_timestamp(
                    existing_record.get("received_at"),
                    WEBHOOK_RECEIVED_STALE_SECONDS,
                )
            ):
                return _api_response(
                    {
                        "status": "accepted",
                        "eventType": event_type,
                        "idempotent": True,
                    },
                    200,
                )

            try:
                if event_type == "payment_intent.succeeded":
                    _handle_payment_intent_succeeded(payment_intent)
                    _update_webhook_status(event_id, "PROCESSED")
                elif event_type == "payment_intent.payment_failed":
                    _handle_payment_intent_failed(payment_intent)
                    _update_webhook_status(event_id, "PROCESSED")
                else:
                    _update_webhook_status(event_id, "IGNORED")
            except Exception as error:
                logger.exception(
                    "Webhook processing failed for %s: %s", event_id, error)
                _update_webhook_status(event_id, "FAILED", str(error))
                raise

            return _api_response(
                {
                    "status": "accepted",
                    "eventType": event_type,
                    "idempotent": False,
                },
                200,
            )
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception("Unexpected webhook error: %s", error)
            return _api_response({"error": "Failed to process webhook"}, 500)

    @app.get("/payments/verify/<booking_id>")
    def payments_verify(booking_id: str):
        try:
            _require_supabase()
            transaction, resolved_by = _resolve_booking_transaction(booking_id)
            policy = _compute_policy(transaction)
            return _api_response(
                {
                    "bookingID": booking_id,
                    "resolvedBy": resolved_by,
                    "transactionID": transaction["transaction_id"],
                    "holdID": transaction["hold_id"],
                    "userID": transaction["user_id"],
                    "eventID": transaction["event_id"],
                    "paymentStatus": transaction["status"],
                    "purchaseDate": policy["purchaseDate"],
                    "eventDate": policy["eventDate"],
                    "policyCutoffAt": policy["policyCutoffAt"],
                    "withinPolicy": policy["withinPolicy"],
                    "eligibleRefundAmount": policy["eligibleRefundAmount"],
                    "feePercentage": policy["feePercentage"],
                }
            )
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error verifying booking payment: %s", error)
            return _api_response({"error": "Failed to verify booking payment"}, 500)

    @app.get("/payments/verify-policy/<booking_id>")
    def payments_verify_policy(booking_id: str):
        try:
            _require_supabase()
            transaction, resolved_by = _resolve_booking_transaction(booking_id)
            policy = _compute_policy(transaction)
            reason = (
                "Eligible for refund"
                if policy["withinPolicy"]
                else "Not eligible under 48-hour cancellation policy"
            )
            return _api_response(
                {
                    "bookingID": booking_id,
                    "resolvedBy": resolved_by,
                    "transactionID": transaction["transaction_id"],
                    "eligible": policy["withinPolicy"],
                    "withinPolicy": policy["withinPolicy"],
                    "reason": reason,
                    "policyCutoffAt": policy["policyCutoffAt"],
                    "eventDate": policy["eventDate"],
                    "purchaseDate": policy["purchaseDate"],
                }
            )
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error verifying cancellation policy: %s", error)
            return _api_response({"error": "Failed to verify cancellation policy"}, 500)

    @app.put("/payments/status/<booking_id>")
    def payments_update_status(booking_id: str):
        try:
            _require_internal_auth()
            _require_supabase()
            payload = _get_json_payload()
            requested_status = payload.get("status")
            if not requested_status:
                raise ValidationError("status is required")

            transaction, _ = _resolve_booking_transaction(booking_id)
            refund_amount = (
                _as_decimal(payload.get("refundAmount"), "refundAmount")
                if payload.get("refundAmount") is not None
                else None
            )
            reason = payload.get("reason")
            cancellation_status = payload.get("cancellationStatus")

            updated_transaction = _apply_status_update(
                transaction,
                requested_status,
                refund_amount,
                reason,
                cancellation_override=(
                    _normalize_status(
                        cancellation_status) if cancellation_status else None
                ),
            )

            return _api_response(
                {
                    "updated": True,
                    "bookingID": booking_id,
                    "transactionID": updated_transaction.get("transaction_id"),
                    "status": updated_transaction.get("status"),
                    "refundStatus": updated_transaction.get("refund_status"),
                    "refundAmount": str(updated_transaction.get("refund_amount")),
                }
            )
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error updating payment status: %s", error)
            return _api_response({"error": "Failed to update payment status"}, 500)

    @app.put("/payments/update/<booking_id>")
    def payments_update_alias(booking_id: str):
        return payments_update_status(booking_id)

    @app.put("/payments/processing/<booking_id>")
    def payments_processing_alias(booking_id: str):
        try:
            _require_internal_auth()
            _require_supabase()
            transaction, _ = _resolve_booking_transaction(booking_id)
            updated_transaction = _apply_status_update(
                transaction,
                "PROCESSING_REFUND",
                None,
                None,
            )
            return _api_response(
                {
                    "updated": True,
                    "bookingID": booking_id,
                    "transactionID": updated_transaction.get("transaction_id"),
                    "status": updated_transaction.get("status"),
                }
            )
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error setting processing state: %s", error)
            return _api_response({"error": "Failed to update processing state"}, 500)

    @app.put("/payments/success/<booking_id>")
    def payments_success_alias(booking_id: str):
        try:
            _require_internal_auth()
            _require_supabase()
            payload = _get_json_payload()
            transaction, _ = _resolve_booking_transaction(booking_id)
            refund_amount = (
                _as_decimal(payload.get("refundAmount"), "refundAmount")
                if payload.get("refundAmount") is not None
                else None
            )
            updated_transaction = _apply_status_update(
                transaction,
                "REFUND_SUCCEEDED",
                refund_amount,
                payload.get("reason"),
            )
            return _api_response(
                {
                    "updated": True,
                    "bookingID": booking_id,
                    "transactionID": updated_transaction.get("transaction_id"),
                    "status": updated_transaction.get("status"),
                }
            )
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error setting success state: %s", error)
            return _api_response({"error": "Failed to update success state"}, 500)

    @app.put("/payments/status/fail")
    def payments_fail_alias():
        try:
            _require_internal_auth()
            _require_supabase()
            payload = _get_json_payload()
            booking_id = (
                payload.get("bookingID")
                or payload.get("bookingId")
                or payload.get("transactionID")
                or payload.get("transactionId")
                or payload.get("holdID")
                or payload.get("holdId")
            )
            if not booking_id:
                raise ValidationError("bookingID or transactionID is required")

            transaction, _ = _resolve_booking_transaction(str(booking_id))
            updated_transaction = _apply_status_update(
                transaction,
                "REFUND_FAILED",
                None,
                payload.get("reason") or "Refund failed",
                cancellation_override="CANCELLATION_IN_PROGRESS",
            )

            return _api_response(
                {
                    "updated": True,
                    "bookingID": booking_id,
                    "transactionID": updated_transaction.get("transaction_id"),
                    "status": updated_transaction.get("status"),
                }
            )
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception("Unexpected error setting fail state: %s", error)
            return _api_response({"error": "Failed to update fail state"}, 500)

    @app.post("/payments/create")
    def payments_create_alias():
        try:
            _require_internal_auth()
            payload = _get_json_payload()
            hold_id = payload.get("holdID") or payload.get(
                "hold_id") or payload.get("ticketID")
            if not hold_id:
                raise ValidationError(
                    "holdID (or ticketID) is required for payment creation")

            hold_uuid = _as_uuid(hold_id, "holdID")
            user_uuid = _as_uuid(payload.get("userID")
                                 or payload.get("user_id"), "userID")
            amount = _as_decimal(payload.get("amount"), "amount")
            idempotency_key = payload.get(
                "idempotencyKey") or payload.get("idempotency_key")

            response_payload, status_code = _process_payment_initiation(
                hold_uuid,
                user_uuid,
                amount,
                idempotency_key=idempotency_key,
            )
            return _api_response(response_payload, status_code)
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error while creating payment: %s", error)
            return _api_response({"error": "Failed to create payment"}, 500)

    @app.post("/payments/refund/<booking_id>")
    def payments_refund(booking_id: str):
        try:
            _require_internal_auth()
            _require_supabase()
            _require_stripe()
            payload = _get_json_payload()
            transaction, _ = _resolve_booking_transaction(booking_id)
            requested_refund_amount = (
                _as_decimal(payload.get("refundAmount"), "refundAmount")
                if payload.get("refundAmount") is not None
                else None
            )
            reason = payload.get("reason")

            result = _execute_refund(
                transaction, requested_refund_amount, reason)
            return _api_response(result, 200)
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error while processing refund: %s", error)
            return _api_response({"error": "Failed to process refund"}, 500)

    @app.post("/payments/refund")
    def payments_refund_alias():
        try:
            payload = _get_json_payload()
            booking_id = (
                payload.get("bookingID")
                or payload.get("bookingId")
                or payload.get("transactionID")
                or payload.get("transactionId")
                or payload.get("holdID")
                or payload.get("holdId")
            )
            if not booking_id:
                raise ValidationError("bookingID or transactionID is required")
            return payments_refund(str(booking_id))
        except ApiError as error:
            return _handle_api_error(error)
        except Exception as error:
            logger.exception(
                "Unexpected error while processing refund alias: %s", error)
            return _api_response({"error": "Failed to process refund"}, 500)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Unhandled error: %s", error)
        return jsonify({"error": "Internal server error"}), 500

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
