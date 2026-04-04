import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger

from shared.db import db_configured, get_db
from shared.mq import publish_json, rabbitmq_configured

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

EVENT_STATUSES = {
    "SCHEDULED",
    "ACTIVE",
    "FLASH_SALE_ACTIVE",
    "CANCELLED",
    "COMPLETED",
}

PRICE_CHANGE_REASONS = {
    "FLASH_SALE",
    "ESCALATION",
    "REVERT",
    "MANUAL_ADJUSTMENT",
}

ALLOWED_STATUS_TRANSITIONS = {
    "SCHEDULED": {"ACTIVE", "CANCELLED"},
    "ACTIVE": {"FLASH_SALE_ACTIVE", "CANCELLED", "COMPLETED"},
    "FLASH_SALE_ACTIVE": {"ACTIVE", "CANCELLED", "COMPLETED"},
    "CANCELLED": set(),
    "COMPLETED": set(),
}

TERMINAL_EVENT_STATUSES = {"CANCELLED", "COMPLETED"}


def error_response(message: str, status_code: int, details: Optional[Any] = None):
    payload: Dict[str, Any] = {"error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


def parse_json_object_body() -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[Any, int]]]:
    if not request.is_json:
        return None, error_response("Content-Type must be application/json", 415)

    payload = request.get_json(silent=True)
    if payload is None:
        return None, error_response("Malformed JSON payload", 400)

    if not isinstance(payload, dict):
        return None, error_response("JSON body must be an object", 422)

    return payload, None


def parse_uuid(value: str, field_name: str) -> Tuple[Optional[str], Optional[Tuple[Any, int]]]:
    try:
        parsed = UUID(value)
    except (ValueError, TypeError):
        return None, error_response(f"Invalid {field_name}", 400)
    return str(parsed), None


def parse_decimal(value: Any) -> Tuple[Optional[str], Optional[Tuple[Any, int]]]:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None, error_response("Invalid price value", 422)

    if decimal_value < 0:
        return None, error_response("Price must be non-negative", 422)

    return str(decimal_value.quantize(Decimal("0.01"))), None


def require_db() -> Optional[Tuple[Any, int]]:
    if db_configured():
        return None
    return error_response("Supabase is not configured", 503)


def fetch_event(event_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[Any, int]]]:
    try:
        result = (
            get_db()
            .table("events")
            .select(
                "event_id,event_code,name,description,venue,event_date,booking_opens_at,"
                "booking_closes_at,total_capacity,status,metadata,created_at,updated_at,deleted_at"
            )
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
    except Exception as error:
        logger.exception("Failed to load event %s: %s", event_id, error)
        return None, error_response("Failed to load event", 500)

    records = result.data or []
    if not records or records[0].get("deleted_at") is not None:
        return None, error_response("Event not found", 404)

    return records[0], None


def record_integration_event(
    routing_key: str,
    event_name: str,
    payload: Dict[str, Any],
    aggregate_type: str,
    aggregate_id: str,
    exchange_name: str = "ticketblitz",
) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[Any, int]]]:
    row = {
        "producer_service": os.getenv("SERVICE_NAME", "event-service"),
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "event_name": event_name,
        "exchange_name": exchange_name,
        "routing_key": routing_key,
        "payload": payload,
        "headers": {},
        "published": False,
    }

    try:
        result = get_db().table("integration_events").insert(row).execute()
    except Exception as error:
        logger.exception("Failed to record integration event %s: %s", event_name, error)
        return None, error_response("Failed to persist integration event", 500)

    rows = result.data or []
    if not rows:
        return None, error_response("Failed to persist integration event", 500)

    return rows[0], None


def update_integration_event_publish_state(
    integration_event: Dict[str, Any],
    published: bool,
    publish_error: Optional[str] = None,
) -> Optional[str]:
    update_payload: Dict[str, Any] = {
        "published": published,
        "publish_error": publish_error,
    }
    if published:
        update_payload["published_at"] = datetime.now(timezone.utc).isoformat()

    try:
        query = (
            get_db()
            .table("integration_events")
            .update(update_payload)
            .eq("event_id", integration_event.get("event_id"))
        )

        occurred_at = integration_event.get("occurred_at")
        if occurred_at:
            query = query.eq("occurred_at", occurred_at)

        query.execute()
        return None
    except Exception as error:
        logger.warning("Failed to update integration event publish state: %s", error)
        return str(error)


