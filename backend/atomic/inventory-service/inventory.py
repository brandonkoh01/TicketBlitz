import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from flasgger import Swagger, swag_from
from flask import Flask, jsonify, request
from flask_cors import CORS

from shared.db import db_configured, get_db
from shared.mq import publish_json, rabbitmq_configured

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "inventory_openapi",
            "route": "/inventory/openapi.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/inventory/docs/",
}

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "TicketBlitz Inventory Service API",
        "description": "Inventory and hold lifecycle APIs for TicketBlitz.",
        "version": "1.0.0",
    },
    "basePath": "/",
    "schemes": ["http"],
    "tags": [
        {"name": "Inventory", "description": "Inventory and hold operations"},
        {"name": "System", "description": "Service health and diagnostics"},
    ],
    "definitions": {
        "ErrorResponse": {
            "type": "object",
            "properties": {"error": {"type": "string"}},
            "required": ["error"],
        },
        "HealthResponse": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "example": "ok"},
                "service": {"type": "string", "example": "inventory-service"},
                "supabaseConfigured": {"type": "boolean"},
                "rabbitmqConfigured": {"type": "boolean"},
            },
        },
        "InventoryAvailability": {
            "type": "object",
            "properties": {
                "eventID": {"type": "string", "format": "uuid"},
                "seatCategory": {"type": "string", "example": "CAT1"},
                "available": {"type": "integer", "example": 1},
                "status": {"type": "string", "example": "AVAILABLE"},
            },
        },
        "HoldResponse": {
            "type": "object",
            "properties": {
                "holdID": {"type": "string", "format": "uuid"},
                "seatID": {"type": "string", "format": "uuid"},
                "eventID": {"type": "string", "format": "uuid"},
                "categoryID": {"type": "string", "format": "uuid"},
                "userID": {"type": "string", "format": "uuid"},
                "holdStatus": {"type": "string", "example": "HELD"},
                "holdExpiry": {
                    "type": "string",
                    "example": "2026-04-02T12:00:00+00:00",
                },
                "amount": {"type": "number", "example": 160.0},
                "currency": {"type": "string", "example": "SGD"},
                "fromWaitlist": {"type": "boolean"},
                "seatCategory": {"type": "string", "example": "CAT1"},
                "seatNumber": {"type": "string", "example": "D12"},
                "seatStatus": {"type": "string", "example": "HELD"},
            },
        },
        "SeatStatusResponse": {
            "type": "object",
            "properties": {
                "seatID": {"type": "string", "format": "uuid"},
                "eventID": {"type": "string", "format": "uuid"},
                "seatCategory": {"type": "string", "example": "CAT1"},
                "seatNumber": {"type": "string", "example": "D12"},
                "status": {"type": "string", "example": "AVAILABLE"},
            },
        },
        "ExpireHoldsResponse": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "example": 0},
                "publishFailures": {"type": "integer", "example": 0},
                "publishFailureHoldIDs": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
                "expiredHolds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "holdID": {"type": "string", "format": "uuid"},
                            "seatID": {"type": "string", "format": "uuid"},
                            "eventID": {"type": "string", "format": "uuid"},
                            "seatCategory": {"type": "string", "example": "CAT1"},
                            "userID": {"type": "string", "format": "uuid"},
                        },
                    },
                },
            },
        },
        "FlashSaleStateResponse": {
            "type": "object",
            "properties": {
                "eventID": {"type": "string", "format": "uuid"},
                "flashSaleActive": {"type": "boolean"},
                "flashSaleID": {
                    "type": "string",
                    "format": "uuid",
                    "x-nullable": True,
                },
            },
        },
    },
}

HEALTH_SWAGGER = {
    "tags": ["System"],
    "summary": "Inventory service health check",
    "responses": {
        "200": {
            "description": "Service is reachable",
            "schema": {"$ref": "#/definitions/HealthResponse"},
        }
    },
}

