from __future__ import annotations

import hmac
import logging
import os
import uuid
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Blueprint, Flask, Response, current_app, jsonify, request
from flask_cors import CORS

from shared.mq import publish_json

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

cancellation_bp = Blueprint("cancellation_orchestrator", __name__)

NOTIFICATION_ROUTING_KEY = "notification.send"


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 400, details: Any | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


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
    def __init__(self, message: str, details: Any | None = None):
        super().__init__(message, 503, details)


class BaseConfig:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "cancellation-orchestrator")
    PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:5000")
    INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:5000")
    WAITLIST_SERVICE_URL = os.getenv("WAITLIST_SERVICE_URL", "http://waitlist-service:5000")
    USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:5000")
    EVENT_SERVICE_URL = os.getenv("EVENT_SERVICE_URL", "http://event-service:5000")
    OUTSYSTEMS_BASE_URL = os.getenv("OUTSYSTEMS_BASE_URL", "")
    OUTSYSTEMS_API_KEY = os.getenv("OUTSYSTEMS_API_KEY", "")
    OUTSYSTEMS_API_KEY_HEADER = os.getenv("OUTSYSTEMS_API_KEY_HEADER", "X-API-Key")
    INTERNAL_AUTH_HEADER = os.getenv("INTERNAL_AUTH_HEADER", "X-Internal-Token")
    INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "")
    REQUEST_TIMEOUT_SECONDS = float(os.getenv("CANCELLATION_TIMEOUT_SECONDS", "5.0"))
    NOTIFICATION_ROUTING_KEY = os.getenv("NOTIFICATION_TOPIC_ROUTING_KEY", NOTIFICATION_ROUTING_KEY)


def _api_response(payload: dict[str, Any], status_code: int = 200):
    return jsonify(payload), status_code


def _json_error(message: str, status_code: int, details: Any | None = None):
    payload: dict[str, Any] = {"error": message}
    if details is not None:
        payload["details"] = details
    return _api_response(payload, status_code)