def delete_integration_event(integration_event: Optional[Dict[str, Any]]) -> bool:
    if not integration_event:
        return True

    event_id = integration_event.get("event_id")
    occurred_at = integration_event.get("occurred_at")
    if not event_id or not occurred_at:
        logger.warning("Cannot delete integration event due to missing event_id or occurred_at")
        return False

    try:
        (
            get_db()
            .table("integration_events")
            .delete()
            .eq("event_id", event_id)
            .eq("occurred_at", occurred_at)
            .execute()
        )
        return True
    except Exception as error:
        logger.warning("Failed to delete integration event %s/%s: %s", event_id, occurred_at, error)
        return False


def rollback_event_status(event_id: str, previous_status: str) -> bool:
    try:
        (
            get_db()
            .table("events")
            .update({"status": previous_status})
            .eq("event_id", event_id)
            .execute()
        )
        return True
    except Exception as error:
        logger.warning(
            "Failed to rollback event status for event %s to %s: %s",
            event_id,
            previous_status,
            error,
        )
        return False


def rollback_category_prices(event_id: str, old_prices: Dict[str, str]) -> List[str]:
    failed_category_ids: List[str] = []
    for category_id, old_price in old_prices.items():
        try:
            (
                get_db()
                .table("seat_categories")
                .update({"current_price": old_price})
                .eq("category_id", category_id)
                .eq("event_id", event_id)
                .execute()
            )
        except Exception as error:
            logger.warning(
                "Failed to rollback price for category %s on event %s: %s",
                category_id,
                event_id,
                error,
            )
            failed_category_ids.append(category_id)

    return failed_category_ids


def delete_price_change_records(change_ids: List[str]) -> List[str]:
    failed_change_ids: List[str] = []
    for change_id in change_ids:
        try:
            get_db().table("price_changes").delete().eq("change_id", change_id).execute()
        except Exception as error:
            logger.warning("Failed to delete price_change %s during rollback: %s", change_id, error)
            failed_change_ids.append(change_id)

    return failed_change_ids


def publish_with_outbox(
    routing_key: str,
    event_name: str,
    payload: Dict[str, Any],
    aggregate_type: str,
    aggregate_id: str,
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str], int]:
    if not rabbitmq_configured():
        return False, None, "RabbitMQ is not configured", 503

    integration_event, integration_error = record_integration_event(
        routing_key=routing_key,
        event_name=event_name,
        payload=payload,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
    )
    if integration_error:
        return False, None, "Failed to persist integration event", 500

    try:
        publish_json(routing_key=routing_key, payload=payload, exchange="ticketblitz")
    except Exception as error:
        publish_warning = f"RabbitMQ publish failed: {error}"
        logger.warning("Failed to publish MQ event %s: %s", routing_key, error)
        update_integration_event_publish_state(
            integration_event,
            published=False,
            publish_error=publish_warning,
        )
        return False, integration_event, publish_warning, 503

    update_error = update_integration_event_publish_state(integration_event, published=True)
    if update_error:
        return (
            False,
            integration_event,
            f"Failed to finalize integration event publish state: {update_error}",
            500,
        )

    return True, integration_event, None, 200


