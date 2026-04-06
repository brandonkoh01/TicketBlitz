import logging
import os
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
from uuid import UUID

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

from shared.mq import publish_json, rabbitmq_configured

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


class DownstreamError(Exception):
    def __init__(self, service: str, status_code: int, message: str, details: Any = None):
        super().__init__(message)
        self.service = service
        self.status_code = status_code
        self.message = message
        self.details = details


class Config:
    def __init__(self):
        self.SERVICE_NAME = os.getenv("SERVICE_NAME", "flash-sale-orchestrator")
        self.EVENT_SERVICE_URL = os.getenv("EVENT_SERVICE_URL", "http://event-service:5000")
        self.INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:5000")
        self.WAITLIST_SERVICE_URL = os.getenv("WAITLIST_SERVICE_URL", "http://waitlist-service:5000")
        self.PRICING_SERVICE_URL = os.getenv("PRICING_SERVICE_URL", "http://pricing-service:5000")
        self.WAITLIST_SERVICE_AUTH_HEADER = os.getenv("WAITLIST_SERVICE_AUTH_HEADER", "X-Internal-Token")
        self.INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "")
        self.HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "12"))
        self.WAITLIST_FETCH_LIMIT = int(os.getenv("WAITLIST_FETCH_LIMIT", "200"))
        self.INTERNAL_AUTH_HEADER = os.getenv("INTERNAL_AUTH_HEADER", "X-Internal-Token")
        self.RECONCILE_INCLUDE_ENDED = str(os.getenv("RECONCILE_INCLUDE_ENDED", "1")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        try:
            self.RECONCILE_ENDED_WINDOW_MINUTES = max(
                1,
                int(os.getenv("RECONCILE_ENDED_WINDOW_MINUTES", "60")),
            )
        except ValueError:
            logger.warning("Invalid RECONCILE_ENDED_WINDOW_MINUTES, defaulting to 60")
            self.RECONCILE_ENDED_WINDOW_MINUTES = 60


def _json_error(message: str, status_code: int, details: Any = None):
    payload = {"error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


def _parse_uuid(value: Any, field_name: str) -> str:
    try:
        return str(UUID(str(value)))
    except Exception as error:
        raise ValueError(f"{field_name} must be a valid UUID") from error


def _parse_decimal_percentage(value: Any, field_name: str, minimum: Decimal, maximum: Decimal) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a numeric value") from error

    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")

    return parsed


def _parse_positive_int(value: Any, field_name: str, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer") from error

    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    if parsed > maximum:
        raise ValueError(f"{field_name} must be less than or equal to {maximum}")

    return parsed


def _request_json(
    method: str,
    service_name: str,
    base_url: str,
    path: str,
    *,
    expected_statuses: List[int],
    timeout_seconds: float,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            params=params,
            headers=headers,
            json=json_body,
            timeout=timeout_seconds,
        )
    except requests.Timeout as error:
        raise DownstreamError(service_name, 504, f"{service_name} request timed out") from error
    except requests.RequestException as error:
        raise DownstreamError(service_name, 503, f"{service_name} unavailable") from error

    try:
        body = response.json() if response.text else {}
    except ValueError:
        body = {}

    if response.status_code not in expected_statuses:
        message = body.get("error") if isinstance(body, dict) else None
        raise DownstreamError(
            service_name,
            response.status_code,
            message or f"{service_name} request failed",
            details=body if body else response.text,
        )

    if isinstance(body, dict):
        return body

    return {"data": body}


def _safe_waitlist_emails(config: Config, event_id: str) -> List[str]:
    if not config.INTERNAL_SERVICE_TOKEN:
        logger.warning("INTERNAL_SERVICE_TOKEN is not set. waitlist emails will be skipped")
        return []

    headers = {config.WAITLIST_SERVICE_AUTH_HEADER: config.INTERNAL_SERVICE_TOKEN}

    try:
        body = _request_json(
            "GET",
            "waitlist-service",
            config.WAITLIST_SERVICE_URL,
            "/waitlist",
            expected_statuses=[200],
            timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
            headers=headers,
            params={
                "eventID": event_id,
                "status": "WAITING",
                "includeEmail": "true",
                "limit": str(config.WAITLIST_FETCH_LIMIT),
            },
        )
    except DownstreamError as error:
        logger.warning(
            "Unable to load waitlist emails for event=%s: status=%s message=%s",
            event_id,
            error.status_code,
            error.message,
        )
        return []

    rows = body.get("entries") if isinstance(body, dict) else []
    if not isinstance(rows, list):
        return []

    unique: Dict[str, bool] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        email = row.get("email")
        if isinstance(email, str) and "@" in email:
            unique[email] = True

    return list(unique.keys())


def _publish_price_broadcast(payload: Dict[str, Any]) -> bool:
    if not rabbitmq_configured():
        logger.warning("RabbitMQ is not configured; skipped fanout publish")
        return False

    try:
        publish_json(
            routing_key="",
            payload=payload,
            exchange="ticketblitz.price",
            exchange_type="fanout",
        )
        return True
    except Exception as error:
        logger.exception("Failed to publish price broadcast: %s", error)
        return False


def _event_price_updates(updated_prices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "category_id": row.get("categoryID"),
            "new_price": row.get("newPrice"),
        }
        for row in updated_prices
        if row.get("categoryID") and row.get("newPrice") is not None
    ]


def _as_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    config = Config()

    @app.get("/health")
    def health():
        return (
            jsonify(
                {
                    "status": "ok",
                    "service": config.SERVICE_NAME,
                    "rabbitmqConfigured": rabbitmq_configured(),
                    "dependencies": {
                        "event": config.EVENT_SERVICE_URL,
                        "pricing": config.PRICING_SERVICE_URL,
                        "inventory": config.INVENTORY_SERVICE_URL,
                        "waitlist": config.WAITLIST_SERVICE_URL,
                    },
                }
            ),
            200,
        )

    def _require_internal_auth():
        if not config.INTERNAL_SERVICE_TOKEN:
            logger.error("INTERNAL_SERVICE_TOKEN must be configured for internal endpoints")
            return _json_error("Internal authentication is not configured", 503)

        provided = (request.headers.get(config.INTERNAL_AUTH_HEADER) or "").strip()
        if provided != config.INTERNAL_SERVICE_TOKEN:
            return _json_error("Unauthorised internal request", 401)

        return None

    def _execute_flash_sale_end(
        event_id: str,
        flash_sale_id: str,
        correlation_id: str,
        *,
        allow_non_active: bool,
    ) -> Dict[str, Any]:
        pricing_snapshot = _request_json(
            "GET",
            "pricing-service",
            config.PRICING_SERVICE_URL,
            f"/pricing/{event_id}",
            expected_statuses=[200],
            timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
        )

        categories = pricing_snapshot.get("categories", [])
        reverted_prices: List[Dict[str, Any]] = []
        updates: List[Dict[str, Any]] = []
        for row in categories:
            if not isinstance(row, dict):
                continue

            category_id = row.get("categoryID")
            current_price = row.get("currentPrice")
            base_price = row.get("basePrice")

            if not category_id or base_price is None:
                continue

            try:
                if _as_decimal(current_price) == _as_decimal(base_price):
                    continue
            except Exception:
                continue

            updates.append({"category_id": category_id, "new_price": str(base_price)})
            reverted_prices.append(
                {
                    "categoryID": category_id,
                    "category": row.get("category"),
                    "oldPrice": str(current_price),
                    "newPrice": str(base_price),
                    "currency": row.get("currency", "SGD"),
                }
            )

        if updates:
            _request_json(
                "PUT",
                "event-service",
                config.EVENT_SERVICE_URL,
                f"/event/{event_id}/categories/prices",
                expected_statuses=[200],
                timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
                json_body={
                    "reason": "REVERT",
                    "flashSaleID": flash_sale_id,
                    "changed_by": config.SERVICE_NAME,
                    "context": {
                        "operation": "FLASH_SALE_END",
                        "correlationID": correlation_id,
                    },
                    "updates": updates,
                },
            )

        _request_json(
            "PUT",
            "event-service",
            config.EVENT_SERVICE_URL,
            f"/event/{event_id}/status",
            expected_statuses=[200],
            timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
            json_body={"status": "ACTIVE"},
        )

        _request_json(
            "PUT",
            "inventory-service",
            config.INVENTORY_SERVICE_URL,
            f"/inventory/{event_id}/flash-sale",
            expected_statuses=[200],
            timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
            json_body={"active": False},
        )

        try:
            _request_json(
                "PUT",
                "pricing-service",
                config.PRICING_SERVICE_URL,
                f"/pricing/{flash_sale_id}/end",
                expected_statuses=[200],
                timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
            )
        except DownstreamError as error:
            if allow_non_active and error.service == "pricing-service" and error.status_code in (404, 409):
                return {
                    "status": "skipped",
                    "eventID": event_id,
                    "flashSaleID": flash_sale_id,
                    "reason": error.message,
                    "correlationID": correlation_id,
                }
            raise

        waitlist_emails = _safe_waitlist_emails(config, event_id)
        published = _publish_price_broadcast(
            {
                "type": "FLASH_SALE_ENDED",
                "eventID": event_id,
                "flashSaleID": flash_sale_id,
                "revertedPrices": reverted_prices,
                "waitlistEmails": waitlist_emails,
                "correlationID": correlation_id,
            }
        )

        return {
            "status": "success",
            "eventID": event_id,
            "flashSaleID": flash_sale_id,
            "revertedPrices": reverted_prices,
            "waitlistCount": len(waitlist_emails),
            "broadcastPublished": published,
            "correlationID": correlation_id,
        }

    @app.post("/flash-sale/launch")
    def launch_flash_sale():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _json_error("Request body must be a JSON object", 400)

        try:
            event_id = _parse_uuid(payload.get("eventID"), "eventID")
            discount_percentage = _parse_decimal_percentage(
                payload.get("discountPercentage"),
                "discountPercentage",
                Decimal("0.01"),
                Decimal("100"),
            )
            duration_minutes = _parse_positive_int(
                payload.get("durationMinutes"),
                "durationMinutes",
                24 * 7 * 4,
            )
            escalation_percentage = _parse_decimal_percentage(
                payload.get("escalationPercentage", "20"),
                "escalationPercentage",
                Decimal("0"),
                Decimal("500"),
            )
        except ValueError as error:
            return _json_error(str(error), 400)

        correlation_id = str(payload.get("correlationID") or uuid.uuid4())

        try:
            categories_snapshot = _request_json(
                "GET",
                "event-service",
                config.EVENT_SERVICE_URL,
                f"/event/{event_id}/categories",
                expected_statuses=[200],
                timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
            )
            categories = categories_snapshot.get("categories", [])

            pricing_response = _request_json(
                "POST",
                "pricing-service",
                config.PRICING_SERVICE_URL,
                "/pricing/flash-sale/configure",
                expected_statuses=[200],
                timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
                json_body={
                    "eventID": event_id,
                    "discountPercentage": str(discount_percentage),
                    "durationMinutes": duration_minutes,
                    "escalationPercentage": str(escalation_percentage),
                    "categories": categories,
                    "source": config.SERVICE_NAME,
                },
            )

            flash_sale_id = pricing_response.get("flashSaleID")
            updated_prices = pricing_response.get("updatedPrices", [])
            expires_at = pricing_response.get("expiresAt")

            _request_json(
                "PUT",
                "event-service",
                config.EVENT_SERVICE_URL,
                f"/event/{event_id}/status",
                expected_statuses=[200],
                timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
                json_body={"status": "FLASH_SALE_ACTIVE"},
            )

            updates = _event_price_updates(updated_prices)
            if updates:
                _request_json(
                    "PUT",
                    "event-service",
                    config.EVENT_SERVICE_URL,
                    f"/event/{event_id}/categories/prices",
                    expected_statuses=[200],
                    timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
                    json_body={
                        "reason": "FLASH_SALE",
                        "flashSaleID": flash_sale_id,
                        "changed_by": config.SERVICE_NAME,
                        "context": {
                            "operation": "FLASH_SALE_LAUNCH",
                            "correlationID": correlation_id,
                        },
                        "updates": updates,
                    },
                )

            _request_json(
                "PUT",
                "inventory-service",
                config.INVENTORY_SERVICE_URL,
                f"/inventory/{event_id}/flash-sale",
                expected_statuses=[200],
                timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
                json_body={
                    "active": True,
                    "flashSaleID": flash_sale_id,
                },
            )

            waitlist_emails = _safe_waitlist_emails(config, event_id)
            broadcast_payload = {
                "type": "FLASH_SALE_LAUNCHED",
                "eventID": event_id,
                "flashSaleID": flash_sale_id,
                "updatedPrices": updated_prices,
                "waitlistEmails": waitlist_emails,
                "expiresAt": expires_at,
                "correlationID": correlation_id,
            }
            published = _publish_price_broadcast(broadcast_payload)
        except DownstreamError as error:
            return _json_error(
                "Flash sale launch failed",
                error.status_code,
                {
                    "service": error.service,
                    "message": error.message,
                    "details": error.details,
                    "correlationID": correlation_id,
                },
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "eventID": event_id,
                    "flashSaleID": flash_sale_id,
                    "updatedPrices": updated_prices,
                    "expiresAt": expires_at,
                    "waitlistCount": len(waitlist_emails),
                    "broadcastPublished": published,
                    "correlationID": correlation_id,
                }
            ),
            200,
        )

    @app.post("/flash-sale/end")
    def end_flash_sale():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _json_error("Request body must be a JSON object", 400)

        try:
            event_id = _parse_uuid(payload.get("eventID"), "eventID")
            flash_sale_id = _parse_uuid(payload.get("flashSaleID"), "flashSaleID")
        except ValueError as error:
            return _json_error(str(error), 400)

        correlation_id = str(payload.get("correlationID") or uuid.uuid4())

        try:
            result = _execute_flash_sale_end(
                event_id,
                flash_sale_id,
                correlation_id,
                allow_non_active=False,
            )
        except DownstreamError as error:
            return _json_error(
                "Flash sale end failed",
                error.status_code,
                {
                    "service": error.service,
                    "message": error.message,
                    "details": error.details,
                    "correlationID": correlation_id,
                },
            )

        return jsonify(result), 200

    @app.post("/internal/flash-sale/reconcile-expired")
    def reconcile_expired_flash_sales():
        auth_error = _require_internal_auth()
        if auth_error:
            return auth_error

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _json_error("Request body must be a JSON object", 400)

        event_id = None
        if payload.get("eventID"):
            try:
                event_id = _parse_uuid(payload.get("eventID"), "eventID")
            except ValueError as error:
                return _json_error(str(error), 400)

        try:
            limit = _parse_positive_int(payload.get("limit", 50), "limit", 500)
        except ValueError as error:
            return _json_error(str(error), 400)

        correlation_id = str(payload.get("correlationID") or uuid.uuid4())
        params = {"limit": str(limit)}
        if event_id:
            params["eventID"] = event_id
        if config.RECONCILE_INCLUDE_ENDED:
            params["includeEnded"] = "1"
            params["endedWindowMinutes"] = str(config.RECONCILE_ENDED_WINDOW_MINUTES)

        try:
            candidates_response = _request_json(
                "GET",
                "pricing-service",
                config.PRICING_SERVICE_URL,
                "/pricing/flash-sales/expired",
                expected_statuses=[200],
                timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
                params=params,
            )
        except DownstreamError as error:
            return _json_error(
                "Failed to load expired flash sales",
                error.status_code,
                {
                    "service": error.service,
                    "message": error.message,
                    "details": error.details,
                    "correlationID": correlation_id,
                },
            )

        rows = candidates_response.get("flashSales", [])
        if not isinstance(rows, list):
            rows = []

        ended: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []

        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue

            try:
                row_event_id = _parse_uuid(row.get("eventID"), "eventID")
                row_flash_sale_id = _parse_uuid(row.get("flashSaleID"), "flashSaleID")
            except ValueError as error:
                failures.append(
                    {
                        "eventID": row.get("eventID"),
                        "flashSaleID": row.get("flashSaleID"),
                        "message": str(error),
                    }
                )
                continue

            row_correlation_id = f"{correlation_id}:{index + 1}"

            try:
                result = _execute_flash_sale_end(
                    row_event_id,
                    row_flash_sale_id,
                    row_correlation_id,
                    allow_non_active=True,
                )
            except DownstreamError as error:
                failures.append(
                    {
                        "eventID": row_event_id,
                        "flashSaleID": row_flash_sale_id,
                        "service": error.service,
                        "status": error.status_code,
                        "message": error.message,
                    }
                )
                continue

            if result.get("status") == "success":
                ended.append(
                    {
                        "eventID": row_event_id,
                        "flashSaleID": row_flash_sale_id,
                        "correlationID": row_correlation_id,
                    }
                )
            else:
                skipped.append(
                    {
                        "eventID": row_event_id,
                        "flashSaleID": row_flash_sale_id,
                        "reason": result.get("reason") or "Already ended",
                        "correlationID": row_correlation_id,
                    }
                )

        if failures:
            return _json_error(
                "Expired flash sale reconciliation failed",
                502,
                {
                    "candidateCount": len(rows),
                    "endedCount": len(ended),
                    "skippedCount": len(skipped),
                    "failedCount": len(failures),
                    "failures": failures,
                    "correlationID": correlation_id,
                },
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "candidateCount": len(rows),
                    "endedCount": len(ended),
                    "skippedCount": len(skipped),
                    "ended": ended,
                    "skipped": skipped,
                    "correlationID": correlation_id,
                }
            ),
            200,
        )

    @app.get("/flash-sale/<event_id>/status")
    def flash_sale_status(event_id: str):
        try:
            parsed_event_id = _parse_uuid(event_id, "eventID")
        except ValueError as error:
            return _json_error(str(error), 400)

        try:
            event_status = _request_json(
                "GET",
                "event-service",
                config.EVENT_SERVICE_URL,
                f"/event/{parsed_event_id}/flash-sale/status",
                expected_statuses=[200],
                timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
            )
        except DownstreamError as error:
            return _json_error(
                "Failed to load flash sale status",
                error.status_code,
                {
                    "service": error.service,
                    "message": error.message,
                    "details": error.details,
                },
            )

        active_pricing: Optional[Dict[str, Any]] = None
        try:
            active_pricing = _request_json(
                "GET",
                "pricing-service",
                config.PRICING_SERVICE_URL,
                f"/pricing/{parsed_event_id}/flash-sale/active",
                expected_statuses=[200],
                timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
            )
        except DownstreamError as error:
            if error.status_code != 404:
                logger.warning("Failed to fetch active pricing status: %s", error.message)

        return jsonify({"event": event_status, "pricing": active_pricing}), 200

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
