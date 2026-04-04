from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Blueprint, Flask, Response, current_app, jsonify, request
from flask_cors import CORS

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

booking_status_bp = Blueprint("booking_status_service", __name__)

UI_STATUS_PROCESSING = "PROCESSING"
UI_STATUS_CONFIRMED = "CONFIRMED"
UI_STATUS_FAILED_PAYMENT = "FAILED_PAYMENT"
UI_STATUS_EXPIRED = "EXPIRED"

RELEASE_REASON_PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"


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


class DependencyError(ApiError):
    def __init__(self, message: str, details: Any | None = None):
        super().__init__(message, 503, details)


class BaseConfig:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "booking-status-service")
    INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:5000")
    PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:5000")
    OUTSYSTEMS_BASE_URL = os.getenv("OUTSYSTEMS_BASE_URL", "")
    INTERNAL_AUTH_HEADER = os.getenv("INTERNAL_AUTH_HEADER", "X-Internal-Token")
    INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "")
    REQUEST_TIMEOUT_SECONDS = 3.0
    ALLOW_CONFIRMED_WITHOUT_TICKET = False


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        parsed = float(raw)
    except ValueError:
        return default

    return parsed if parsed > 0 else default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


BaseConfig.REQUEST_TIMEOUT_SECONDS = _env_float("BOOKING_STATUS_TIMEOUT_SECONDS", 3.0)
BaseConfig.ALLOW_CONFIRMED_WITHOUT_TICKET = _env_bool("BOOKING_STATUS_ALLOW_CONFIRMED_WITHOUT_TICKET", False)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
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


def _latest_iso_timestamp(values: list[Any]) -> str | None:
    parsed = [ts for ts in (_parse_datetime(value) for value in values) if ts]
    if not parsed:
        return None
    return max(parsed).isoformat()


def _api_response(payload: dict[str, Any], status_code: int = 200):
    return jsonify(payload), status_code


def _json_error(message: str, status_code: int, details: Any | None = None):
    payload: dict[str, Any] = {"error": message}
    if details is not None:
        payload["details"] = details
    return _api_response(payload, status_code)


def _safe_error_details(error: ApiError) -> Any | None:
    if error.details is None:
        return None

    if isinstance(error, DependencyError):
        if isinstance(error.details, dict) and error.details.get("dependency"):
            return {"dependency": error.details["dependency"]}
        return {"dependency": "upstream"}

    return error.details


def _parse_hold_id(hold_id: str) -> str:
    try:
        return str(uuid.UUID(str(hold_id)))
    except Exception as error:
        raise ValidationError("holdID must be a valid UUID") from error


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _internal_auth_headers() -> dict[str, str]:
    token = str(current_app.config.get("INTERNAL_SERVICE_TOKEN") or "").strip()
    if not token:
        return {}

    header = str(current_app.config.get("INTERNAL_AUTH_HEADER") or "X-Internal-Token").strip()
    return {header: token}


def _request_json(url: str, *, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any] | None]:
    timeout = float(current_app.config.get("REQUEST_TIMEOUT_SECONDS", 3.0))
    try:
        response = requests.get(url, headers=headers or {}, timeout=timeout)
    except requests.RequestException as error:
        logger.warning("Dependency request failed: url=%s reason=%s", url, error)
        raise DependencyError("Dependency request failed", details={"dependency": "upstream"}) from error

    if response.status_code == 204:
        return response.status_code, None

    if not response.text:
        return response.status_code, None

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    if isinstance(payload, dict):
        return response.status_code, payload

    return response.status_code, {"data": payload}


def _fetch_inventory_hold(hold_id: str) -> dict[str, Any]:
    base_url = current_app.config["INVENTORY_SERVICE_URL"]
    url = _join_url(base_url, f"/inventory/hold/{hold_id}")
    status_code, payload = _request_json(url, headers=_internal_auth_headers())

    if status_code == 404:
        raise NotFoundError("Hold not found")

    if status_code != 200 or not isinstance(payload, dict):
        logger.warning(
            "Inventory service unavailable: status_code=%s url=%s payload=%s",
            status_code,
            url,
            payload,
        )
        raise DependencyError(
            "Inventory service unavailable",
            details={"dependency": "inventory-service"},
        )

    return payload