def normalize_price_updates(payload: Dict[str, Any]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Tuple[Any, int]]]:
    updates = payload.get("updates")
    if not isinstance(updates, list) or not updates:
        return None, error_response("Field 'updates' must be a non-empty list", 422)

    normalized: List[Dict[str, Any]] = []
    seen_ids = set()

    for update in updates:
        if not isinstance(update, dict):
            return None, error_response("Each update must be an object", 422)

        category_id_raw = update.get("category_id") or update.get("categoryID")
        new_price_raw = update.get("new_price")
        if new_price_raw is None:
            new_price_raw = update.get("newPrice")

        if not category_id_raw:
            return None, error_response("Each update requires category_id", 422)

        category_id, category_error = parse_uuid(category_id_raw, "category_id")
        if category_error:
            return None, category_error

        if category_id in seen_ids:
            return None, error_response("Duplicate category_id in updates", 422)
        seen_ids.add(category_id)

        if new_price_raw is None:
            return None, error_response("Each update requires new_price", 422)

        new_price, price_error = parse_decimal(new_price_raw)
        if price_error:
            return None, price_error

        normalized.append(
            {
                "category_id": category_id,
                "new_price": new_price,
            }
        )

    return normalized, None


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    app.config["SWAGGER"] = {
        "title": "TicketBlitz Event Service API",
        "uiversion": 3,
        "specs_route": "/apidocs/",
    }
    Swagger(
        app,
        template={
            "swagger": "2.0",
            "info": {
                "title": "TicketBlitz Event Service API",
                "description": "Read and organiser update endpoints for event metadata and pricing.",
                "version": "1.0.0",
            },
            "basePath": "/",
            "schemes": ["http"],
            "securityDefinitions": {
                "OrganiserApiKey": {
                    "type": "apiKey",
                    "name": "x-organiser-api-key",
                    "in": "header",
                    "description": "Required for mutating organiser endpoints routed via Kong.",
                }
            },
        },
    )

    @app.get("/health")
    def health():
        """Service health probe.
        ---
        tags:
          - Health
        responses:
          200:
            description: Service health status and dependency configuration flags.
        """
        return (
            jsonify(
                {
                    "status": "ok",
                    "service": os.getenv("SERVICE_NAME", "event-service"),
                    "supabaseConfigured": db_configured(),
                    "rabbitmqConfigured": rabbitmq_configured(),
                }
            ),
            200,
        )

    @app.get("/events")
    def list_events():
        """List active events.
        ---
        tags:
          - Events
        responses:
          200:
            description: List of events ordered by date.
          503:
            description: Database is not configured.
        """
        db_error = require_db()
        if db_error:
            return db_error

        events = []

        try:
            result = (
                get_db()
                .table("events")
                .select("event_id,event_code,name,venue,event_date,status,deleted_at")
                .order("event_date")
                .limit(100)
                .execute()
            )
            rows = result.data or []
            events = [
                {
                    "event_id": row.get("event_id"),
                    "event_code": row.get("event_code"),
                    "name": row.get("name"),
                    "venue": row.get("venue"),
                    "event_date": row.get("event_date"),
                    "status": row.get("status"),
                }
                for row in rows
                if row.get("deleted_at") is None
            ]
        except Exception as error:
            logger.exception("Failed to load events from Supabase: %s", error)
            return error_response("Failed to load events", 500)

        return jsonify({"events": events}), 200

    @app.get("/event/<event_id>")
    def get_event(event_id: str):
        """Get one event by ID.
        ---
        tags:
          - Events
        parameters:
          - name: event_id
            in: path
            required: true
            type: string
            format: uuid
        responses:
          200:
            description: Event record.
          400:
            description: Invalid event identifier.
          404:
            description: Event not found.
        """
        db_error = require_db()
        if db_error:
            return db_error

        parsed_event_id, parse_error = parse_uuid(event_id, "eventID")
        if parse_error:
            return parse_error

        event, fetch_error = fetch_event(parsed_event_id)
        if fetch_error:
            return fetch_error

        event.pop("deleted_at", None)
        return jsonify(event), 200

    @app.get("/event/<event_id>/categories")
    def list_event_categories(event_id: str):
        """List categories for an event.
        ---
        tags:
          - Categories
        parameters:
          - name: event_id
            in: path
            required: true
            type: string
            format: uuid
        responses:
          200:
            description: Event category pricing snapshot.
          404:
            description: Event not found.
        """
        db_error = require_db()
        if db_error:
            return db_error

        parsed_event_id, parse_error = parse_uuid(event_id, "eventID")
        if parse_error:
            return parse_error

        _event, fetch_error = fetch_event(parsed_event_id)
        if fetch_error:
            return fetch_error

        try:
            result = (
                get_db()
                .table("seat_categories")
                .select(
                    "category_id,event_id,category_code,name,base_price,current_price,"
                    "currency,total_seats,is_active,sort_order,metadata,deleted_at"
                )
                .eq("event_id", parsed_event_id)
                .order("sort_order")
                .execute()
            )
        except Exception as error:
            logger.exception("Failed to load categories for event %s: %s", parsed_event_id, error)
            return error_response("Failed to load categories", 500)

        categories = [
            row
            for row in (result.data or [])
            if row.get("deleted_at") is None
        ]
        for category in categories:
            category.pop("deleted_at", None)

        return jsonify({"event_id": parsed_event_id, "categories": categories}), 200

    @app.get("/event/<event_id>/flash-sale/status")
    def get_flash_sale_status(event_id: str):
        """Get active flash sale status for an event.
        ---
        tags:
          - Flash Sale
        parameters:
          - name: event_id
            in: path
            required: true
            type: string
            format: uuid
        responses:
          200:
            description: Flash sale and inventory state details.
          404:
            description: Event not found.
        """
        db_error = require_db()
        if db_error:
            return db_error

        parsed_event_id, parse_error = parse_uuid(event_id, "eventID")
        if parse_error:
            return parse_error

        event, fetch_error = fetch_event(parsed_event_id)
        if fetch_error:
            return fetch_error

        state = None
        active_flash_sale = None

        try:
            state_result = (
                get_db()
                .table("inventory_event_state")
                .select(
                    "event_id,flash_sale_active,active_flash_sale_id,last_sold_out_category,"
                    "last_sold_out_at,metadata,updated_at"
                )
                .eq("event_id", parsed_event_id)
                .limit(1)
                .execute()
            )
            state_rows = state_result.data or []
            state = state_rows[0] if state_rows else None

            sale_query = (
                get_db()
                .table("flash_sales")
                .select(
                    "flash_sale_id,event_id,discount_percentage,escalation_percentage,"
                    "starts_at,ends_at,status,launched_by_user_id,config,ended_at"
                )
                .eq("event_id", parsed_event_id)
            )

            active_flash_sale_id = state.get("active_flash_sale_id") if state else None
            if active_flash_sale_id:
                sale_query = sale_query.eq("flash_sale_id", active_flash_sale_id)
            else:
                sale_query = sale_query.eq("status", "ACTIVE")

            sale_result = sale_query.order("starts_at", desc=True).limit(1).execute()
            sales = sale_result.data or []
            active_flash_sale = sales[0] if sales else None
        except Exception as error:
            logger.exception("Failed to load flash sale status for event %s: %s", parsed_event_id, error)
            return error_response("Failed to load flash sale status", 500)

        return (
            jsonify(
                {
                    "event_id": parsed_event_id,
                    "event_status": event.get("status"),
                    "flash_sale_active": bool(state and state.get("flash_sale_active")),
                    "inventory_state": state,
                    "active_flash_sale": active_flash_sale,
                }
            ),
            200,
        )

    @app.get("/event/<event_id>/price-history")
    def get_price_history(event_id: str):
        """Get event price change history.
        ---
        tags:
          - Categories
        parameters:
          - name: event_id
            in: path
            required: true
            type: string
            format: uuid
          - name: limit
            in: query
            required: false
            type: integer
            minimum: 1
            maximum: 200
            default: 50
        responses:
          200:
            description: Price change records ordered by changed_at descending.
          422:
            description: Limit outside allowed range.
        """
        db_error = require_db()
        if db_error:
            return db_error

        parsed_event_id, parse_error = parse_uuid(event_id, "eventID")
        if parse_error:
            return parse_error

        _event, fetch_error = fetch_event(parsed_event_id)
        if fetch_error:
            return fetch_error

        try:
            limit = int(request.args.get("limit", "50"))
        except ValueError:
            return error_response("Invalid limit value", 400)

        if limit < 1 or limit > 200:
            return error_response("Limit must be between 1 and 200", 422)

        try:
            history_result = (
                get_db()
                .table("price_changes")
                .select(
                    "change_id,flash_sale_id,event_id,category_id,reason,old_price,new_price,"
                    "changed_at,changed_by,context"
                )
                .eq("event_id", parsed_event_id)
                .order("changed_at", desc=True)
                .limit(limit)
                .execute()
            )
            history_rows = history_result.data or []
        except Exception as error:
            logger.exception("Failed to load price history for event %s: %s", parsed_event_id, error)
            return error_response("Failed to load price history", 500)

        category_ids = list({row.get("category_id") for row in history_rows if row.get("category_id")})
        categories_by_id = {}
        if category_ids:
            try:
                categories_result = (
                    get_db()
                    .table("seat_categories")
                    .select("category_id,category_code,name")
                    .in_("category_id", category_ids)
                    .execute()
                )
                categories_by_id = {
                    row["category_id"]: row
                    for row in (categories_result.data or [])
                }
            except Exception as error:
                logger.warning("Failed to enrich category metadata for price history: %s", error)

        enriched_rows = []
        for row in history_rows:
            category = categories_by_id.get(row.get("category_id"), {})
            enriched_rows.append(
                {
                    **row,
                    "category_code": category.get("category_code"),
                    "category_name": category.get("name"),
                }
            )

        return jsonify({"event_id": parsed_event_id, "price_changes": enriched_rows}), 200

    @app.put("/event/<event_id>/status")
    def update_event_status(event_id: str):
        """Update event lifecycle status.
        ---
        tags:
          - Events
        security:
          - OrganiserApiKey: []
        parameters:
          - name: event_id
            in: path
            required: true
            type: string
            format: uuid
          - in: body
            name: body
            required: true
            schema:
              type: object
              required:
                - status
              properties:
                status:
                  type: string
                  enum: [SCHEDULED, ACTIVE, FLASH_SALE_ACTIVE, CANCELLED, COMPLETED]
        responses:
          200:
            description: Event status updated.
          409:
            description: Invalid transition or terminal-state mutation.
          500:
            description: Update failed and rollback attempted.
          503:
            description: RabbitMQ unavailable; update rolled back.
        """
        db_error = require_db()
        if db_error:
            return db_error

        parsed_event_id, parse_error = parse_uuid(event_id, "eventID")
        if parse_error:
            return parse_error

        event, fetch_error = fetch_event(parsed_event_id)
        if fetch_error:
            return fetch_error

        payload, payload_error = parse_json_object_body()
        if payload_error:
            return payload_error

        target_status = payload.get("status")
        if not isinstance(target_status, str):
            return error_response("Field 'status' is required", 422)

        target_status = target_status.strip().upper()
        if target_status not in EVENT_STATUSES:
            return error_response("Invalid status", 422, sorted(EVENT_STATUSES))

        current_status = event.get("status")
        if current_status in TERMINAL_EVENT_STATUSES and target_status != current_status:
            return error_response("Terminal event status cannot be changed", 409)

        if target_status != current_status and target_status not in ALLOWED_STATUS_TRANSITIONS.get(
            current_status,
            set(),
        ):
            return error_response(
                "Invalid status transition",
                409,
                {
                    "from": current_status,
                    "to": target_status,
                    "allowed": sorted(ALLOWED_STATUS_TRANSITIONS.get(current_status, set())),
                },
            )

        if target_status == current_status:
            event.pop("deleted_at", None)
            return jsonify({"event": event, "message": "Status unchanged"}), 200

        try:
            (
                get_db()
                .table("events")
                .update({"status": target_status})
                .eq("event_id", parsed_event_id)
                .execute()
            )
        except Exception as error:
            logger.exception("Failed to update status for event %s: %s", parsed_event_id, error)
            return error_response("Failed to update event status", 500)

        updated_event, updated_fetch_error = fetch_event(parsed_event_id)
        if updated_fetch_error:
            rollback_success = rollback_event_status(parsed_event_id, current_status)
            return error_response(
                "Failed to load updated event",
                500,
                {
                    "rolledBack": rollback_success,
                    "reason": "Failed to read updated event after status write",
                },
            )

        updated_event.pop("deleted_at", None)

        publish_payload = {
            "eventID": parsed_event_id,
            "oldStatus": current_status,
            "newStatus": target_status,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        published, integration_event, publish_error, publish_status = publish_with_outbox(
            routing_key="event.status.updated",
            event_name="event.status.updated",
            payload=publish_payload,
            aggregate_type="event",
            aggregate_id=parsed_event_id,
        )
        if not published:
            rollback_success = rollback_event_status(parsed_event_id, current_status)
            outbox_cleanup_success = delete_integration_event(integration_event)
            return error_response(
                "Failed to update event status",
                publish_status,
                {
                    "rolledBack": rollback_success,
                    "rollbackTargetStatus": current_status,
                    "outboxCleanedUp": outbox_cleanup_success,
                    "reason": publish_error,
                },
            )

        return jsonify({"event": updated_event}), 200

    @app.put("/event/<event_id>/categories/prices")
    def update_category_prices(event_id: str):
        """Update event category prices in batch.
        ---
        tags:
          - Categories
        security:
          - OrganiserApiKey: []
        parameters:
          - name: event_id
            in: path
            required: true
            type: string
            format: uuid
          - in: body
            name: body
            required: true
            schema:
              type: object
              required:
                - reason
                - updates
              properties:
                reason:
                  type: string
                  enum: [FLASH_SALE, ESCALATION, REVERT, MANUAL_ADJUSTMENT]
                flash_sale_id:
                  type: string
                  format: uuid
                changed_by:
                  type: string
                context:
                  type: object
                updates:
                  type: array
                  items:
                    type: object
                    required:
                      - category_id
                      - new_price
                    properties:
                      category_id:
                        type: string
                        format: uuid
                      new_price:
                        type: number
        responses:
          200:
            description: Category prices updated.
          404:
            description: One or more categories not found for event.
          409:
            description: Event is in terminal state.
          500:
            description: Update failed and rollback attempted.
          503:
            description: RabbitMQ unavailable; update rolled back.
        """
        db_error = require_db()
        if db_error:
            return db_error

        parsed_event_id, parse_error = parse_uuid(event_id, "eventID")
        if parse_error:
            return parse_error

        event, fetch_error = fetch_event(parsed_event_id)
        if fetch_error:
            return fetch_error

        if event.get("status") in TERMINAL_EVENT_STATUSES:
            return error_response("Cannot update prices for terminal event status", 409)

        payload, payload_error = parse_json_object_body()
        if payload_error:
            return payload_error

        reason = payload.get("reason")
        if not isinstance(reason, str):
            return error_response("Field 'reason' is required", 422)
        reason = reason.strip().upper()
        if reason not in PRICE_CHANGE_REASONS:
            return error_response("Invalid reason", 422, sorted(PRICE_CHANGE_REASONS))

        flash_sale_id_raw = payload.get("flash_sale_id") or payload.get("flashSaleID")
        flash_sale_id = None
        if flash_sale_id_raw:
            flash_sale_id, flash_sale_error = parse_uuid(flash_sale_id_raw, "flashSaleID")
            if flash_sale_error:
                return flash_sale_error

        changed_by = payload.get("changed_by") or payload.get("changedBy") or os.getenv(
            "SERVICE_NAME",
            "event-service",
        )
        if not isinstance(changed_by, str) or not changed_by.strip():
            return error_response("Field 'changed_by' must be a non-empty string", 422)

        context = payload.get("context") or {}
        if not isinstance(context, dict):
            return error_response("Field 'context' must be an object", 422)

        normalized_updates, updates_error = normalize_price_updates(payload)
        if updates_error:
            return updates_error

        category_ids = [item["category_id"] for item in normalized_updates]

        try:
            existing_categories_result = (
                get_db()
                .table("seat_categories")
                .select("category_id,event_id,current_price,deleted_at")
                .in_("category_id", category_ids)
                .execute()
            )
            existing_categories = existing_categories_result.data or []
        except Exception as error:
            logger.exception("Failed to load existing categories for price update: %s", error)
            return error_response("Failed to load categories", 500)

        categories_by_id = {
            row.get("category_id"): row
            for row in existing_categories
            if row.get("deleted_at") is None and row.get("event_id") == parsed_event_id
        }

        missing_ids = [
            category_id
            for category_id in category_ids
            if category_id not in categories_by_id
        ]
        if missing_ids:
            return error_response(
                "Some categories were not found for this event",
                404,
                {"missingCategoryIDs": missing_ids},
            )

        old_prices = {
            category_id: str(categories_by_id[category_id].get("current_price"))
            for category_id in category_ids
        }
        applied_price_rollbacks: Dict[str, str] = {}
        recorded_price_change_ids: List[str] = []

        try:
            for item in normalized_updates:
                category_id = item["category_id"]
                new_price = item["new_price"]

                (
                    get_db()
                    .table("seat_categories")
                    .update({"current_price": new_price})
                    .eq("category_id", category_id)
                    .eq("event_id", parsed_event_id)
                    .execute()
                )
                applied_price_rollbacks[category_id] = old_prices[category_id]

                price_change_row = {
                    "flash_sale_id": flash_sale_id,
                    "event_id": parsed_event_id,
                    "category_id": category_id,
                    "reason": reason,
                    "old_price": old_prices[category_id],
                    "new_price": new_price,
                    "changed_by": changed_by.strip(),
                    "context": context,
                }
                inserted_change = get_db().table("price_changes").insert(price_change_row).execute()
                inserted_rows = inserted_change.data or []
                if not inserted_rows:
                    raise RuntimeError("Failed to record price change audit row")

                change_id = inserted_rows[0].get("change_id")
                if change_id:
                    recorded_price_change_ids.append(change_id)

        except Exception as error:
            logger.exception("Failed during batch price update for event %s: %s", parsed_event_id, error)
            rollback_failed_categories = rollback_category_prices(parsed_event_id, applied_price_rollbacks)
            rollback_failed_changes = delete_price_change_records(recorded_price_change_ids)

            return error_response(
                "Failed to update category prices",
                500,
                {
                    "rolledBack": not rollback_failed_categories and not rollback_failed_changes,
                    "failedCategoryRollbacks": rollback_failed_categories,
                    "failedPriceChangeCleanup": rollback_failed_changes,
                    "reason": str(error),
                },
            )

        try:
            updated_categories_result = (
                get_db()
                .table("seat_categories")
                .select(
                    "category_id,event_id,category_code,name,base_price,current_price,currency,"
                    "total_seats,is_active,sort_order,metadata,deleted_at"
                )
                .eq("event_id", parsed_event_id)
                .in_("category_id", category_ids)
                .order("sort_order")
                .execute()
            )
            updated_categories = [
                row
                for row in (updated_categories_result.data or [])
                if row.get("deleted_at") is None
            ]
            for category in updated_categories:
                category.pop("deleted_at", None)
        except Exception as error:
            logger.exception("Failed to load updated categories for event %s: %s", parsed_event_id, error)
            rollback_failed_categories = rollback_category_prices(parsed_event_id, old_prices)
            rollback_failed_changes = delete_price_change_records(recorded_price_change_ids)
            return error_response(
                "Failed to load updated categories",
                500,
                {
                    "rolledBack": not rollback_failed_categories and not rollback_failed_changes,
                    "failedCategoryRollbacks": rollback_failed_categories,
                    "failedPriceChangeCleanup": rollback_failed_changes,
                    "reason": str(error),
                },
            )

        publish_payload = {
            "eventID": parsed_event_id,
            "reason": reason,
            "flashSaleID": flash_sale_id,
            "changedBy": changed_by.strip(),
            "context": context,
            "updates": [
                {
                    "categoryID": item["category_id"],
                    "oldPrice": old_prices[item["category_id"]],
                    "newPrice": item["new_price"],
                }
                for item in normalized_updates
            ],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        published, integration_event, publish_error, publish_status = publish_with_outbox(
            routing_key="event.prices.updated",
            event_name="event.prices.updated",
            payload=publish_payload,
            aggregate_type="event",
            aggregate_id=parsed_event_id,
        )
        if not published:
            rollback_failed_categories = rollback_category_prices(parsed_event_id, old_prices)
            rollback_failed_changes = delete_price_change_records(recorded_price_change_ids)
            outbox_cleanup_success = delete_integration_event(integration_event)
            return error_response(
                "Failed to update category prices",
                publish_status,
                {
                    "rolledBack": (
                        not rollback_failed_categories
                        and not rollback_failed_changes
                        and outbox_cleanup_success
                    ),
                    "failedCategoryRollbacks": rollback_failed_categories,
                    "failedPriceChangeCleanup": rollback_failed_changes,
                    "outboxCleanedUp": outbox_cleanup_success,
                    "reason": publish_error,
                },
            )

        return (
            jsonify(
                {
                    "event_id": parsed_event_id,
                    "reason": reason,
                    "categories": updated_categories,
                }
            ),
            200,
        )

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
