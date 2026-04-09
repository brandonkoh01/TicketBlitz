from __future__ import annotations

import hmac
import logging
import os
import uuid
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Blueprint, Flask, current_app, jsonify, request
from flask_cors import CORS

from shared.mq import publish_json
from shared.openapi import register_openapi_routes
from shared.swagger_specs import get_service_swagger_spec

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

cancellation_bp = Blueprint("cancellation_orchestrator", __name__)

NOTIFICATION_ROUTING_KEY = "notification.send"


def _is_production_env() -> bool:
    for name in ("APP_ENV", "ENVIRONMENT", "FLASK_ENV"):
        value = str(os.getenv(name, "")).strip().lower()
        if value in {"prod", "production"}:
            return True
    return False


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
    BOOKING_STATUS_SERVICE_URL = os.getenv("BOOKING_STATUS_SERVICE_URL", "http://booking-status-service:5000")
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
    WAITLIST_PAYMENT_URL_TEMPLATE = os.getenv("WAITLIST_PAYMENT_URL_TEMPLATE", "/waitlist/confirm/{holdID}")
    FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "" if _is_production_env() else "http://localhost:5173")


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


def _build_waitlist_payment_url(hold_id: str) -> str:
    template = str(current_app.config.get("WAITLIST_PAYMENT_URL_TEMPLATE") or "").strip()
    if not template:
        template = "/waitlist/confirm/{holdID}"

    if "{holdID}" in template:
        payment_url = template.replace("{holdID}", hold_id)
    else:
        payment_url = f"{template.rstrip('/')}/{hold_id}"

    if payment_url.startswith("/"):
        frontend_base_url = str(current_app.config.get("FRONTEND_BASE_URL") or "").strip().rstrip("/")
        if frontend_base_url:
            return f"{frontend_base_url}{payment_url}"

    return payment_url


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


def _fetch_public_announcement_emails() -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()
    page = 1
    page_size = 100
    max_recipients = 5000

    while len(recipients) < max_recipients:
        users_url = _join_url(
            current_app.config["USER_SERVICE_URL"],
            f"/users?page={page}&pageSize={page_size}",
        )
        status_code, payload = _request_json("GET", users_url, headers=_internal_headers())

        if status_code != 200 or not payload:
            _raise_dependency_http_error(
                service="user-service",
                status_code=status_code,
                payload=payload,
                fallback_message="Failed to resolve public announcement recipients",
            )

        users = payload.get("users")
        if not isinstance(users, list):
            users = []

        for user in users:
            if not isinstance(user, dict):
                continue
            email = user.get("email")
            if not isinstance(email, str) or "@" not in email:
                continue
            normalized = email.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            recipients.append(normalized)
            if len(recipients) >= max_recipients:
                break

        pagination = payload.get("pagination") if isinstance(payload, dict) else None
        total_pages = 0
        if isinstance(pagination, dict):
            try:
                total_pages = int(pagination.get("totalPages") or 0)
            except Exception:
                total_pages = 0

        if total_pages > 0 and page >= total_pages:
            break

        if total_pages == 0 and len(users) < page_size:
            break

        page += 1

    return recipients


def _resolve_public_announcement_emails(
    fallback_email: str,
    excluded_emails: list[str] | None = None,
) -> list[str]:
    fallback_normalized = str(fallback_email or "").strip().lower()

    excluded: set[str] = set()
    for value in excluded_emails or []:
        normalized = str(value or "").strip().lower()
        if normalized and "@" in normalized:
            excluded.add(normalized)

    try:
        recipients = _fetch_public_announcement_emails()
    except Exception as error:
        logger.warning("Falling back to single-recipient public announcement: %s", error)
        recipients = [fallback_normalized] if fallback_normalized else []

    filtered: list[str] = []
    seen: set[str] = set()
    for recipient in recipients:
        normalized = str(recipient or "").strip().lower()
        if not normalized or "@" not in normalized:
            continue
        if normalized in excluded or normalized in seen:
            continue
        seen.add(normalized)
        filtered.append(normalized)

    if filtered:
        return filtered

    if fallback_normalized and fallback_normalized not in excluded:
        return [fallback_normalized]

    return []