def _fetch_payment_hold(hold_id: str) -> dict[str, Any] | None:
    base_url = current_app.config["PAYMENT_SERVICE_URL"]
    url = _join_url(base_url, f"/payment/hold/{hold_id}")
    status_code, payload = _request_json(url, headers=_internal_auth_headers())

    if status_code == 404:
        return None

    if status_code != 200:
        logger.warning(
            "Payment service unavailable: status_code=%s url=%s payload=%s",
            status_code,
            url,
            payload,
        )
        raise DependencyError(
            "Payment service unavailable",
            details={"dependency": "payment-service"},
        )

    if payload is None:
        return None

    if not isinstance(payload, dict):
        logger.warning("Payment service returned non-dict payload: status_code=%s url=%s", status_code, url)
        raise DependencyError(
            "Payment service returned invalid payload",
            details={"dependency": "payment-service"},
        )

    return payload


def _fetch_eticket_by_hold(hold_id: str) -> tuple[str, dict[str, Any] | None]:
    base_url = str(current_app.config.get("OUTSYSTEMS_BASE_URL") or "").strip()
    if not base_url:
        return "disabled", None

    url = _join_url(base_url, f"/eticket/hold/{hold_id}")
    status_code, payload = _request_json(url)

    if status_code == 404:
        return "not_found", None

    if status_code != 200:
        logger.warning("OutSystems e-ticket dependency unavailable: status=%s url=%s", status_code, url)
        return "unavailable", None

    if payload is None or not isinstance(payload, dict):
        return "unavailable", None

    return "ok", payload


def _is_expired_terminal_hold(hold_status: str, inventory_hold: dict[str, Any]) -> bool:
    normalized_status = hold_status.upper()
    if normalized_status == "EXPIRED":
        return True

    if normalized_status != "RELEASED":
        return False

    release_reason = str(inventory_hold.get("releaseReason") or "").upper()
    if release_reason == RELEASE_REASON_PAYMENT_TIMEOUT:
        return True

    return bool(inventory_hold.get("expiredAt"))


def _build_booking_status_payload(hold_id: str, inventory_hold: dict[str, Any]) -> dict[str, Any]:
    hold_status = str(inventory_hold.get("holdStatus") or "UNKNOWN")
    normalized_hold_status = hold_status.upper()

    payload: dict[str, Any] = {
        "holdID": hold_id,
        "uiStatus": UI_STATUS_PROCESSING,
        "holdStatus": hold_status,
        "paymentStatus": None,
        "ticketStatus": None,
        "ticketID": None,
        "seatNumber": inventory_hold.get("seatNumber"),
        "amount": inventory_hold.get("amount"),
        "currency": inventory_hold.get("currency"),
        "holdExpiry": inventory_hold.get("holdExpiry"),
        "confirmedAt": inventory_hold.get("confirmedAt"),
        "expiredAt": inventory_hold.get("expiredAt"),
        "releasedAt": inventory_hold.get("releasedAt"),
        "transactionID": None,
        "paymentIntentID": None,
        "failureReason": None,
        "issuedAt": None,
        "fromWaitlist": inventory_hold.get("fromWaitlist"),
        "dependencyStatus": {
            "inventory": "ok",
            "payment": "pending",
            "eticket": "skipped",
        },
        "updatedAt": _latest_iso_timestamp(
            [
                inventory_hold.get("confirmedAt"),
                inventory_hold.get("expiredAt"),
                inventory_hold.get("releasedAt"),
                inventory_hold.get("holdExpiry"),
            ]
        ),
    }

    if _is_expired_terminal_hold(hold_status, inventory_hold):
        payload["uiStatus"] = UI_STATUS_EXPIRED
        payload["dependencyStatus"]["payment"] = "skipped"
        payload["dependencyStatus"]["eticket"] = "skipped"
        return payload

    payment = _fetch_payment_hold(hold_id)
    if not payment:
        payload["dependencyStatus"]["payment"] = "not_found"
        return payload

    payment_status = str(payment.get("paymentStatus") or "UNKNOWN")
    payload["paymentStatus"] = payment_status
    payload["transactionID"] = payment.get("transactionID")
    payload["paymentIntentID"] = payment.get("paymentIntentID")
    payload["failureReason"] = payment.get("failureReason")
    payload["dependencyStatus"]["payment"] = "ok"

    payload["updatedAt"] = _latest_iso_timestamp(
        [
            payload.get("updatedAt"),
            payment.get("createdAt"),
            payment.get("updatedAt"),
        ]
    )

    if payment_status == "FAILED":
        payload["uiStatus"] = UI_STATUS_FAILED_PAYMENT
        return payload

    if payment_status == "SUCCEEDED" and normalized_hold_status == "CONFIRMED":
        eticket_status, eticket = _fetch_eticket_by_hold(hold_id)
        payload["dependencyStatus"]["eticket"] = eticket_status

        if eticket:
            payload["ticketStatus"] = eticket.get("status")
            payload["ticketID"] = eticket.get("ticketID")
            payload["issuedAt"] = eticket.get("issuedAt")
            payload["seatNumber"] = eticket.get("seatNumber") or payload["seatNumber"]
            payload["updatedAt"] = _latest_iso_timestamp([payload.get("updatedAt"), eticket.get("issuedAt")])

            if eticket.get("ticketID"):
                payload["uiStatus"] = UI_STATUS_CONFIRMED
                return payload

        if bool(current_app.config.get("ALLOW_CONFIRMED_WITHOUT_TICKET", False)):
            payload["uiStatus"] = UI_STATUS_CONFIRMED
            return payload

        payload["uiStatus"] = UI_STATUS_PROCESSING
        return payload

    payload["dependencyStatus"]["eticket"] = "skipped"
    payload["uiStatus"] = UI_STATUS_PROCESSING
    return payload