def _extract_dependency_message(payload: dict[str, Any] | None, fallback: str) -> str:
    if not payload:
        return fallback

    for key in ("error", "message", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return fallback


def _raise_dependency_http_error(
    *,
    service: str,
    status_code: int,
    payload: dict[str, Any] | None,
    fallback_message: str,
    not_found_message: str | None = None,
) -> None:
    message = _extract_dependency_message(payload, fallback_message)

    if status_code == 404:
        raise NotFoundError(not_found_message or message)

    if status_code == 409:
        raise ConflictError(message)

    if status_code in {400, 422}:
        raise ValidationError(message)

    if status_code in {401, 403}:
        raise ApiError(message, status_code)

    raise DependencyError(
        message,
        details={
            "dependency": service,
            "statusCode": status_code,
            "response": payload,
        },
    )


def _parse_uuid(value: Any, field_name: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except Exception as error:
        raise ValidationError(f"{field_name} must be a valid UUID") from error


def _parse_non_empty_string(value: Any, field_name: str) -> str:
    parsed = str(value or "").strip()
    if not parsed:
        raise ValidationError(f"{field_name} is required")
    return parsed


def _get_json_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValidationError("JSON body must be an object")
    return payload


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _internal_headers() -> dict[str, str]:
    token = str(current_app.config.get("INTERNAL_SERVICE_TOKEN") or "").strip()
    if not token:
        return {}

    header_name = str(current_app.config.get("INTERNAL_AUTH_HEADER") or "X-Internal-Token").strip()
    return {header_name: token}


def _outsystems_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    api_key = str(current_app.config.get("OUTSYSTEMS_API_KEY") or "").strip()
    if api_key:
        header_name = str(current_app.config.get("OUTSYSTEMS_API_KEY_HEADER") or "X-API-Key").strip()
        headers[header_name] = api_key
    return headers


def _authorize_internal_request() -> None:
    expected_token = str(current_app.config.get("INTERNAL_SERVICE_TOKEN") or "").strip()
    if not expected_token:
        raise DependencyError("INTERNAL_SERVICE_TOKEN is not configured", details={"dependency": "configuration"})

    header_name = str(current_app.config.get("INTERNAL_AUTH_HEADER") or "X-Internal-Token").strip()
    provided_token = request.headers.get(header_name, "")

    if not hmac.compare_digest(provided_token, expected_token):
        raise ApiError("Unauthorized", 401)


def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | None]:
    timeout = float(current_app.config.get("REQUEST_TIMEOUT_SECONDS", 5.0))
    try:
        response = requests.request(method=method, url=url, headers=headers or {}, json=payload, timeout=timeout)
    except requests.RequestException as error:
        raise DependencyError(
            "Dependency request failed",
            details={"url": url, "error": str(error)},
        ) from error

    if response.status_code == 204 or not response.text:
        return response.status_code, None

    try:
        parsed = response.json()
    except ValueError:
        parsed = {"raw": response.text}

    if isinstance(parsed, dict):
        return response.status_code, parsed

    return response.status_code, {"data": parsed}


def _extract_email_from_user(user_id: str) -> str:
    user_url = _join_url(current_app.config["USER_SERVICE_URL"], f"/user/{user_id}")
    status_code, payload = _request_json("GET", user_url, headers=_internal_headers())
    if status_code != 200 or not payload:
        _raise_dependency_http_error(
            service="user-service",
            status_code=status_code,
            payload=payload,
            fallback_message="Failed to resolve user email",
            not_found_message="User not found",
        )

    email = payload.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise DependencyError("User email missing or invalid", details={"dependency": "user-service"})
    return email


def _extract_event_name(event_id: str) -> str | None:
    event_url = _join_url(current_app.config["EVENT_SERVICE_URL"], f"/event/{event_id}")
    status_code, payload = _request_json("GET", event_url, headers=_internal_headers())
    if status_code != 200 or not payload:
        return None
    name = payload.get("name")
    return str(name) if name else None


def _fetch_payment_verification(booking_id: str, *, strict_policy: bool = False) -> dict[str, Any]:
    path = f"/payments/verify-policy/{booking_id}" if strict_policy else f"/payments/verify/{booking_id}"
    url = _join_url(current_app.config["PAYMENT_SERVICE_URL"], path)
    status_code, payload = _request_json("GET", url, headers=_internal_headers())

    if status_code != 200 or not payload:
        _raise_dependency_http_error(
            service="payment-service",
            status_code=status_code,
            payload=payload,
            fallback_message="Payment verification failed",
            not_found_message="Booking payment record not found",
        )

    return payload


def _update_payment_status(
    booking_id: str,
    status: str,
    *,
    refund_amount: Any | None = None,
    reason: str | None = None,
    cancellation_status: str | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {"status": status}
    if refund_amount is not None:
        payload["refundAmount"] = refund_amount
    if reason:
        payload["reason"] = reason
    if cancellation_status:
        payload["cancellationStatus"] = cancellation_status

    url = _join_url(current_app.config["PAYMENT_SERVICE_URL"], f"/payments/status/{booking_id}")
    status_code, body = _request_json("PUT", url, headers=_internal_headers(), payload=payload)
    if status_code not in {200, 201}:
        raise DependencyError("Failed to update payment status", details={"dependency": "payment-service"})
    return body


def _mark_payment_failed(booking_id: str, reason: str) -> None:
    url = _join_url(current_app.config["PAYMENT_SERVICE_URL"], "/payments/status/fail")
    payload = {"bookingID": booking_id, "status": "REFUND_FAILED", "reason": reason}
    status_code, _ = _request_json("PUT", url, headers=_internal_headers(), payload=payload)
    if status_code not in {200, 201}:
        raise DependencyError("Failed to apply refund failure compensation", details={"dependency": "payment-service"})


def _request_refund(booking_id: str, reason: str | None) -> dict[str, Any]:
    url = _join_url(current_app.config["PAYMENT_SERVICE_URL"], f"/payments/refund/{booking_id}")
    payload = {"reason": reason} if reason else {}
    status_code, body = _request_json("POST", url, headers=_internal_headers(), payload=payload)

    if status_code in {200, 201} and body:
        return body

    if status_code == 409 and body and "already" in str(body.get("error", "")).lower():
        return {"status": "already_refunded"}

    error_message = "Refund request failed"
    if body and isinstance(body.get("error"), str):
        error_message = body["error"]

    raise DependencyError(error_message, details={"dependency": "payment-service", "statusCode": status_code})


def _fetch_inventory_hold(hold_id: str) -> dict[str, Any]:
    url = _join_url(current_app.config["INVENTORY_SERVICE_URL"], f"/inventory/hold/{hold_id}")
    status_code, payload = _request_json("GET", url, headers=_internal_headers())
    if status_code == 404:
        raise NotFoundError("Hold not found")
    if status_code != 200 or not payload:
        raise DependencyError("Failed to load hold details", details={"dependency": "inventory-service"})
    return payload


def _release_hold(hold_id: str) -> dict[str, Any] | None:
    url = _join_url(current_app.config["INVENTORY_SERVICE_URL"], f"/inventory/hold/{hold_id}/release")
    status_code, payload = _request_json(
        "PUT",
        url,
        headers=_internal_headers(),
        payload={"reason": "CANCELLATION"},
    )

    if status_code == 404:
        raise NotFoundError("Hold not found for release")
    if status_code not in {200, 409}:
        raise DependencyError("Failed to release hold", details={"dependency": "inventory-service"})
    return payload


def _create_waitlist_hold(event_id: str, user_id: str, seat_category: str) -> dict[str, Any]:
    url = _join_url(current_app.config["INVENTORY_SERVICE_URL"], "/inventory/hold")
    payload = {
        "eventID": event_id,
        "userID": user_id,
        "seatCategory": seat_category,
        "qty": 1,
        "fromWaitlist": True,
    }
    status_code, body = _request_json("POST", url, headers=_internal_headers(), payload=payload)
    if status_code not in {200, 201} or not body:
        _raise_dependency_http_error(
            service="inventory-service",
            status_code=status_code,
            payload=body,
            fallback_message="Failed to create waitlist hold",
        )
    return body


def _confirm_hold(hold_id: str) -> dict[str, Any]:
    url = _join_url(current_app.config["INVENTORY_SERVICE_URL"], f"/inventory/hold/{hold_id}/confirm")
    status_code, body = _request_json("PUT", url, headers=_internal_headers(), payload={})

    if status_code in {200, 201} and body:
        return body

    if status_code == 409:
        latest_hold = _fetch_inventory_hold(hold_id)
        if str(latest_hold.get("holdStatus") or "").upper() == "CONFIRMED":
            return latest_hold

    _raise_dependency_http_error(
        service="inventory-service",
        status_code=status_code,
        payload=body,
        fallback_message="Failed to confirm waitlist hold",
    )
    return body


def _fetch_waitlist_status(hold_id: str) -> dict[str, Any]:
    url = _join_url(current_app.config["WAITLIST_SERVICE_URL"], f"/waitlist/status/{hold_id}")
    status_code, payload = _request_json("GET", url, headers=_internal_headers())

    if status_code == 404:
        return {"hasWaitlist": False, "entries": []}

    if status_code != 200 or not payload:
        raise DependencyError("Failed to query waitlist", details={"dependency": "waitlist-service"})

    return payload


def _mark_waitlist_offer(waitlist_id: str, hold_id: str) -> None:
    url = _join_url(current_app.config["WAITLIST_SERVICE_URL"], f"/waitlist/{waitlist_id}/offer")
    status_code, payload = _request_json("PUT", url, headers=_internal_headers(), payload={"holdID": hold_id})
    if status_code not in {200, 201}:
        _raise_dependency_http_error(
            service="waitlist-service",
            status_code=status_code,
            payload=payload,
            fallback_message="Failed to mark waitlist offer",
        )


def _fetch_waitlist_entry(waitlist_id: str) -> dict[str, Any]:
    url = _join_url(current_app.config["WAITLIST_SERVICE_URL"], f"/waitlist/{waitlist_id}")
    status_code, payload = _request_json("GET", url, headers=_internal_headers())
    if status_code != 200 or not payload:
        _raise_dependency_http_error(
            service="waitlist-service",
            status_code=status_code,
            payload=payload,
            fallback_message="Failed to load waitlist entry",
            not_found_message="Waitlist entry not found",
        )
    return payload


def _mark_waitlist_confirm(waitlist_id: str, hold_id: str) -> None:
    url = _join_url(current_app.config["WAITLIST_SERVICE_URL"], f"/waitlist/{waitlist_id}/confirm")
    status_code, payload = _request_json("PUT", url, headers=_internal_headers(), payload={"holdID": hold_id})
    if status_code in {200, 201}:
        return

    if status_code == 409:
        waitlist_entry = _fetch_waitlist_entry(waitlist_id)
        status = str(waitlist_entry.get("status") or "").upper()
        existing_hold_id = _parse_uuid(waitlist_entry.get("holdID"), "waitlist.holdID")
        if status == "CONFIRMED" and existing_hold_id == hold_id:
            return

    _raise_dependency_http_error(
        service="waitlist-service",
        status_code=status_code,
        payload=payload,
        fallback_message="Failed to confirm waitlist entry",
    )


def _create_payment_for_hold(hold_id: str, user_id: str, amount: Any) -> dict[str, Any]:
    url = _join_url(current_app.config["PAYMENT_SERVICE_URL"], "/payments/create")
    payload = {"holdID": hold_id, "userID": user_id, "amount": amount}
    status_code, body = _request_json("POST", url, headers=_internal_headers(), payload=payload)
    if status_code not in {200, 201} or not body:
        _raise_dependency_http_error(
            service="payment-service",
            status_code=status_code,
            payload=body,
            fallback_message="Failed to initialize waitlist payment",
        )
    return body


def _fetch_payment_for_hold(hold_id: str) -> dict[str, Any]:
    url = _join_url(current_app.config["PAYMENT_SERVICE_URL"], f"/payment/hold/{hold_id}")
    status_code, body = _request_json("GET", url, headers=_internal_headers())
    if status_code != 200 or not body:
        _raise_dependency_http_error(
            service="payment-service",
            status_code=status_code,
            payload=body,
            fallback_message="Failed to resolve payment status for hold",
            not_found_message="Payment transaction for hold not found",
        )
    return body


def _fetch_eticket_by_hold(hold_id: str) -> dict[str, Any]:
    base_url = str(current_app.config.get("OUTSYSTEMS_BASE_URL") or "").strip()
    if not base_url:
        raise DependencyError("OUTSYSTEMS_BASE_URL is not configured", details={"dependency": "outsystems"})

    url = _join_url(base_url, f"/eticket/hold/{hold_id}")
    status_code, payload = _request_json("GET", url, headers=_outsystems_headers())
    if status_code == 404:
        raise NotFoundError("E-ticket record not found for hold")
    if status_code != 200 or not payload:
        raise DependencyError("Failed to resolve e-ticket for hold", details={"dependency": "outsystems"})
    return payload


def _validate_ticket_ownership(ticket_id: str, user_id: str) -> None:
    base_url = str(current_app.config.get("OUTSYSTEMS_BASE_URL") or "").strip()
    if not base_url:
        raise DependencyError("OUTSYSTEMS_BASE_URL is not configured", details={"dependency": "outsystems"})

    url = _join_url(base_url, f"/eticket/validate?ticketID={ticket_id}&userID={user_id}")
    status_code, payload = _request_json("GET", url, headers=_outsystems_headers())

    if status_code == 404:
        raise NotFoundError("Ticket not found")
    if status_code == 403:
        raise ConflictError("Ticket ownership mismatch")
    if status_code == 409:
        raise ConflictError("Ticket is not in a cancellable status")
    if status_code != 200 or not payload:
        raise DependencyError("Failed to validate ticket ownership", details={"dependency": "outsystems"})

    if payload.get("valid") is False:
        raise ConflictError(f"Ticket validation failed: {payload.get('reason') or 'invalid ownership'}")


def _update_eticket_status(ticket_id: str, status: str, correlation_id: str) -> None:
    base_url = str(current_app.config.get("OUTSYSTEMS_BASE_URL") or "").strip()
    if not base_url:
        raise DependencyError("OUTSYSTEMS_BASE_URL is not configured", details={"dependency": "outsystems"})

    url = _join_url(base_url, f"/etickets/status/{ticket_id}")
    payload = {"status": status, "correlationID": correlation_id}
    status_code, _ = _request_json("PUT", url, headers=_outsystems_headers(), payload=payload)

    if status_code not in {200, 201}:
        raise DependencyError("Failed to update e-ticket status", details={"dependency": "outsystems"})


def _update_etickets_transfer(
    old_ticket_id: str,
    new_owner_user_id: str,
    new_hold_id: str,
    new_seat_id: str | None,
    new_seat_number: str | None,
    new_transaction_id: str | None,
    correlation_id: str,
) -> dict[str, Any]:
    base_url = str(current_app.config.get("OUTSYSTEMS_BASE_URL") or "").strip()
    if not base_url:
        raise DependencyError("OUTSYSTEMS_BASE_URL is not configured", details={"dependency": "outsystems"})

    url = _join_url(base_url, "/etickets/update")
    payload = {
        "oldTicketID": old_ticket_id,
        "newOwnerUserID": new_owner_user_id,
        "newHoldID": new_hold_id,
        "newSeatID": new_seat_id,
        "newSeatNumber": new_seat_number,
        "operation": "TRANSFER_AND_REISSUE",
        "correlationID": correlation_id,
        "newTransactionID": new_transaction_id,
    }
    status_code, body = _request_json("POST", url, headers=_outsystems_headers(), payload=payload)
    if status_code not in {200, 201} or not body:
        _raise_dependency_http_error(
            service="outsystems",
            status_code=status_code,
            payload=body,
            fallback_message="Failed to transfer/reissue e-ticket",
        )
    return body


def _publish_notification(event_type: str, payload: dict[str, Any]) -> None:
    message = {"type": event_type, **payload}
    try:
        publish_json(
            routing_key=current_app.config.get("NOTIFICATION_ROUTING_KEY", NOTIFICATION_ROUTING_KEY),
            payload=message,
        )
    except Exception as error:
        raise DependencyError("Failed to publish notification event", details={"error": str(error)}) from error


def _derive_booking_id_from_payload(payload: dict[str, Any]) -> str:
    booking_id = payload.get("bookingID") or payload.get("bookingId")
    if not booking_id:
        raise ValidationError("bookingID is required")
    return _parse_uuid(booking_id, "bookingID")


def _derive_user_id_from_payload(payload: dict[str, Any]) -> str:
    user_id = payload.get("userID") or payload.get("userId")
    if not user_id:
        raise ValidationError("userID is required")
    return _parse_uuid(user_id, "userID")


def _derive_correlation_id(payload: dict[str, Any]) -> str:
    raw = payload.get("correlationID") or request.headers.get("X-Correlation-ID")
    if raw:
        return _parse_uuid(raw, "correlationID")
    return str(uuid.uuid4())


def _build_refund_success_payload(
    booking_id: str,
    user_id: str,
    event_id: str,
    event_name: str | None,
    old_hold_id: str,
    refund_amount: Any,
    waitlist_status: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    has_waitlist = bool(waitlist_status.get("hasWaitlist"))
    entries = waitlist_status.get("entries") or []
    next_user = waitlist_status.get("nextUser") or (entries[0] if entries else None)

    if not has_waitlist or not next_user:
        _publish_notification(
            "TICKET_AVAILABLE_PUBLIC",
            {
                "email": _extract_email_from_user(user_id),
                "bookingID": booking_id,
                "eventID": event_id,
                "eventName": event_name,
                "holdID": old_hold_id,
                "refundAmount": refund_amount,
            },
        )
        return (
            {
                "status": "REFUND_COMPLETED",
                "bookingID": booking_id,
                "eventID": event_id,
                "eventName": event_name,
                "waitlistReallocation": "PUBLIC_INVENTORY",
                "refundAmount": refund_amount,
            },
            200,
        )

    waitlist_id = _parse_uuid(next_user.get("waitlistID"), "waitlistID")
    next_user_id = _parse_uuid(next_user.get("userID"), "nextUser.userID")
    seat_category = next_user.get("seatCategory") or waitlist_status.get("seatCategory")
    if not seat_category:
        raise DependencyError("Waitlist status did not include seatCategory", details={"dependency": "waitlist-service"})

    new_hold = _create_waitlist_hold(event_id, next_user_id, str(seat_category))
    new_hold_id = _parse_uuid(new_hold.get("holdID"), "holdID")
    _mark_waitlist_offer(waitlist_id, new_hold_id)

    payment_init = _create_payment_for_hold(new_hold_id, next_user_id, new_hold.get("amount"))
    next_user_email = _extract_email_from_user(next_user_id)

    _publish_notification(
        "SEAT_AVAILABLE",
        {
            "email": next_user_email,
            "eventName": event_name,
            "holdID": new_hold_id,
            "holdExpiry": new_hold.get("holdExpiry"),
            "paymentURL": f"/waitlist/confirm/{new_hold_id}",
            "waitlistID": waitlist_id,
            "bookingID": booking_id,
            "correlationID": payment_init.get("transactionID"),
        },
    )

    return (
        {
            "status": "REALLOCATION_PENDING",
            "bookingID": booking_id,
            "eventID": event_id,
            "eventName": event_name,
            "refundAmount": refund_amount,
            "waitlistID": waitlist_id,
            "nextUserID": next_user_id,
            "newHoldID": new_hold_id,
            "payment": {
                "paymentIntentID": payment_init.get("paymentIntentID"),
                "clientSecret": payment_init.get("clientSecret"),
                "amount": payment_init.get("amount"),
                "currency": payment_init.get("currency"),
            },
        },
        202,
    )


def _process_cancellation(booking_id: str, user_id: str, reason: str | None, correlation_id: str):
    verification = _fetch_payment_verification(booking_id, strict_policy=False)

    owner_user_id = _parse_uuid(verification.get("userID"), "payment.userID")
    if owner_user_id != user_id:
        raise ConflictError("Booking does not belong to requesting user")

    payment_status = str(verification.get("paymentStatus") or "").upper()
    if payment_status == "REFUND_PENDING":
        raise ConflictError("Refund is already in progress")

    if payment_status == "REFUND_FAILED":
        raise ConflictError("Refund previously failed and needs manual follow-up")

    old_hold_id = _parse_uuid(verification.get("holdID"), "holdID")
    event_id = _parse_uuid(verification.get("eventID"), "eventID")

    email = _extract_email_from_user(user_id)
    event_name = _extract_event_name(event_id)

    if not bool(verification.get("withinPolicy")):
        _publish_notification(
            "CANCELLATION_DENIED",
            {
                "email": email,
                "bookingID": booking_id,
                "userID": user_id,
                "eventID": event_id,
                "eventName": event_name,
                "reason": "Not eligible under 48-hour cancellation policy",
                "correlationID": correlation_id,
            },
        )
        return (
            {
                "status": "DENIED",
                "bookingID": booking_id,
                "withinPolicy": False,
                "reason": "Not eligible under 48-hour cancellation policy",
            },
            409,
        )

    if payment_status == "REFUND_SUCCEEDED":
        return (
            {
                "status": "ALREADY_REFUNDED",
                "bookingID": booking_id,
                "holdID": old_hold_id,
            },
            200,
        )

    old_ticket = _fetch_eticket_by_hold(old_hold_id)
    old_ticket_id = _parse_non_empty_string(old_ticket.get("ticketID"), "ticketID")
    _validate_ticket_ownership(old_ticket_id, user_id)

    _update_payment_status(booking_id, "PROCESSING_REFUND", reason=reason)

    _publish_notification(
        "CANCELLATION_CONFIRMED",
        {
            "email": email,
            "bookingID": booking_id,
            "userID": user_id,
            "eventID": event_id,
            "eventName": event_name,
            "correlationID": correlation_id,
        },
    )

    try:
        refund_result = _request_refund(booking_id, reason)
    except ApiError as error:
        _mark_payment_failed(booking_id, error.message)
        try:
            _update_eticket_status(old_ticket_id, "CANCELLATION_IN_PROGRESS", correlation_id)
        except ApiError as eticket_error:
            logger.warning("Failed to set CANCELLATION_IN_PROGRESS: %s", eticket_error.message)

        _publish_notification(
            "REFUND_ERROR",
            {
                "email": email,
                "bookingID": booking_id,
                "userID": user_id,
                "eventID": event_id,
                "eventName": event_name,
                "errorDetail": error.message,
                "nextSteps": "Cancellation remains in progress. Manual follow-up required.",
                "correlationID": correlation_id,
            },
        )

        return (
            {
                "status": "CANCELLATION_IN_PROGRESS",
                "bookingID": booking_id,
                "reason": error.message,
                "nextSteps": "Manual follow-up required",
            },
            502,
        )

    refund_amount = refund_result.get("refundAmount") or verification.get("eligibleRefundAmount")

    _update_eticket_status(old_ticket_id, "CANCELLED", correlation_id)
    _release_hold(old_hold_id)

    _publish_notification(
        "REFUND_SUCCESSFUL",
        {
            "email": email,
            "bookingID": booking_id,
            "userID": user_id,
            "eventID": event_id,
            "eventName": event_name,
            "refundAmount": refund_amount,
            "correlationID": correlation_id,
        },
    )

    waitlist_status = _fetch_waitlist_status(old_hold_id)
    return _build_refund_success_payload(
        booking_id,
        user_id,
        event_id,
        event_name,
        old_hold_id,
        refund_amount,
        waitlist_status,
    )


def _process_reallocation_confirmation(payload: dict[str, Any]):
    booking_id = _derive_booking_id_from_payload(payload)
    new_hold_id = _parse_uuid(payload.get("newHoldID"), "newHoldID")
    waitlist_id = _parse_uuid(payload.get("waitlistID"), "waitlistID")
    correlation_id = _derive_correlation_id(payload)

    waitlist_entry = _fetch_waitlist_entry(waitlist_id)
    waitlist_user_id = _parse_uuid(waitlist_entry.get("userID"), "waitlist.userID")
    waitlist_hold_id = _parse_uuid(waitlist_entry.get("holdID"), "waitlist.holdID")
    waitlist_status = str(waitlist_entry.get("status") or "").upper()

    if waitlist_hold_id != new_hold_id:
        raise ConflictError("waitlist entry is not associated with newHoldID")

    if waitlist_status == "CONFIRMED":
        raise ConflictError("Waitlist entry is already confirmed")

    if waitlist_status != "HOLD_OFFERED":
        raise ConflictError("Waitlist entry is not eligible for confirmation")

    provided_new_user_id = payload.get("newUserID")
    if provided_new_user_id is not None:
        requested_user_id = _parse_uuid(provided_new_user_id, "newUserID")
        if requested_user_id != waitlist_user_id:
            raise ConflictError("newUserID does not match the waitlist entry owner")

    new_user_id = waitlist_user_id

    payment_for_new_hold = _fetch_payment_for_hold(new_hold_id)
    payment_status = str(payment_for_new_hold.get("paymentStatus") or "").upper()
    if payment_status != "SUCCEEDED":
        raise ConflictError("Waitlist payment is not completed")

    _confirm_hold(new_hold_id)

    original_verification = _fetch_payment_verification(booking_id, strict_policy=False)
    original_hold_id = _parse_uuid(original_verification.get("holdID"), "holdID")
    original_ticket = _fetch_eticket_by_hold(original_hold_id)
    old_ticket_id = _parse_non_empty_string(original_ticket.get("ticketID"), "ticketID")

    new_hold_snapshot = _fetch_inventory_hold(new_hold_id)

    try:
        transfer_result = _update_etickets_transfer(
            old_ticket_id=old_ticket_id,
            new_owner_user_id=new_user_id,
            new_hold_id=new_hold_id,
            new_seat_id=new_hold_snapshot.get("seatID"),
            new_seat_number=new_hold_snapshot.get("seatNumber"),
            new_transaction_id=payment_for_new_hold.get("transactionID"),
            correlation_id=correlation_id,
        )
    except ApiError as error:
        logger.warning(
            "Reallocation transfer failed after hold confirmation. bookingID=%s waitlistID=%s newHoldID=%s error=%s",
            booking_id,
            waitlist_id,
            new_hold_id,
            error.message,
        )
        return (
            {
                "status": "REALLOCATION_RECONCILIATION_REQUIRED",
                "bookingID": booking_id,
                "waitlistID": waitlist_id,
                "newHoldID": new_hold_id,
                "reason": error.message,
                "nextSteps": "Retry reallocation confirmation or follow up manually",
            },
            502,
        )

    _mark_waitlist_confirm(waitlist_id, new_hold_id)

    new_ticket_id = transfer_result.get("newTicketID") or transfer_result.get("ticketID") or old_ticket_id
    user_email = _extract_email_from_user(new_user_id)
    event_name = _extract_event_name(_parse_uuid(original_verification.get("eventID"), "eventID"))

    _publish_notification(
        "TICKET_CONFIRMATION",
        {
            "email": user_email,
            "bookingID": booking_id,
            "newUserID": new_user_id,
            "ticketID": new_ticket_id,
            "seatNumber": new_hold_snapshot.get("seatNumber"),
            "eventName": event_name,
            "correlationID": correlation_id,
        },
    )

    return (
        {
            "status": "REALLOCATION_CONFIRMED",
            "bookingID": booking_id,
            "waitlistID": waitlist_id,
            "newHoldID": new_hold_id,
            "newUserID": new_user_id,
            "ticketID": new_ticket_id,
            "seatNumber": new_hold_snapshot.get("seatNumber"),
        },
        200,
    )


@cancellation_bp.get("/health")
def health():
    return _api_response(
        {
            "status": "ok",
            "service": current_app.config.get("SERVICE_NAME", "cancellation-orchestrator"),
            "dependencies": {
                "paymentConfigured": bool(current_app.config.get("PAYMENT_SERVICE_URL")),
                "inventoryConfigured": bool(current_app.config.get("INVENTORY_SERVICE_URL")),
                "waitlistConfigured": bool(current_app.config.get("WAITLIST_SERVICE_URL")),
                "userConfigured": bool(current_app.config.get("USER_SERVICE_URL")),
                "outsystemsConfigured": bool(str(current_app.config.get("OUTSYSTEMS_BASE_URL") or "").strip()),
            },
        }
    )


@cancellation_bp.post("/orchestrator/cancellation")
def orchestrate_cancellation():
    try:
        payload = _get_json_payload()
        booking_id = _derive_booking_id_from_payload(payload)
        user_id = _derive_user_id_from_payload(payload)
        reason = payload.get("reason")
        if reason is not None:
            reason = str(reason)
        correlation_id = _derive_correlation_id(payload)
        body, status_code = _process_cancellation(booking_id, user_id, reason, correlation_id)
        return _api_response(body, status_code)
    except ApiError as error:
        return _json_error(error.message, error.status_code, error.details)
    except Exception as error:
        logger.exception("Unexpected cancellation orchestration error: %s", error)
        return _json_error("Failed to orchestrate cancellation", 500)


@cancellation_bp.post("/bookings/cancel/<booking_id>")
def orchestrate_cancellation_alias(booking_id: str):
    try:
        payload = _get_json_payload()
        payload.setdefault("bookingID", booking_id)
        user_id = _derive_user_id_from_payload(payload)
        reason = payload.get("reason")
        if reason is not None:
            reason = str(reason)
        correlation_id = _derive_correlation_id(payload)
        parsed_booking_id = _derive_booking_id_from_payload(payload)
        body, status_code = _process_cancellation(parsed_booking_id, user_id, reason, correlation_id)
        return _api_response(body, status_code)
    except ApiError as error:
        return _json_error(error.message, error.status_code, error.details)
    except Exception as error:
        logger.exception("Unexpected cancellation alias error: %s", error)
        return _json_error("Failed to orchestrate cancellation", 500)


@cancellation_bp.post("/orchestrator/cancellation/reallocation/confirm")
def confirm_reallocation():
    try:
        _authorize_internal_request()
        payload = _get_json_payload()
        body, status_code = _process_reallocation_confirmation(payload)
        return _api_response(body, status_code)
    except ApiError as error:
        return _json_error(error.message, error.status_code, error.details)
    except Exception as error:
        logger.exception("Unexpected reallocation confirmation error: %s", error)
        return _json_error("Failed to confirm reallocation", 500)


def _build_openapi_spec(base_url: str) -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "TicketBlitz Cancellation Orchestrator API",
            "version": "1.0.0",
            "description": "Scenario 3 cancellation and reallocation orchestration endpoints.",
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health check",
                    "responses": {
                        "200": {
                            "description": "Service health",
                        }
                    },
                }
            },
            "/orchestrator/cancellation": {
                "post": {
                    "summary": "Start cancellation and refund orchestration",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["bookingID", "userID"],
                                    "properties": {
                                        "bookingID": {"type": "string", "format": "uuid"},
                                        "userID": {"type": "string", "format": "uuid"},
                                        "reason": {"type": "string"},
                                        "correlationID": {"type": "string", "format": "uuid"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Cancellation completed"},
                        "202": {"description": "Reallocation payment pending"},
                        "409": {"description": "Policy denied or conflict"},
                        "502": {"description": "Refund failed with compensation"},
                    },
                }
            },
            "/bookings/cancel/{booking_id}": {
                "post": {
                    "summary": "Alias endpoint for Kong-facing cancellation path",
                    "parameters": [
                        {
                            "name": "booking_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["userID"],
                                    "properties": {
                                        "userID": {"type": "string", "format": "uuid"},
                                        "reason": {"type": "string"},
                                        "correlationID": {"type": "string", "format": "uuid"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Cancellation completed"},
                        "202": {"description": "Reallocation payment pending"},
                    },
                }
            },
            "/orchestrator/cancellation/reallocation/confirm": {
                "post": {
                    "summary": "Finalize waitlist reallocation after new payment",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["bookingID", "newHoldID", "waitlistID"],
                                    "properties": {
                                        "bookingID": {"type": "string", "format": "uuid"},
                                        "newHoldID": {"type": "string", "format": "uuid"},
                                        "waitlistID": {"type": "string", "format": "uuid"},
                                        "newUserID": {"type": "string", "format": "uuid"},
                                        "correlationID": {"type": "string", "format": "uuid"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Reallocation confirmed"},
                        "409": {"description": "Payment not completed"},
                    },
                }
            },
        },
    }


def _build_swagger_ui_html(openapi_url: str) -> str:
    return """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>TicketBlitz Cancellation Orchestrator API Docs</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui.css\" />
    <style>
      body {{ margin: 0; background: #fafafa; }}
      #swagger-ui {{ max-width: 1180px; margin: 0 auto; }}
    </style>
  </head>
  <body>
    <div id=\"swagger-ui\"></div>
    <script src=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js\"></script>
    <script>
      window.ui = SwaggerUIBundle({{
        url: '{openapi_url}',
        dom_id: '#swagger-ui',
        deepLinking: true,
        displayRequestDuration: true,
      }});
    </script>
  </body>
</html>
""".format(openapi_url=openapi_url)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def _not_found(_error):
        return _json_error("Not found", 404)

    @app.errorhandler(405)
    def _method_not_allowed(_error):
        return _json_error("Method not allowed", 405)

    @app.errorhandler(500)
    def _internal_error(_error):
        return _json_error("Internal server error", 500)


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    load_dotenv(override=False)

    app = Flask(__name__)
    app.config.from_object(BaseConfig)

    if test_config:
        app.config.update(test_config)

    CORS(app)
    app.register_blueprint(cancellation_bp)

    @app.get("/openapi.json")
    def openapi_json():
        return jsonify(_build_openapi_spec(request.host_url.rstrip("/")))

    @app.get("/docs")
    def docs():
        return Response(_build_swagger_ui_html("/openapi.json"), mimetype="text/html")

    _register_error_handlers(app)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