FLASH_SALE_SWAGGER = {
    "tags": ["Inventory"],
    "summary": "Toggle flash-sale inventory state for an event",
    "parameters": [
        {
            "name": "event_id",
            "in": "path",
            "required": True,
            "type": "string",
            "format": "uuid",
            "description": "Event ID",
        },
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "active": {"type": "boolean"},
                    "flashSaleID": {"type": "string", "format": "uuid"},
                },
                "required": ["active"],
            },
        },
    ],
    "responses": {
        "200": {
            "description": "Flash-sale state updated",
            "schema": {"$ref": "#/definitions/FlashSaleStateResponse"},
        },
        "400": {
            "description": "Invalid payload",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "503": {
            "description": "Database unavailable",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
    },
}

GET_INVENTORY_SWAGGER = {
    "tags": ["Inventory"],
    "summary": "Get available seats for an event and category",
    "parameters": [
        {
            "name": "event_id",
            "in": "path",
            "required": True,
            "type": "string",
            "format": "uuid",
            "description": "Event ID",
        },
        {
            "name": "seat_category",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Seat category code (for example CAT1 or PEN)",
        },
    ],
    "responses": {
        "200": {
            "description": "Availability returned",
            "schema": {"$ref": "#/definitions/InventoryAvailability"},
        },
        "400": {
            "description": "Invalid path parameters",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "404": {
            "description": "Category not found",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "503": {
            "description": "Database unavailable",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
    },
}

CREATE_HOLD_SWAGGER = {
    "tags": ["Inventory"],
    "summary": "Create a seat hold",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "eventID": {"type": "string", "format": "uuid"},
                    "userID": {"type": "string", "format": "uuid"},
                    "seatCategory": {"type": "string"},
                    "qty": {"type": "integer", "default": 1},
                    "fromWaitlist": {"type": "boolean", "default": False},
                    "idempotencyKey": {"type": "string"},
                },
                "required": ["eventID", "userID", "seatCategory"],
            },
        }
    ],
    "responses": {
        "201": {
            "description": "Hold created",
            "schema": {"$ref": "#/definitions/HoldResponse"},
        },
        "200": {
            "description": "Idempotent replay result",
            "schema": {"$ref": "#/definitions/HoldResponse"},
        },
        "400": {
            "description": "Invalid payload",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "404": {
            "description": "Category not found",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "409": {
            "description": "Seat unavailable or hold conflict",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "503": {
            "description": "Database unavailable",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
    },
}

GET_HOLD_SWAGGER = {
    "tags": ["Inventory"],
    "summary": "Get hold details by hold ID",
    "parameters": [
        {
            "name": "hold_id",
            "in": "path",
            "required": True,
            "type": "string",
            "format": "uuid",
        }
    ],
    "responses": {
        "200": {
            "description": "Hold found",
            "schema": {"$ref": "#/definitions/HoldResponse"},
        },
        "400": {
            "description": "Invalid hold ID",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "404": {
            "description": "Hold not found",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
    },
}

CONFIRM_HOLD_SWAGGER = {
    "tags": ["Inventory"],
    "summary": "Confirm an existing HELD seat hold",
    "parameters": [
        {
            "name": "hold_id",
            "in": "path",
            "required": True,
            "type": "string",
            "format": "uuid",
        },
        {
            "name": "body",
            "in": "body",
            "required": False,
            "schema": {
                "type": "object",
                "properties": {
                    "correlationID": {"type": "string", "format": "uuid"}
                },
            },
        },
    ],
    "responses": {
        "200": {
            "description": "Hold confirmed or already confirmed",
            "schema": {"$ref": "#/definitions/HoldResponse"},
        },
        "400": {
            "description": "Invalid payload",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "404": {
            "description": "Hold not found",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "409": {
            "description": "Hold cannot be confirmed in current state",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
    },
}

RELEASE_HOLD_SWAGGER = {
    "tags": ["Inventory"],
    "summary": "Release a HELD seat hold",
    "parameters": [
        {
            "name": "hold_id",
            "in": "path",
            "required": True,
            "type": "string",
            "format": "uuid",
        },
        {
            "name": "body",
            "in": "body",
            "required": False,
            "schema": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "enum": [
                            "PAYMENT_TIMEOUT",
                            "CANCELLATION",
                            "MANUAL_RELEASE",
                            "SYSTEM_CLEANUP",
                        ],
                    }
                },
            },
        },
    ],
    "responses": {
        "200": {
            "description": "Hold released",
            "schema": {"$ref": "#/definitions/HoldResponse"},
        },
        "400": {
            "description": "Invalid payload",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "404": {
            "description": "Hold not found",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "409": {
            "description": "Hold cannot be released in current state",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
    },
}

UPDATE_SEAT_STATUS_SWAGGER = {
    "tags": ["Inventory"],
    "summary": "Update a seat status",
    "parameters": [
        {
            "name": "seat_id",
            "in": "path",
            "required": True,
            "type": "string",
            "format": "uuid",
        },
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["AVAILABLE", "PENDING_WAITLIST", "HELD", "SOLD"],
                    }
                },
                "required": ["status"],
            },
        },
    ],
    "responses": {
        "200": {
            "description": "Seat status updated",
            "schema": {"$ref": "#/definitions/SeatStatusResponse"},
        },
        "400": {
            "description": "Invalid payload",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "404": {
            "description": "Seat not found",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
        "409": {
            "description": "Invalid status transition",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
    },
}

EXPIRE_HOLDS_SWAGGER = {
    "tags": ["Inventory"],
    "summary": "Expire stale HELD holds and emit release events",
    "responses": {
        "200": {
            "description": "Expire-holds batch executed",
            "schema": {"$ref": "#/definitions/ExpireHoldsResponse"},
        },
        "503": {
            "description": "Database unavailable",
            "schema": {"$ref": "#/definitions/ErrorResponse"},
        },
    },
}

HOLD_DURATION_SECONDS = int(os.getenv("HOLD_DURATION_SECONDS", "600"))

VALID_RELEASE_REASONS = {
    "PAYMENT_TIMEOUT",
    "CANCELLATION",
    "MANUAL_RELEASE",
    "SYSTEM_CLEANUP",
}

VALID_SEAT_STATUSES = {
    "AVAILABLE",
    "PENDING_WAITLIST",
    "HELD",
    "SOLD",
}

ALLOWED_SEAT_TRANSITIONS = {
    "AVAILABLE": {"HELD", "PENDING_WAITLIST"},
    "PENDING_WAITLIST": {"HELD", "AVAILABLE"},
    "HELD": {"AVAILABLE", "PENDING_WAITLIST", "SOLD"},
    "SOLD": {"AVAILABLE", "PENDING_WAITLIST"},
}


def _error(message: str, status_code: int):
    return jsonify({"error": message}), status_code


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def _parse_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a UUID string")

    try:
        return str(uuid.UUID(value))
    except ValueError as error:
        raise ValueError(f"Invalid {field_name}") from error


def _parse_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False

    raise ValueError(f"{field_name} must be a boolean")


def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        normalized = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _is_expired(hold_expires_at: Any) -> bool:
    parsed = _parse_iso_timestamp(hold_expires_at)
    if parsed is None:
        return False
    return parsed <= datetime.now(timezone.utc)


def _fetch_category_by_code(event_id: str, seat_category: str) -> Optional[dict]:
    result = (
        get_db()
        .table("seat_categories")
        .select("category_id,category_code,current_price,currency,is_active")
        .eq("event_id", event_id)
        .eq("category_code", seat_category.upper())
        .limit(1)
        .execute()
    )

    data = result.data or []
    if not data:
        return None

    category = data[0]
    if not category.get("is_active", True):
        return None

    return category


def _fetch_category_by_id(category_id: str) -> Optional[dict]:
    result = (
        get_db()
        .table("seat_categories")
        .select("category_id,category_code,current_price,currency,is_active")
        .eq("category_id", category_id)
        .limit(1)
        .execute()
    )

    data = result.data or []
    return data[0] if data else None


def _fetch_hold(hold_id: str) -> Optional[dict]:
    result = (
        get_db()
        .table("seat_holds")
        .select(
            "hold_id,seat_id,event_id,category_id,user_id,from_waitlist,"
            "hold_expires_at,status,release_reason,amount,currency,idempotency_key,"
            "correlation_id,confirmed_at,released_at,expired_at,created_at"
        )
        .eq("hold_id", hold_id)
        .limit(1)
        .execute()
    )

    data = result.data or []
    return data[0] if data else None


def _fetch_seat(seat_id: str) -> Optional[dict]:
    result = (
        get_db()
        .table("seats")
        .select("seat_id,event_id,category_id,seat_number,status,sold_at")
        .eq("seat_id", seat_id)
        .limit(1)
        .execute()
    )

    data = result.data or []
    return data[0] if data else None


def _rpc(function_name: str, params: Optional[dict] = None) -> list[dict]:
    result = get_db().rpc(function_name, params or {}).execute()
    return result.data or []


def _hold_from_rpc_row(row: dict) -> dict:
    return {
        "hold_id": row.get("hold_id"),
        "seat_id": row.get("seat_id"),
        "event_id": row.get("event_id"),
        "category_id": row.get("category_id"),
        "user_id": row.get("user_id"),
        "from_waitlist": row.get("from_waitlist", False),
        "hold_expires_at": row.get("hold_expires_at"),
        "status": row.get("status"),
        "release_reason": row.get("release_reason"),
        "amount": row.get("amount"),
        "currency": row.get("currency"),
        "idempotency_key": row.get("idempotency_key"),
        "correlation_id": row.get("correlation_id"),
        "confirmed_at": row.get("confirmed_at"),
        "released_at": row.get("released_at"),
        "expired_at": row.get("expired_at"),
        "created_at": row.get("created_at"),
    }


def _publish_event(routing_key: str, payload: dict) -> bool:
    if not rabbitmq_configured():
        logger.warning(
            "RabbitMQ not configured, skipped publishing %s event", routing_key
        )
        return False

    try:
        publish_json(routing_key=routing_key, payload=payload, exchange="ticketblitz")
        return True
    except Exception as error:
        logger.exception("Failed to publish %s event: %s", routing_key, error)
        return False


def _build_hold_response(hold: dict) -> dict:
    seat = _fetch_seat(hold["seat_id"])
    category = _fetch_category_by_id(hold["category_id"])

    response = {
        "holdID": hold["hold_id"],
        "seatID": hold["seat_id"],
        "eventID": hold["event_id"],
        "categoryID": hold["category_id"],
        "userID": hold["user_id"],
        "holdStatus": hold["status"],
        "holdExpiry": hold["hold_expires_at"],
        "amount": _as_float(hold.get("amount")),
        "currency": hold.get("currency", "SGD"),
        "fromWaitlist": bool(hold.get("from_waitlist", False)),
        "correlationID": hold.get("correlation_id"),
        "confirmedAt": hold.get("confirmed_at"),
        "releasedAt": hold.get("released_at"),
        "expiredAt": hold.get("expired_at"),
    }

    if category:
        response["seatCategory"] = category.get("category_code")

    if seat:
        response["seatNumber"] = seat.get("seat_number")
        response["seatStatus"] = seat.get("status")

    return response


def _maybe_publish_category_sold_out(event_id: str, category_id: str) -> None:
    try:
        state_result = (
            get_db()
            .table("inventory_event_state")
            .select(
                "event_id,flash_sale_active,active_flash_sale_id,last_sold_out_category"
            )
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
    except Exception as error:
        logger.warning("Failed to load inventory event state: %s", error)
        return

    state_rows = state_result.data or []
    if not state_rows:
        return

    state = state_rows[0]
    if not state.get("flash_sale_active"):
        return

    category = _fetch_category_by_id(category_id)
    if not category:
        return

    category_code = category.get("category_code")
    if not category_code:
        return

    if state.get("last_sold_out_category") == category_code:
        return

    try:
        remaining = (
            get_db()
            .table("seats")
            .select("seat_id")
            .eq("event_id", event_id)
            .eq("category_id", category_id)
            .neq("status", "SOLD")
            .limit(1)
            .execute()
        )
    except Exception as error:
        logger.warning("Failed to evaluate sold-out category: %s", error)
        return

    if remaining.data:
        return

    sold_at = _utc_now_iso()
    payload = {
        "eventID": event_id,
        "category": category_code,
        "flashSaleID": state.get("active_flash_sale_id"),
        "soldAt": sold_at,
    }
    _publish_event("category.sold_out", payload)

    try:
        (
            get_db()
            .table("inventory_event_state")
            .update(
                {
                    "last_sold_out_category": category_code,
                    "last_sold_out_at": sold_at,
                }
            )
            .eq("event_id", event_id)
            .execute()
        )
    except Exception as error:
        logger.warning("Failed to persist sold-out metadata: %s", error)


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)

    @app.get("/health")
    @swag_from(HEALTH_SWAGGER)
    def health():
        return (
            jsonify(
                {
                    "status": "ok",
                    "service": os.getenv("SERVICE_NAME", "inventory-service"),
                    "supabaseConfigured": db_configured(),
                    "rabbitmqConfigured": rabbitmq_configured(),
                }
            ),
            200,
        )

    @app.put("/inventory/<event_id>/flash-sale")
    @swag_from(FLASH_SALE_SWAGGER)
    def set_flash_sale_state(event_id: str):
        if not db_configured():
            return _error("Supabase is not configured", 503)

        try:
            event_id = _parse_uuid(event_id, "eventID")
        except ValueError as error:
            return _error(str(error), 400)

        payload = request.get_json(silent=True) or {}

        try:
            active = _parse_bool(payload.get("active"), "active")
        except ValueError as error:
            return _error(str(error), 400)

        flash_sale_id = payload.get("flashSaleID")
        if flash_sale_id is not None:
            try:
                flash_sale_id = _parse_uuid(flash_sale_id, "flashSaleID")
            except ValueError as error:
                return _error(str(error), 400)

        if active and not flash_sale_id:
            return _error("flashSaleID is required when active is true", 400)

        update_payload = {
            "event_id": event_id,
            "flash_sale_active": active,
            "active_flash_sale_id": flash_sale_id if active else None,
            "updated_at": _utc_now_iso(),
        }

        try:
            result = (
                get_db()
                .table("inventory_event_state")
                .upsert(update_payload, on_conflict="event_id")
                .execute()
            )
        except Exception as error:
            logger.exception("Failed to update flash sale state: %s", error)
            return _error("Failed to update flash sale state", 500)

        row = (result.data or [update_payload])[0]
        return (
            jsonify(
                {
                    "eventID": row.get("event_id", event_id),
                    "flashSaleActive": bool(row.get("flash_sale_active", active)),
                    "flashSaleID": row.get("active_flash_sale_id"),
                }
            ),
            200,
        )

    @app.get("/inventory/<event_id>/<seat_category>")
    @swag_from(GET_INVENTORY_SWAGGER)
    def get_inventory(event_id: str, seat_category: str):
        if not db_configured():
            return _error("Supabase is not configured", 503)

        try:
            event_id = _parse_uuid(event_id, "eventID")
        except ValueError as error:
            return _error(str(error), 400)

        category_name = seat_category.upper()

        try:
            category = _fetch_category_by_code(event_id, category_name)
        except Exception as error:
            logger.exception("Failed to load category: %s", error)
            return _error("Failed to load inventory", 500)

        if not category:
            return _error("Category not found for event", 404)

        try:
            seats_result = (
                get_db()
                .table("seats")
                .select("seat_id")
                .eq("event_id", event_id)
                .eq("category_id", category["category_id"])
                .eq("status", "AVAILABLE")
                .execute()
            )
        except Exception as error:
            logger.exception("Failed to load inventory seats: %s", error)
            return _error("Failed to load inventory", 500)

        available = len(seats_result.data or [])
        availability_status = "AVAILABLE" if available > 0 else "SOLD_OUT"

        return (
            jsonify(
                {
                    "eventID": event_id,
                    "seatCategory": category_name,
                    "available": available,
                    "status": availability_status,
                }
            ),
            200,
        )

    @app.post("/inventory/hold")
    @swag_from(CREATE_HOLD_SWAGGER)
    def create_hold():
        if not db_configured():
            return _error("Supabase is not configured", 503)

        payload = request.get_json(silent=True) or {}

        try:
            event_id = _parse_uuid(payload.get("eventID"), "eventID")
            user_id = _parse_uuid(payload.get("userID"), "userID")
        except ValueError as error:
            return _error(str(error), 400)

        seat_category = payload.get("seatCategory")
        if not isinstance(seat_category, str) or not seat_category.strip():
            return _error("seatCategory is required", 400)

        qty = payload.get("qty", 1)
        if qty != 1:
            return _error("Only qty=1 is supported", 400)

        try:
            from_waitlist = _parse_bool(payload.get("fromWaitlist", False), "fromWaitlist")
        except ValueError as error:
            return _error(str(error), 400)

        idempotency_key = payload.get("idempotencyKey")
        if idempotency_key is not None and not isinstance(idempotency_key, str):
            return _error("idempotencyKey must be a string", 400)

        seat_category = seat_category.strip().upper()
        if idempotency_key is not None:
            normalized_key = idempotency_key.strip()
            idempotency_key = normalized_key if normalized_key else None

        try:
            rows = _rpc(
                "inventory_create_hold",
                {
                    "p_event_id": event_id,
                    "p_user_id": user_id,
                    "p_seat_category": seat_category,
                    "p_from_waitlist": from_waitlist,
                    "p_hold_duration_seconds": HOLD_DURATION_SECONDS,
                    "p_idempotency_key": idempotency_key,
                },
            )
        except Exception as error:
            logger.exception("Failed to create hold via RPC: %s", error)
            return _error("Failed to place hold", 500)

        if not rows:
            return _error("Failed to place hold", 500)

        row = rows[0]
        outcome = row.get("outcome")

        if outcome == "CATEGORY_NOT_FOUND":
            return _error("Category not found for event", 404)

        if outcome == "NO_SEAT_AVAILABLE":
            return _error("No seat available for hold", 409)

        if outcome == "IDEMPOTENCY_KEY_CONFLICT":
            return _error(
                "idempotencyKey was already used for a different user or event",
                409,
            )

        if outcome in {"CREATED", "IDEMPOTENT"}:
            hold = _hold_from_rpc_row(row)
            status_code = 201 if outcome == "CREATED" else 200
            return jsonify(_build_hold_response(hold)), status_code

        logger.warning("Unexpected create hold outcome: %s", outcome)
        return _error("Failed to place hold", 500)

    @app.get("/inventory/hold/<hold_id>")
    @swag_from(GET_HOLD_SWAGGER)
    def get_hold(hold_id: str):
        if not db_configured():
            return _error("Supabase is not configured", 503)

        try:
            hold_id = _parse_uuid(hold_id, "holdID")
        except ValueError as error:
            return _error(str(error), 400)

        try:
            hold = _fetch_hold(hold_id)
        except Exception as error:
            logger.exception("Failed to fetch hold: %s", error)
            return _error("Failed to load hold", 500)

        if not hold:
            return _error("Hold not found", 404)

        return jsonify(_build_hold_response(hold)), 200

    @app.put("/inventory/hold/<hold_id>/confirm")
    @swag_from(CONFIRM_HOLD_SWAGGER)
    def confirm_hold(hold_id: str):
        if not db_configured():
            return _error("Supabase is not configured", 503)

        try:
            hold_id = _parse_uuid(hold_id, "holdID")
        except ValueError as error:
            return _error(str(error), 400)

        payload = request.get_json(silent=True) or {}
        correlation_id = payload.get("correlationID")
        if correlation_id is not None:
            try:
                correlation_id = _parse_uuid(correlation_id, "correlationID")
            except ValueError as error:
                return _error(str(error), 400)

        try:
            rows = _rpc(
                "inventory_confirm_hold",
                {
                    "p_hold_id": hold_id,
                    "p_correlation_id": correlation_id,
                },
            )
        except Exception as error:
            logger.exception("Failed to confirm hold via RPC: %s", error)
            return _error("Failed to confirm hold", 500)

        if not rows:
            return _error("Failed to confirm hold", 500)

        row = rows[0]
        outcome = row.get("outcome")

        if outcome == "HOLD_NOT_FOUND":
            return _error("Hold not found", 404)

        hold = _hold_from_rpc_row(row)

        if outcome in {"INVALID_STATUS", "HOLD_EXPIRED", "SEAT_CONFLICT", "HOLD_CONFLICT"}:
            if outcome == "HOLD_EXPIRED":
                return _error("Hold already expired", 409)
            if outcome == "INVALID_STATUS":
                return _error("Hold is not in HELD state", 409)
            return _error("Seat is no longer confirmable", 409)

        if outcome == "CONFIRMED":
            _maybe_publish_category_sold_out(hold["event_id"], hold["category_id"])

        if outcome in {"CONFIRMED", "ALREADY_CONFIRMED"}:
            return jsonify(_build_hold_response(hold)), 200

        logger.warning("Unexpected confirm hold outcome: %s", outcome)
        return _error("Failed to confirm hold", 500)

    @app.put("/inventory/hold/<hold_id>/release")
    @swag_from(RELEASE_HOLD_SWAGGER)
    def release_hold(hold_id: str):
        if not db_configured():
            return _error("Supabase is not configured", 503)

        try:
            hold_id = _parse_uuid(hold_id, "holdID")
        except ValueError as error:
            return _error(str(error), 400)

        payload = request.get_json(silent=True) or {}
        reason = str(payload.get("reason", "MANUAL_RELEASE")).upper()
        if reason not in VALID_RELEASE_REASONS:
            return _error("Invalid release reason", 400)

        try:
            rows = _rpc(
                "inventory_release_hold",
                {
                    "p_hold_id": hold_id,
                    "p_reason": reason,
                },
            )
        except Exception as error:
            logger.exception("Failed to release hold via RPC: %s", error)
            return _error("Failed to release hold", 500)

        if not rows:
            return _error("Failed to release hold", 500)

        row = rows[0]
        outcome = row.get("outcome")

        if outcome == "HOLD_NOT_FOUND":
            return _error("Hold not found", 404)

        hold = _hold_from_rpc_row(row)

        if outcome in {"INVALID_STATUS", "SEAT_CONFLICT", "HOLD_CONFLICT"}:
            if outcome == "INVALID_STATUS":
                return _error("Hold is not in HELD state", 409)
            return _error("Seat is not releasable", 409)

        if outcome not in {"RELEASED", "ALREADY_RELEASED"}:
            logger.warning("Unexpected release hold outcome: %s", outcome)
            return _error("Failed to release hold", 500)

        category = _fetch_category_by_id(hold["category_id"])
        seat_category = category.get("category_code") if category else None

        if outcome == "RELEASED":
            publish_payload = {
                "eventID": hold["event_id"],
                "seatCategory": seat_category,
                "seatID": hold["seat_id"],
                "qty": 1,
                "reason": hold.get("release_reason") or reason,
            }
            if (hold.get("release_reason") or reason) == "PAYMENT_TIMEOUT":
                publish_payload["expiredHoldID"] = hold["hold_id"]

            _publish_event("seat.released", publish_payload)

        return jsonify(_build_hold_response(hold)), 200

    @app.put("/inventory/seat/<seat_id>/status")
    @swag_from(UPDATE_SEAT_STATUS_SWAGGER)
    def update_seat_status(seat_id: str):
        if not db_configured():
            return _error("Supabase is not configured", 503)

        try:
            seat_id = _parse_uuid(seat_id, "seatID")
        except ValueError as error:
            return _error(str(error), 400)

        payload = request.get_json(silent=True) or {}
        target_status = payload.get("status")
        if not isinstance(target_status, str):
            return _error("status is required", 400)

        target_status = target_status.upper()
        if target_status not in VALID_SEAT_STATUSES:
            return _error("Invalid seat status", 400)

        try:
            seat = _fetch_seat(seat_id)
        except Exception as error:
            logger.exception("Failed to load seat: %s", error)
            return _error("Failed to update seat status", 500)

        if not seat:
            return _error("Seat not found", 404)

        current_status = seat["status"]
        if target_status == current_status:
            category = _fetch_category_by_id(seat["category_id"])
            return (
                jsonify(
                    {
                        "seatID": seat["seat_id"],
                        "eventID": seat["event_id"],
                        "seatCategory": category.get("category_code") if category else None,
                        "seatNumber": seat.get("seat_number"),
                        "status": current_status,
                    }
                ),
                200,
            )

        if target_status not in ALLOWED_SEAT_TRANSITIONS.get(current_status, set()):
            return _error(
                f"Invalid seat status transition from {current_status} to {target_status}",
                409,
            )

        update_payload = {"status": target_status}
        # Keep sold_at consistent with seats_sold_at_chk:
        # SOLD requires a timestamp; all other statuses require null.
        if target_status == "SOLD":
            update_payload["sold_at"] = _utc_now_iso()
        else:
            update_payload["sold_at"] = None

        try:
            seat_update = (
                get_db()
                .table("seats")
                .update(update_payload)
                .eq("seat_id", seat_id)
                .eq("status", current_status)
                .execute()
            )
        except Exception as error:
            logger.exception("Failed to update seat status: %s", error)
            return _error("Failed to update seat status", 500)

        updated_rows = seat_update.data or []
        if not updated_rows:
            return _error("Seat update conflicted with another update", 409)

        updated = updated_rows[0]
        category = _fetch_category_by_id(updated["category_id"])
        return (
            jsonify(
                {
                    "seatID": updated["seat_id"],
                    "eventID": updated["event_id"],
                    "seatCategory": category.get("category_code") if category else None,
                    "seatNumber": updated.get("seat_number"),
                    "status": updated["status"],
                }
            ),
            200,
        )

    @app.post("/inventory/maintenance/expire-holds")
    @swag_from(EXPIRE_HOLDS_SWAGGER)
    def expire_holds():
        if not db_configured():
            return _error("Supabase is not configured", 503)

        try:
            rows = _rpc("inventory_expire_holds", {"p_limit": 200})
        except Exception as error:
            logger.exception("Failed to expire holds via RPC: %s", error)
            return _error("Failed to expire holds", 500)

        if not rows:
            return jsonify({"expiredHolds": [], "count": 0, "publishFailures": 0}), 200

        category_cache: dict[str, Optional[str]] = {}

        def category_code_for(category_id: str) -> Optional[str]:
            if category_id in category_cache:
                return category_cache[category_id]
            category = _fetch_category_by_id(category_id)
            code = category.get("category_code") if category else None
            category_cache[category_id] = code
            return code

        expired: list[dict] = []
        publish_failures = 0
        publish_failure_hold_ids: list[str] = []

        for row in rows:
            if row.get("outcome") != "EXPIRED":
                continue

            hold = _hold_from_rpc_row(row)

            seat_category = category_code_for(hold["category_id"])
            published = _publish_event(
                "seat.released",
                {
                    "eventID": hold["event_id"],
                    "seatCategory": seat_category,
                    "seatID": hold["seat_id"],
                    "qty": 1,
                    "reason": "PAYMENT_TIMEOUT",
                    "expiredHoldID": hold["hold_id"],
                },
            )

            if not published:
                publish_failures += 1
                publish_failure_hold_ids.append(str(hold["hold_id"]))

            expired.append(
                {
                    "holdID": hold["hold_id"],
                    "seatID": hold["seat_id"],
                    "eventID": hold["event_id"],
                    "seatCategory": seat_category,
                    "userID": hold["user_id"],
                }
            )

        response_payload: dict[str, Any] = {
            "expiredHolds": expired,
            "count": len(expired),
            "publishFailures": publish_failures,
        }

        if publish_failure_hold_ids:
            response_payload["publishFailureHoldIDs"] = publish_failure_hold_ids

        return jsonify(response_payload), 200

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