@booking_status_bp.get("/health")
def health():
    return _api_response(
        {
            "status": "ok",
            "service": current_app.config.get("SERVICE_NAME", "booking-status-service"),
            "dependencies": {
                "inventoryConfigured": bool(current_app.config.get("INVENTORY_SERVICE_URL")),
                "paymentConfigured": bool(current_app.config.get("PAYMENT_SERVICE_URL")),
                "outsystemsConfigured": bool(str(current_app.config.get("OUTSYSTEMS_BASE_URL") or "").strip()),
            },
        }
    )


@booking_status_bp.get("/booking-status/<hold_id>")
def get_booking_status(hold_id: str):
    try:
        parsed_hold_id = _parse_hold_id(hold_id)
        hold = _fetch_inventory_hold(parsed_hold_id)
        payload = _build_booking_status_payload(parsed_hold_id, hold)
        return _api_response(payload, 200)
    except ApiError as error:
        return _json_error(error.message, error.status_code, _safe_error_details(error))
    except Exception as error:
        logger.exception("Unexpected error while resolving booking status: %s", error)
        return _json_error("Failed to resolve booking status", 500)


def _build_openapi_spec(base_url: str) -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "TicketBlitz Booking Status Service API",
            "version": "1.0.0",
            "description": "Composite read endpoint for booking status polling.",
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health check",
                    "responses": {
                        "200": {
                            "description": "Service health",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/booking-status/{hold_id}": {
                "get": {
                    "summary": "Resolve booking status by hold ID",
                    "parameters": [
                        {
                            "in": "path",
                            "name": "hold_id",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                            "description": "Seat hold ID",
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Booking status response",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/BookingStatusResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid hold ID",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Hold not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Dependency unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "HealthResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "service": {"type": "string"},
                        "dependencies": {"type": "object"},
                    },
                    "required": ["status", "service"],
                },
                "BookingStatusResponse": {
                    "type": "object",
                    "properties": {
                        "holdID": {"type": "string", "format": "uuid"},
                        "uiStatus": {
                            "type": "string",
                            "enum": [
                                UI_STATUS_PROCESSING,
                                UI_STATUS_CONFIRMED,
                                UI_STATUS_FAILED_PAYMENT,
                                UI_STATUS_EXPIRED,
                            ],
                        },
                        "holdStatus": {"type": "string"},
                        "paymentStatus": {"type": ["string", "null"]},
                        "ticketStatus": {"type": ["string", "null"]},
                        "ticketID": {"type": ["string", "null"]},
                        "seatNumber": {"type": ["string", "null"]},
                        "amount": {"type": ["number", "null"]},
                        "currency": {"type": ["string", "null"]},
                        "holdExpiry": {"type": ["string", "null"], "format": "date-time"},
                        "confirmedAt": {"type": ["string", "null"], "format": "date-time"},
                        "expiredAt": {"type": ["string", "null"], "format": "date-time"},
                        "releasedAt": {"type": ["string", "null"], "format": "date-time"},
                        "transactionID": {"type": ["string", "null"], "format": "uuid"},
                        "paymentIntentID": {"type": ["string", "null"]},
                        "failureReason": {"type": ["string", "null"]},
                        "issuedAt": {"type": ["string", "null"], "format": "date-time"},
                        "fromWaitlist": {"type": ["boolean", "null"]},
                        "dependencyStatus": {"type": "object"},
                        "updatedAt": {"type": ["string", "null"], "format": "date-time"},
                    },
                    "required": ["holdID", "uiStatus", "holdStatus"],
                },
                "ErrorResponse": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "details": {},
                    },
                    "required": ["error"],
                },
            }
        },
    }


def _build_swagger_ui_html(openapi_url: str) -> str:
    return """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>TicketBlitz Booking Status API Docs</title>
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
    app.register_blueprint(booking_status_bp)

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
