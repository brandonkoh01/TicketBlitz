import logging
import os
import time
import uuid
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from flask import Blueprint, Flask, current_app, jsonify, request
from flask_cors import CORS

from shared.mq import publish_json, rabbitmq_configured
from shared.openapi import build_openapi_spec, register_openapi_routes

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 400, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class ValidationError(ApiError):
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message, 400, details)


class NotFoundError(ApiError):
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message, 404, details)


class ConflictError(ApiError):
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message, 409, details)


class DependencyError(ApiError):
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message, 503, details)


class ExternalServiceError(ApiError):
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message, 502, details)


class BaseConfig:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "reservation-orchestrator")

    USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:5000")
    INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:5000")
    PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:5000")
    WAITLIST_SERVICE_URL = os.getenv("WAITLIST_SERVICE_URL", "http://waitlist-service:5000")
    EVENT_SERVICE_URL = os.getenv("EVENT_SERVICE_URL", "http://event-service:5000")

    INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "").strip()
    USER_SERVICE_AUTH_HEADER = os.getenv("USER_SERVICE_AUTH_HEADER", "X-Internal-Token")
    WAITLIST_SERVICE_AUTH_HEADER = os.getenv("WAITLIST_SERVICE_AUTH_HEADER", "X-Internal-Token")
    PAYMENT_SERVICE_AUTH_HEADER = os.getenv("PAYMENT_SERVICE_AUTH_HEADER", "X-Internal-Token")
    PAYMENT_INTERNAL_TOKEN = os.getenv("PAYMENT_INTERNAL_TOKEN", INTERNAL_SERVICE_TOKEN).strip()

    OUTSYSTEMS_BASE_URL = os.getenv("OUTSYSTEMS_BASE_URL", "").strip()
    OUTSYSTEMS_API_KEY = os.getenv("OUTSYSTEMS_API_KEY", "").strip()
    OUTSYSTEMS_AUTH_HEADER = os.getenv("OUTSYSTEMS_AUTH_HEADER", "X-API-Key")

    HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
    HTTP_MAX_RETRIES = int(os.getenv("HTTP_MAX_RETRIES", "2"))

    AUTHENTICATED_USER_HEADER = os.getenv("AUTHENTICATED_USER_HEADER", "X-User-ID")
    FALLBACK_AUTHENTICATED_USER_HEADERS = os.getenv(
        "FALLBACK_AUTHENTICATED_USER_HEADERS",
        "X-Authenticated-User-ID,X-Consumer-Custom-ID",
    )
    REQUIRE_AUTHENTICATED_USER_HEADER = os.getenv("REQUIRE_AUTHENTICATED_USER_HEADER", "true")
    CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173")


def _parse_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a valid UUID")

    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError) as error:
        raise ValidationError(f"{field_name} must be a valid UUID") from error


def _parse_qty(value: Any) -> int:
    if value is None:
        return 1

    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError("qty must be an integer") from error

    if parsed != 1:
        raise ValidationError("Only qty=1 is supported")

    return parsed