def _extract_event_name(event_id: str) -> str | None:
    event_url = _join_url(current_app.config["EVENT_SERVICE_URL"], f"/event/{event_id}")
    status_code, payload = _request_json("GET", event_url, headers=_internal_headers())
    if status_code != 200 or not payload:
        return None

    def _coerce_name(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    for key in ("name", "eventName", "event_name"):
        if isinstance(payload, dict) and key in payload:
            resolved = _coerce_name(payload.get(key))
            if resolved:
                return resolved

    nested_event = payload.get("event") if isinstance(payload, dict) else None
    if isinstance(nested_event, dict):
        for key in ("name", "eventName", "event_name"):
            resolved = _coerce_name(nested_event.get(key))
            if resolved:
                return resolved

    return None


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


def _fetch_booking_status(hold_id: str) -> dict[str, Any]:
    url = _join_url(current_app.config["BOOKING_STATUS_SERVICE_URL"], f"/booking-status/{hold_id}")
    status_code, payload = _request_json("GET", url, headers=_internal_headers())

    if status_code != 200 or not payload:
        _raise_dependency_http_error(
            service="booking-status-service",
            status_code=status_code,
            payload=payload,
            fallback_message="Failed to resolve booking status",
            not_found_message="Booking status not found",
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


def _update_seat_status(seat_id: str, status: str) -> dict[str, Any] | None:
    normalized_status = str(status or "").strip().upper()
    if normalized_status not in {"AVAILABLE", "PENDING_WAITLIST"}:
        raise ValidationError("status must be AVAILABLE or PENDING_WAITLIST")

    url = _join_url(current_app.config["INVENTORY_SERVICE_URL"], f"/inventory/seat/{seat_id}/status")
    status_code, payload = _request_json(
        "PUT",
        url,
        headers=_internal_headers(),
        payload={"status": normalized_status},
    )

    if status_code not in {200, 201}:
        _raise_dependency_http_error(
            service="inventory-service",
            status_code=status_code,
            payload=payload,
            fallback_message="Failed to update seat status",
        )

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


def _build_cancellation_status_payload(
    *,
    booking_id: str,
    requesting_user_id: str,
    new_hold_id: str | None,
) -> tuple[dict[str, Any], int]:
    verification = _fetch_payment_verification(booking_id, strict_policy=False)

    owner_user_id = _parse_uuid(verification.get("userID"), "payment.userID")
    if owner_user_id != requesting_user_id:
        raise ConflictError("Booking does not belong to requesting user")

    payment_status = str(verification.get("paymentStatus") or "").upper()
    within_policy = bool(verification.get("withinPolicy"))
    base_payload: dict[str, Any] = {
        "bookingID": booking_id,
        "userID": owner_user_id,
        "eventID": verification.get("eventID"),
        "holdID": verification.get("holdID"),
        "paymentStatus": payment_status,
        "withinPolicy": within_policy,
        "policyCutoffAt": verification.get("policyCutoffAt"),
        "refundAmount": verification.get("eligibleRefundAmount"),
        "terminal": False,
        "status": "CANCELLATION_AVAILABLE",
    }

    if payment_status == "REFUND_PENDING":
        base_payload.update(
            {
                "status": "REALLOCATION_PENDING",
                "terminal": False,
                "reason": "Refund is being processed",
            }
        )
        return base_payload, 200

    if payment_status == "REFUND_FAILED":
        base_payload.update(
            {
                "status": "CANCELLATION_IN_PROGRESS",
                "terminal": False,
                "reason": "Refund previously failed and requires manual follow-up",
            }
        )
        return base_payload, 200

    if payment_status == "REFUND_SUCCEEDED":
        base_payload.update(
            {
                "status": "REFUND_COMPLETED",
                "terminal": True,
                "reason": "Refund completed",
            }
        )

        if not new_hold_id:
            return base_payload, 200

        hold_status_payload = _fetch_booking_status(new_hold_id)
        ui_status = str(hold_status_payload.get("uiStatus") or "").upper()
        hold_status = str(hold_status_payload.get("holdStatus") or "").upper()

        base_payload.update(
            {
                "newHoldID": new_hold_id,
                "reallocation": {
                    "uiStatus": ui_status,
                    "holdStatus": hold_status,
                    "ticketID": hold_status_payload.get("ticketID"),
                    "seatNumber": hold_status_payload.get("seatNumber"),
                    "updatedAt": hold_status_payload.get("updatedAt"),
                },
            }
        )

        if ui_status == "CONFIRMED":
            base_payload.update({"status": "REALLOCATION_CONFIRMED", "terminal": True})
            return base_payload, 200

        if ui_status == "PROCESSING":
            base_payload.update(
                {
                    "status": "REALLOCATION_PENDING",
                    "terminal": False,
                    "reason": "Reallocation is still in progress",
                }
            )
            return base_payload, 200

        if ui_status in {"FAILED_PAYMENT", "EXPIRED"}:
            base_payload.update(
                {
                    "status": "REFUND_COMPLETED",
                    "terminal": True,
                    "reason": "Refund completed; waitlist reallocation was not completed",
                }
            )
            return base_payload, 200

        return base_payload, 200

    if payment_status == "SUCCEEDED" and not within_policy:
        base_payload.update(
            {
                "status": "DENIED",
                "terminal": True,
                "reason": "Not eligible under 48-hour cancellation policy",
            }
        )
        return base_payload, 200

    return base_payload, 200


def _build_refund_success_payload(
    booking_id: str,
    user_id: str,
    event_id: str,
    event_name: str | None,
    old_hold_id: str,
    refund_amount: Any,
    waitlist_status: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    refreshed_event_name = _extract_event_name(event_id) or event_name

    has_waitlist = bool(waitlist_status.get("hasWaitlist"))
    entries = waitlist_status.get("entries") or []
    next_user = waitlist_status.get("nextUser") or (entries[0] if entries else None)
    old_hold = _fetch_inventory_hold(old_hold_id)
    seat_id = _parse_uuid(old_hold.get("seatID"), "seatID")

    if not has_waitlist or not next_user:
        _update_seat_status(seat_id, "AVAILABLE")
        public_announcement_email = _extract_email_from_user(user_id)
        public_announcement_recipients = _resolve_public_announcement_emails(
            public_announcement_email,
            excluded_emails=[public_announcement_email],
        )

        if public_announcement_recipients:
            _publish_notification(
                "TICKET_AVAILABLE_PUBLIC",
                {
                    "email": public_announcement_recipients[0],
                    "waitlistEmails": public_announcement_recipients,
                    "bookingID": booking_id,
                    "eventID": event_id,
                    "eventName": refreshed_event_name,
                    "holdID": old_hold_id,
                    "refundAmount": refund_amount,
                },
            )
        else:
            logger.info(
                "No public announcement recipients after excluding cancelling user. bookingID=%s eventID=%s",
                booking_id,
                event_id,
            )

        return (
            {
                "status": "REFUND_COMPLETED",
                "bookingID": booking_id,
                "eventID": event_id,
                "eventName": refreshed_event_name,
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

    _update_seat_status(seat_id, "PENDING_WAITLIST")

    new_hold = _create_waitlist_hold(event_id, next_user_id, str(seat_category))
    new_hold_id = _parse_uuid(new_hold.get("holdID"), "holdID")
    _mark_waitlist_offer(waitlist_id, new_hold_id)

    payment_init = _create_payment_for_hold(new_hold_id, next_user_id, new_hold.get("amount"))
    next_user_email = _extract_email_from_user(next_user_id)

    _publish_notification(
        "SEAT_AVAILABLE",
        {
            "email": next_user_email,
            "eventName": refreshed_event_name,
            "holdID": new_hold_id,
            "holdExpiry": new_hold.get("holdExpiry"),
            "paymentURL": _build_waitlist_payment_url(new_hold_id),
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
            "eventName": refreshed_event_name,
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


@cancellation_bp.get("/bookings/cancel/status/<booking_id>")
def get_cancellation_status(booking_id: str):
    try:
        parsed_booking_id = _parse_uuid(booking_id, "bookingID")
        user_id = _parse_uuid(request.args.get("userID"), "userID")
        new_hold_id_raw = request.args.get("newHoldID")
        new_hold_id = _parse_uuid(new_hold_id_raw, "newHoldID") if new_hold_id_raw else None

        payload, status_code = _build_cancellation_status_payload(
            booking_id=parsed_booking_id,
            requesting_user_id=user_id,
            new_hold_id=new_hold_id,
        )
        return _api_response(payload, status_code)
    except ApiError as error:
        return _json_error(error.message, error.status_code, error.details)
    except Exception as error:
        logger.exception("Unexpected cancellation status error: %s", error)
        return _json_error("Failed to resolve cancellation status", 500)


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
    spec = get_service_swagger_spec("cancellation-orchestrator")
    spec["servers"] = [{"url": base_url}]
    return spec


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

    register_openapi_routes(app, lambda: _build_openapi_spec(request.host_url.rstrip("/")))

    _register_error_handlers(app)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