def _normalize_seat_category(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError("seatCategory must be a string")

    normalized = value.strip().upper()
    if not normalized:
        raise ValidationError("seatCategory is required")

    return normalized


def _safe_json(response: requests.Response) -> dict[str, Any]:
    if not response.content:
        return {}

    try:
        payload = response.json()
    except ValueError as error:
        raise ExternalServiceError("Downstream response is not valid JSON") from error

    if isinstance(payload, dict):
        return payload

    return {"data": payload}


def _extract_error_message(payload: dict[str, Any], fallback: str) -> str:
    return str(payload.get("error") or payload.get("message") or fallback)


def _str_to_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _parse_csv(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_correlation_id(payload: Optional[dict[str, Any]]) -> str:
    header_value = request.headers.get("X-Correlation-ID")
    if header_value:
        return header_value

    if payload and isinstance(payload.get("correlationID"), str) and payload["correlationID"].strip():
        return payload["correlationID"].strip()

    return str(uuid.uuid4())


def _resolve_authenticated_user_id(required: bool) -> Optional[str]:
    header_names = [current_app.config.get("AUTHENTICATED_USER_HEADER", "X-User-ID")]
    header_names.extend(_parse_csv(current_app.config.get("FALLBACK_AUTHENTICATED_USER_HEADERS", "")))

    for header_name in header_names:
        header_value = request.headers.get(header_name)
        if header_value:
            return _parse_uuid(header_value.strip(), header_name)

    if required:
        raise ValidationError("Authenticated user header is required")
    return None


def _validate_authenticated_user_binding(payload: dict[str, Any], *, required: bool) -> Optional[str]:
    authenticated_user_id = _resolve_authenticated_user_id(required=required)
    if not authenticated_user_id:
        return None

    payload_user_id = payload.get("userID")
    if not isinstance(payload_user_id, str):
        return authenticated_user_id

    try:
        payload_user_id = str(uuid.UUID(payload_user_id))
    except (ValueError, TypeError):
        # Keep route-level behavior focused on auth checks; domain validation remains in service methods.
        return authenticated_user_id

    if payload_user_id != authenticated_user_id:
        raise ConflictError("userID does not match authenticated user")

    return authenticated_user_id


def _public_eticket_view(ticket: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(ticket, dict):
        return None

    allowed = (
        "ticketID",
        "status",
        "issuedAt",
        "qrCode",
        "qrCodeUrl",
        "holdID",
        "eventID",
        "userID",
    )
    return {key: ticket[key] for key in allowed if key in ticket}


def _public_hold_view(hold: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(hold, dict):
        return None

    allowed = (
        "holdID",
        "eventID",
        "userID",
        "seatCategory",
        "seatID",
        "seatNumber",
        "holdStatus",
        "holdExpiry",
        "amount",
        "currency",
    )
    return {key: hold[key] for key in allowed if key in hold}


def _public_waitlist_view(waitlist: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(waitlist, dict):
        return None

    allowed = (
        "waitlistID",
        "eventID",
        "userID",
        "holdID",
        "status",
        "position",
        "joinedAt",
        "offeredAt",
        "expiredAt",
    )
    return {key: waitlist[key] for key in allowed if key in waitlist}


def _public_payment_view(payment: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(payment, dict):
        return None

    allowed = ("paymentIntentID", "paymentStatus", "status", "amount", "currency")
    return {key: payment[key] for key in allowed if key in payment}


def _configure_cors(app: Flask) -> None:
    origins = _parse_csv(app.config.get("CORS_ALLOWED_ORIGINS", ""))
    if not origins:
        logger.warning("CORS_ALLOWED_ORIGINS is empty; only health endpoint allows cross-origin requests")
        CORS(app, resources={r"/health": {"origins": "*"}})
        return

    CORS(
        app,
        resources={
            r"/reserve.*": {"origins": origins},
            r"/waitlist/.*": {"origins": origins},
            r"/openapi.json": {"origins": origins},
            r"/docs.*": {"origins": origins},
            r"/health": {"origins": "*"},
        },
    )


def _json_response(payload: dict[str, Any], status_code: int, correlation_id: str):
    response = jsonify(payload)
    response.status_code = status_code
    response.headers["X-Correlation-ID"] = correlation_id
    return response


def _json_error(error: ApiError, correlation_id: str):
    payload: dict[str, Any] = {"error": error.message}
    if error.details is not None:
        payload["details"] = error.details
    return _json_response(payload, error.status_code, correlation_id)


class DownstreamClient:
    def __init__(self, config: BaseConfig):
        self.config = config
        self.session = requests.Session()

    def _request(
        self,
        *,
        service_name: str,
        base_url: str,
        method: str,
        path: str,
        correlation_id: str,
        json_body: Optional[dict[str, Any]] = None,
        auth_header: Optional[str] = None,
        auth_token: Optional[str] = None,
        allow_404: bool = False,
    ) -> Optional[dict[str, Any]]:
        url = base_url.rstrip("/") + "/" + path.lstrip("/")
        headers: dict[str, str] = {
            "Accept": "application/json",
            "X-Correlation-ID": correlation_id,
        }
        if auth_header and auth_token:
            headers[auth_header] = auth_token

        attempts = max(1, self.config.HTTP_MAX_RETRIES + 1)
        last_error: Optional[str] = None

        for attempt in range(attempts):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=json_body,
                    headers=headers,
                    timeout=self.config.HTTP_TIMEOUT_SECONDS,
                )
            except requests.RequestException as error:
                last_error = str(error)
                if attempt < attempts - 1:
                    time.sleep(0.25 * (2 ** attempt))
                    continue
                raise DependencyError(f"{service_name} is unavailable", details=last_error) from error

            if response.status_code in {502, 503, 504} and attempt < attempts - 1:
                time.sleep(0.25 * (2 ** attempt))
                continue

            if allow_404 and response.status_code == 404:
                return None

            payload = _safe_json(response)

            if 200 <= response.status_code < 300:
                return payload

            error_message = _extract_error_message(payload, f"{service_name} returned {response.status_code}")
            details = payload.get("details")

            if response.status_code == 400:
                raise ValidationError(error_message, details)
            if response.status_code == 404:
                raise NotFoundError(error_message, details)
            if response.status_code == 409:
                raise ConflictError(error_message, details)
            if response.status_code in {401, 403}:
                raise ExternalServiceError(
                    f"{service_name} authorization failed",
                    details={"status": response.status_code, "message": error_message},
                )
            if response.status_code >= 500:
                raise DependencyError(f"{service_name} is unavailable", details=error_message)

            raise ExternalServiceError(
                f"Unexpected response from {service_name}",
                details={"status": response.status_code, "body": payload},
            )

        raise DependencyError(f"{service_name} is unavailable", details=last_error)

    def get_user(self, user_id: str, correlation_id: str) -> dict[str, Any]:
        payload = self._request(
            service_name="user-service",
            base_url=self.config.USER_SERVICE_URL,
            method="GET",
            path=f"/user/{user_id}",
            correlation_id=correlation_id,
            auth_header=self.config.USER_SERVICE_AUTH_HEADER,
            auth_token=self.config.INTERNAL_SERVICE_TOKEN,
        )
        if payload is None:
            raise NotFoundError("User not found")
        return payload

    def get_event(self, event_id: str, correlation_id: str) -> Optional[dict[str, Any]]:
        return self._request(
            service_name="event-service",
            base_url=self.config.EVENT_SERVICE_URL,
            method="GET",
            path=f"/event/{event_id}",
            correlation_id=correlation_id,
            allow_404=True,
        )

    def get_inventory(self, event_id: str, seat_category: str, correlation_id: str) -> dict[str, Any]:
        payload = self._request(
            service_name="inventory-service",
            base_url=self.config.INVENTORY_SERVICE_URL,
            method="GET",
            path=f"/inventory/{event_id}/{seat_category}",
            correlation_id=correlation_id,
        )
        if payload is None:
            raise NotFoundError("Inventory category not found")
        return payload

    def create_hold(
        self,
        *,
        event_id: str,
        user_id: str,
        seat_category: str,
        qty: int,
        from_waitlist: bool,
        correlation_id: str,
    ) -> dict[str, Any]:
        payload = self._request(
            service_name="inventory-service",
            base_url=self.config.INVENTORY_SERVICE_URL,
            method="POST",
            path="/inventory/hold",
            correlation_id=correlation_id,
            json_body={
                "eventID": event_id,
                "userID": user_id,
                "seatCategory": seat_category,
                "qty": qty,
                "fromWaitlist": from_waitlist,
            },
        )
        if payload is None:
            raise ExternalServiceError("Failed to create inventory hold")
        return payload

    def get_hold(self, hold_id: str, correlation_id: str) -> dict[str, Any]:
        payload = self._request(
            service_name="inventory-service",
            base_url=self.config.INVENTORY_SERVICE_URL,
            method="GET",
            path=f"/inventory/hold/{hold_id}",
            correlation_id=correlation_id,
        )
        if payload is None:
            raise NotFoundError("Hold not found")
        return payload

    def initiate_payment(self, *, hold_id: str, user_id: str, amount: Any, correlation_id: str) -> dict[str, Any]:
        payload = self._request(
            service_name="payment-service",
            base_url=self.config.PAYMENT_SERVICE_URL,
            method="POST",
            path="/payment/initiate",
            correlation_id=correlation_id,
            auth_header=self.config.PAYMENT_SERVICE_AUTH_HEADER,
            auth_token=self.config.PAYMENT_INTERNAL_TOKEN,
            json_body={
                "holdID": hold_id,
                "userID": user_id,
                "amount": amount,
                "idempotencyKey": f"reserve:{hold_id}",
            },
        )
        if payload is None:
            raise ExternalServiceError("Failed to initiate payment")
        return payload

    def get_payment_hold(self, hold_id: str, correlation_id: str) -> Optional[dict[str, Any]]:
        return self._request(
            service_name="payment-service",
            base_url=self.config.PAYMENT_SERVICE_URL,
            method="GET",
            path=f"/payment/hold/{hold_id}",
            correlation_id=correlation_id,
            allow_404=True,
        )

    def join_waitlist(
        self,
        *,
        user_id: str,
        event_id: str,
        seat_category: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        payload = self._request(
            service_name="waitlist-service",
            base_url=self.config.WAITLIST_SERVICE_URL,
            method="POST",
            path="/waitlist/join",
            correlation_id=correlation_id,
            auth_header=self.config.WAITLIST_SERVICE_AUTH_HEADER,
            auth_token=self.config.INTERNAL_SERVICE_TOKEN,
            json_body={
                "userID": user_id,
                "eventID": event_id,
                "seatCategory": seat_category,
                "qty": 1,
                "source": "RESERVATION_ORCHESTRATOR",
            },
        )
        if payload is None:
            raise ExternalServiceError("Failed to join waitlist")
        return payload

    def get_waitlist_by_hold(self, hold_id: str, correlation_id: str) -> Optional[dict[str, Any]]:
        return self._request(
            service_name="waitlist-service",
            base_url=self.config.WAITLIST_SERVICE_URL,
            method="GET",
            path=f"/waitlist/by-hold/{hold_id}",
            correlation_id=correlation_id,
            auth_header=self.config.WAITLIST_SERVICE_AUTH_HEADER,
            auth_token=self.config.INTERNAL_SERVICE_TOKEN,
            allow_404=True,
        )

    def _outsystems_enabled(self) -> bool:
        return bool(self.config.OUTSYSTEMS_BASE_URL and self.config.OUTSYSTEMS_API_KEY)

    def get_eticket_by_hold(self, hold_id: str, correlation_id: str) -> Optional[dict[str, Any]]:
        if not self._outsystems_enabled():
            return None

        return self._request(
            service_name="outsystems-eticket",
            base_url=self.config.OUTSYSTEMS_BASE_URL,
            method="GET",
            path=f"/eticket/hold/{hold_id}",
            correlation_id=correlation_id,
            auth_header=self.config.OUTSYSTEMS_AUTH_HEADER,
            auth_token=self.config.OUTSYSTEMS_API_KEY,
            allow_404=True,
        )

    def generate_eticket(self, hold: dict[str, Any], user_id: str, correlation_id: str) -> Optional[dict[str, Any]]:
        if not self._outsystems_enabled():
            return None

        payload = self._request(
            service_name="outsystems-eticket",
            base_url=self.config.OUTSYSTEMS_BASE_URL,
            method="POST",
            path="/eticket/generate",
            correlation_id=correlation_id,
            auth_header=self.config.OUTSYSTEMS_AUTH_HEADER,
            auth_token=self.config.OUTSYSTEMS_API_KEY,
            json_body={
                "holdID": hold.get("holdID"),
                "userID": user_id,
                "eventID": hold.get("eventID"),
                "seatID": hold.get("seatID"),
                "seatNumber": hold.get("seatNumber"),
                "correlationID": correlation_id,
                "metadata": "generated_by=reservation_orchestrator",
            },
        )
        return payload


class ReservationOrchestrator:
    def __init__(self, config: BaseConfig, client: DownstreamClient):
        self.config = config
        self.client = client

    def reserve(self, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        user_id = _parse_uuid(payload.get("userID"), "userID")
        event_id = _parse_uuid(payload.get("eventID"), "eventID")
        seat_category = _normalize_seat_category(payload.get("seatCategory"))
        qty = _parse_qty(payload.get("qty"))

        user = self.client.get_user(user_id, correlation_id)
        event = self.client.get_event(event_id, correlation_id)
        if event is None:
            raise NotFoundError("Event not found")
        inventory = self.client.get_inventory(event_id, seat_category, correlation_id)

        available = int(inventory.get("available") or 0)
        inventory_status = str(inventory.get("status") or "").upper()

        if available > 0 and inventory_status != "SOLD_OUT":
            hold = self.client.create_hold(
                event_id=event_id,
                user_id=user_id,
                seat_category=seat_category,
                qty=qty,
                from_waitlist=False,
                correlation_id=correlation_id,
            )
            payment = self.client.initiate_payment(
                hold_id=hold["holdID"],
                user_id=user_id,
                amount=hold.get("amount"),
                correlation_id=correlation_id,
            )
            existing_ticket = self.client.get_eticket_by_hold(hold["holdID"], correlation_id)

            return {
                "status": "PAYMENT_PENDING",
                "holdID": hold.get("holdID"),
                "holdExpiry": hold.get("holdExpiry"),
                "amount": hold.get("amount"),
                "currency": hold.get("currency"),
                "paymentIntentID": payment.get("paymentIntentID"),
                "clientSecret": payment.get("clientSecret"),
                "returnURL": f"/booking/pending/{hold.get('holdID')}",
                "eventID": event_id,
                "seatCategory": seat_category,
                "eventName": (event or {}).get("name"),
                "existingETicket": _public_eticket_view(existing_ticket),
                "correlationID": correlation_id,
            }

        waitlist = self.client.join_waitlist(
            user_id=user_id,
            event_id=event_id,
            seat_category=seat_category,
            correlation_id=correlation_id,
        )
        waitlist_id = waitlist.get("waitlistID")
        position = waitlist.get("position")

        self._publish_waitlist_joined(
            email=user.get("email"),
            event_name=(event or {}).get("name") or "TicketBlitz Event",
            position=position,
            waitlist_id=waitlist_id,
            correlation_id=correlation_id,
        )

        return {
            "status": "WAITLISTED",
            "waitlistID": waitlist_id,
            "position": position,
            "eventID": event_id,
            "seatCategory": seat_category,
            "eventName": (event or {}).get("name"),
            "correlationID": correlation_id,
        }

    def reserve_confirm(self, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        hold_id = _parse_uuid(payload.get("holdID"), "holdID")
        user_id = _parse_uuid(payload.get("userID"), "userID")

        hold = self.client.get_hold(hold_id, correlation_id)
        hold_user = hold.get("userID")
        if hold_user and hold_user != user_id:
            raise ConflictError("holdID does not belong to userID")

        payment_state = self.client.get_payment_hold(hold_id, correlation_id)
        payment_status = str((payment_state or {}).get("paymentStatus") or "").upper()
        hold_status = str(hold.get("holdStatus") or "").upper()

        if payment_status == "SUCCEEDED" or hold_status == "CONFIRMED":
            ticket = self.client.get_eticket_by_hold(hold_id, correlation_id)
            if ticket is None:
                ticket = self.client.generate_eticket(hold, user_id, correlation_id)

            return {
                "status": "CONFIRMED",
                "holdID": hold_id,
                "ticket": _public_eticket_view(ticket),
                "paymentStatus": payment_status or "SUCCEEDED",
                "correlationID": correlation_id,
            }

        if hold_status != "HELD":
            raise ConflictError("Hold is not in HELD status")

        payment = self.client.initiate_payment(
            hold_id=hold_id,
            user_id=user_id,
            amount=hold.get("amount"),
            correlation_id=correlation_id,
        )

        existing_ticket = self.client.get_eticket_by_hold(hold_id, correlation_id)

        return {
            "status": "PAYMENT_PENDING",
            "holdID": hold_id,
            "holdExpiry": hold.get("holdExpiry"),
            "amount": hold.get("amount"),
            "currency": hold.get("currency"),
            "paymentIntentID": payment.get("paymentIntentID"),
            "clientSecret": payment.get("clientSecret"),
            "paymentStatus": payment.get("status"),
            "returnURL": f"/booking/pending/{hold_id}",
            "existingETicket": _public_eticket_view(existing_ticket),
            "correlationID": correlation_id,
        }

    def waitlist_confirm(self, hold_id: str, correlation_id: str) -> dict[str, Any]:
        parsed_hold_id = _parse_uuid(hold_id, "holdID")

        hold = self.client.get_hold(parsed_hold_id, correlation_id)
        waitlist = self.client.get_waitlist_by_hold(parsed_hold_id, correlation_id)
        payment = self.client.get_payment_hold(parsed_hold_id, correlation_id)
        eticket = self.client.get_eticket_by_hold(parsed_hold_id, correlation_id)

        hold_status = str(hold.get("holdStatus") or "").upper()
        payment_status = str((payment or {}).get("paymentStatus") or "").upper()
        waitlist_status = str((waitlist or {}).get("status") or "").upper()

        if eticket:
            ui_status = "CONFIRMED"
        elif hold_status == "EXPIRED":
            ui_status = "EXPIRED"
        elif payment_status == "SUCCEEDED":
            ui_status = "PAID_PROCESSING"
        elif waitlist_status == "HOLD_OFFERED":
            ui_status = "WAITLIST_OFFERED"
        elif waitlist_status == "WAITING":
            ui_status = "WAITLIST_PENDING"
        else:
            ui_status = "PROCESSING"

        return {
            "uiStatus": ui_status,
            "hold": _public_hold_view(hold),
            "waitlist": _public_waitlist_view(waitlist),
            "payment": _public_payment_view(payment),
            "eticket": _public_eticket_view(eticket),
            "correlationID": correlation_id,
        }

    def _publish_waitlist_joined(
        self,
        *,
        email: Optional[str],
        event_name: str,
        position: Any,
        waitlist_id: Any,
        correlation_id: str,
    ) -> None:
        if not email:
            logger.warning("Waitlist notification skipped: missing email")
            return

        if not rabbitmq_configured():
            logger.warning("RabbitMQ not configured; notification.send skipped")
            return

        payload = {
            "type": "WAITLIST_JOINED",
            "email": email,
            "eventName": event_name,
            "position": position,
            "waitlistID": waitlist_id,
            "correlationID": correlation_id,
        }
        try:
            publish_json("notification.send", payload, exchange="ticketblitz")
        except Exception as error:
            logger.warning("Failed to publish waitlist notification: %s", error)


reservation_bp = Blueprint("reservation_orchestrator", __name__)


@reservation_bp.get("/health")
def health():
    payload = {
        "status": "ok",
        "service": current_app.config.get("SERVICE_NAME", "reservation-orchestrator"),
        "rabbitmqConfigured": rabbitmq_configured(),
        "outsystemsConfigured": bool(
            current_app.config.get("OUTSYSTEMS_BASE_URL")
            and current_app.config.get("OUTSYSTEMS_API_KEY")
        ),
    }
    return jsonify(payload), 200


@reservation_bp.post("/reserve")
def reserve():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        correlation_id = _resolve_correlation_id(None)
        return _json_error(ValidationError("Request body must be a JSON object"), correlation_id)

    correlation_id = _resolve_correlation_id(body)
    try:
        require_user_binding = _str_to_bool(current_app.config.get("REQUIRE_AUTHENTICATED_USER_HEADER"), default=True)
        _validate_authenticated_user_binding(body, required=require_user_binding)
        service: ReservationOrchestrator = current_app.config["ORCHESTRATOR"]
        payload = service.reserve(body, correlation_id)
        return _json_response(payload, 200, correlation_id)
    except ApiError as error:
        return _json_error(error, correlation_id)
    except Exception as error:  # pragma: no cover
        logger.exception("Unexpected error in /reserve: %s", error)
        return _json_error(ApiError("Internal server error", 500), correlation_id)


@reservation_bp.post("/reserve/confirm")
def reserve_confirm():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        correlation_id = _resolve_correlation_id(None)
        return _json_error(ValidationError("Request body must be a JSON object"), correlation_id)

    correlation_id = _resolve_correlation_id(body)
    try:
        require_user_binding = _str_to_bool(current_app.config.get("REQUIRE_AUTHENTICATED_USER_HEADER"), default=True)
        _validate_authenticated_user_binding(body, required=require_user_binding)
        service: ReservationOrchestrator = current_app.config["ORCHESTRATOR"]
        payload = service.reserve_confirm(body, correlation_id)
        return _json_response(payload, 200, correlation_id)
    except ApiError as error:
        return _json_error(error, correlation_id)
    except Exception as error:  # pragma: no cover
        logger.exception("Unexpected error in /reserve/confirm: %s", error)
        return _json_error(ApiError("Internal server error", 500), correlation_id)


@reservation_bp.get("/waitlist/confirm/<hold_id>")
def waitlist_confirm(hold_id: str):
    correlation_id = _resolve_correlation_id(None)
    try:
        service: ReservationOrchestrator = current_app.config["ORCHESTRATOR"]
        payload = service.waitlist_confirm(hold_id, correlation_id)
        return _json_response(payload, 200, correlation_id)
    except ApiError as error:
        return _json_error(error, correlation_id)
    except Exception as error:  # pragma: no cover
        logger.exception("Unexpected error in /waitlist/confirm/%s: %s", hold_id, error)
        return _json_error(ApiError("Internal server error", 500), correlation_id)


def _build_openapi(service_name: str) -> dict[str, Any]:
    return build_openapi_spec(
        service_name=service_name,
        title="TicketBlitz Reservation Orchestrator API",
        description="Composite endpoints for reservation, waitlist confirmation, and payment setup.",
        paths={
            "/health": {
                "get": {
                    "summary": "Service health status",
                    "tags": ["System"],
                    "responses": {
                        "200": {
                            "description": "Healthy service response",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/reserve": {
                "post": {
                    "summary": "Reserve a ticket or join waitlist",
                    "tags": ["Reservation"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ReserveRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Reservation outcome",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ReserveResponse"}
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "404": {"$ref": "#/components/responses/NotFound"},
                        "409": {"$ref": "#/components/responses/BadRequest"},
                        "502": {"$ref": "#/components/responses/ServiceUnavailable"},
                        "503": {"$ref": "#/components/responses/ServiceUnavailable"},
                    },
                }
            },
            "/reserve/confirm": {
                "post": {
                    "summary": "Resume or confirm payment flow for a hold",
                    "tags": ["Reservation"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ReserveConfirmRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Payment or confirmation state",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ReserveResponse"}
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "404": {"$ref": "#/components/responses/NotFound"},
                        "409": {"$ref": "#/components/responses/BadRequest"},
                        "502": {"$ref": "#/components/responses/ServiceUnavailable"},
                        "503": {"$ref": "#/components/responses/ServiceUnavailable"},
                    },
                }
            },
            "/waitlist/confirm/{hold_id}": {
                "get": {
                    "summary": "Load waitlist confirmation state by hold ID",
                    "tags": ["Reservation"],
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
                            "description": "Waitlist confirmation context",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/WaitlistConfirmResponse"}
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "404": {"$ref": "#/components/responses/NotFound"},
                        "502": {"$ref": "#/components/responses/ServiceUnavailable"},
                        "503": {"$ref": "#/components/responses/ServiceUnavailable"},
                    },
                }
            },
        },
        extra_components={
            "schemas": {
                "ReserveRequest": {
                    "type": "object",
                    "required": ["userID", "eventID", "seatCategory"],
                    "properties": {
                        "userID": {"type": "string", "format": "uuid"},
                        "eventID": {"type": "string", "format": "uuid"},
                        "seatCategory": {"type": "string"},
                        "qty": {"type": "integer", "default": 1},
                        "correlationID": {"type": "string", "format": "uuid"},
                    },
                },
                "ReserveConfirmRequest": {
                    "type": "object",
                    "required": ["holdID", "userID"],
                    "properties": {
                        "holdID": {"type": "string", "format": "uuid"},
                        "userID": {"type": "string", "format": "uuid"},
                        "correlationID": {"type": "string", "format": "uuid"},
                    },
                },
                "ReserveResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "holdID": {"type": "string", "format": "uuid"},
                        "waitlistID": {"type": "string", "format": "uuid"},
                        "position": {"type": "integer"},
                        "paymentIntentID": {"type": "string"},
                        "clientSecret": {"type": "string"},
                        "returnURL": {"type": "string"},
                        "correlationID": {"type": "string", "format": "uuid"},
                    },
                    "additionalProperties": True,
                },
                "WaitlistConfirmResponse": {
                    "type": "object",
                    "properties": {
                        "uiStatus": {"type": "string"},
                        "hold": {"type": "object", "additionalProperties": True},
                        "waitlist": {"type": "object", "additionalProperties": True},
                        "payment": {"type": "object", "additionalProperties": True},
                        "eticket": {"type": "object", "additionalProperties": True},
                        "correlationID": {"type": "string", "format": "uuid"},
                    },
                    "additionalProperties": True,
                },
            }
        },
    )


def _validate_required_config(app: Flask) -> None:
    required_names = [
        "USER_SERVICE_URL",
        "INVENTORY_SERVICE_URL",
        "PAYMENT_SERVICE_URL",
        "WAITLIST_SERVICE_URL",
        "EVENT_SERVICE_URL",
        "INTERNAL_SERVICE_TOKEN",
    ]

    missing = [name for name in required_names if not app.config.get(name)]
    if missing:
        raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")


def create_app(test_config: Optional[dict[str, Any]] = None) -> Flask:
    load_dotenv(override=False)

    app = Flask(__name__)
    app.config.from_object(BaseConfig)

    if test_config:
        app.config.update(test_config)

    _validate_required_config(app)

    _configure_cors(app)
    app.register_blueprint(reservation_bp)

    config = type("Config", (), app.config)
    client = DownstreamClient(config)
    app.config["ORCHESTRATOR"] = ReservationOrchestrator(config, client)

    register_openapi_routes(
        app,
        lambda: _build_openapi(app.config.get("SERVICE_NAME", "reservation-orchestrator")),
        openapi_path="/openapi.json",
        docs_path="/docs",
    )

    def not_found(_error):
        correlation_id = _resolve_correlation_id(None)
        return _json_error(NotFoundError("Not found"), correlation_id)

    def internal_error(error):
        logger.exception("Unhandled error: %s", error)
        correlation_id = _resolve_correlation_id(None)
        return _json_error(ApiError("Internal server error", 500), correlation_id)

    app.register_error_handler(404, not_found)
    app.register_error_handler(500, internal_error)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
