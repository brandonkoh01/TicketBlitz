import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from uuid import UUID

from flask import Flask, jsonify, request
from flask_cors import CORS

from shared.db import db_configured, get_db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

MAX_FLASH_SALE_MINUTES = 24 * 7 * 4
MAX_LIMIT = 500


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _json_error(message: str, status_code: int, details: Any = None):
    payload: Dict[str, Any] = {"error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


def _normalize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_money_str(value: Any) -> str:
    decimal_value = Decimal(str(value))
    return str(_normalize_money(decimal_value))


def _parse_uuid(value: Any, field_name: str) -> str:
    try:
        return str(UUID(str(value)))
    except Exception as error:
        raise ValueError(f"{field_name} must be a valid UUID") from error


def _parse_percentage(value: Any, field_name: str, minimum: Decimal, maximum: Decimal) -> Decimal:
    try:
        percentage = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a numeric percentage") from error

    if percentage < minimum or percentage > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")

    return _normalize_money(percentage)


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


def _fetch_event(event_id: str) -> Optional[Dict[str, Any]]:
    result = (
        get_db()
        .table("events")
        .select("event_id,status,deleted_at")
        .eq("event_id", event_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows or rows[0].get("deleted_at") is not None:
        return None
    return rows[0]


def _fetch_categories_for_event(event_id: str) -> List[Dict[str, Any]]:
    result = (
        get_db()
        .table("seat_categories")
        .select(
            "category_id,event_id,category_code,name,base_price,current_price,currency,"
            "is_active,sort_order,total_seats,deleted_at"
        )
        .eq("event_id", event_id)
        .order("sort_order")
        .execute()
    )
    return [row for row in (result.data or []) if row.get("deleted_at") is None]


def _seat_counts_by_category(event_id: str) -> Dict[str, Dict[str, int]]:
    try:
        result = (
            get_db()
            .table("seats")
            .select("category_id,status")
            .eq("event_id", event_id)
            .execute()
        )
    except Exception:
        logger.warning("Unable to compute seat availability snapshot for pricing")
        return {}

    counts: Dict[str, Dict[str, int]] = {}
    for row in result.data or []:
        category_id_raw = row.get("category_id")
        category_id = str(category_id_raw) if category_id_raw is not None else ""
        if not category_id:
            continue

        status = str(row.get("status") or "UNKNOWN").upper()
        bucket = counts.setdefault(category_id, {"AVAILABLE": 0, "SOLD": 0})

        if status in bucket:
            bucket[status] += 1

    return counts


def _coerce_non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _find_active_flash_sale(event_id: str, flash_sale_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query = (
        get_db()
        .table("flash_sales")
        .select(
            "flash_sale_id,event_id,discount_percentage,escalation_percentage,starts_at,"
            "ends_at,status,launched_by_user_id,config,ended_at,created_at,updated_at"
        )
        .eq("event_id", event_id)
        .eq("status", "ACTIVE")
        .gt("ends_at", _iso_now())
    )

    if flash_sale_id:
        query = query.eq("flash_sale_id", flash_sale_id)

    result = query.order("starts_at", desc=True).limit(1).execute()
    rows = result.data or []
    return rows[0] if rows else None


def _find_expired_active_flash_sales(
    event_id: Optional[str] = None,
    limit: int = 100,
    include_ended: bool = False,
    ended_since_minutes: int = 60,
) -> List[Dict[str, Any]]:
    now_iso = _iso_now()
    active_query = (
        get_db()
        .table("flash_sales")
        .select(
            "flash_sale_id,event_id,discount_percentage,escalation_percentage,starts_at,"
            "ends_at,status,launched_by_user_id,config,ended_at,created_at,updated_at"
        )
        .eq("status", "ACTIVE")
        .lte("ends_at", now_iso)
    )

    if event_id:
        active_query = active_query.eq("event_id", event_id)

    active_result = active_query.order("ends_at").limit(limit).execute()
    active_rows = active_result.data or []

    if not include_ended:
        return active_rows

    ended_window_floor = (_utc_now() - timedelta(minutes=ended_since_minutes)).isoformat()
    ended_query = (
        get_db()
        .table("flash_sales")
        .select(
            "flash_sale_id,event_id,discount_percentage,escalation_percentage,starts_at,"
            "ends_at,status,launched_by_user_id,config,ended_at,created_at,updated_at"
        )
        .eq("status", "ENDED")
        .lte("ends_at", now_iso)
        .gte("ended_at", ended_window_floor)
    )

    if event_id:
        ended_query = ended_query.eq("event_id", event_id)

    ended_result = ended_query.order("ended_at", desc=True).limit(limit).execute()
    ended_rows = ended_result.data or []

    merged_rows: Dict[str, Dict[str, Any]] = {}
    for row in active_rows + ended_rows:
        flash_sale_id = row.get("flash_sale_id")
        if not flash_sale_id or flash_sale_id in merged_rows:
            continue
        merged_rows[flash_sale_id] = row

    rows = list(merged_rows.values())
    rows.sort(key=lambda row: str(row.get("ends_at") or ""))
    return rows[:limit]


def _insert_flash_sale(row: Dict[str, Any]) -> Dict[str, Any]:
    result = get_db().table("flash_sales").insert(row).execute()
    rows = result.data or []
    if not rows:
        raise RuntimeError("Failed to create flash sale record")
    return rows[0]


def _compute_discount_updates(categories: List[Dict[str, Any]], discount_percentage: Decimal) -> List[Dict[str, Any]]:
    multiplier = Decimal("1") - (discount_percentage / Decimal("100"))
    updates: List[Dict[str, Any]] = []

    for category in categories:
        old_price = _normalize_money(Decimal(str(category.get("base_price"))))
        new_price = _normalize_money(old_price * multiplier)
        updates.append(
            {
                "categoryID": category.get("category_id"),
                "category": category.get("category_code"),
                "oldPrice": str(old_price),
                "newPrice": str(new_price),
                "currency": category.get("currency", "SGD"),
            }
        )

    return updates


def _compute_escalation_updates(
    categories: List[Dict[str, Any]],
    escalation_percentage: Decimal,
) -> List[Dict[str, Any]]:
    multiplier = Decimal("1") + (escalation_percentage / Decimal("100"))

    updates: List[Dict[str, Any]] = []
    for category in categories:
        category_id = category.get("category_id")

        if not category_id:
            continue
        if not category.get("is_active", True):
            continue

        old_price = _normalize_money(Decimal(str(category.get("current_price"))))
        new_price = _normalize_money(old_price * multiplier)

        updates.append(
            {
                "categoryID": category_id,
                "category": category.get("category_code"),
                "oldPrice": str(old_price),
                "newPrice": str(new_price),
                "currency": category.get("currency", "SGD"),
            }
        )

    return updates


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    @app.get("/health")
    def health():
        return (
            jsonify(
                {
                    "status": "ok",
                    "service": os.getenv("SERVICE_NAME", "pricing-service"),
                    "supabaseConfigured": db_configured(),
                }
            ),
            200,
        )

    @app.post("/pricing/flash-sale/configure")
    def configure_flash_sale():
        if not db_configured():
            return _json_error("Supabase is not configured", 503)

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _json_error("Request body must be a JSON object", 400)

        try:
            event_id = _parse_uuid(payload.get("eventID"), "eventID")
            discount_percentage = _parse_percentage(
                payload.get("discountPercentage"),
                "discountPercentage",
                Decimal("0.01"),
                Decimal("100"),
            )
            duration_minutes = _parse_positive_int(
                payload.get("durationMinutes"),
                "durationMinutes",
                MAX_FLASH_SALE_MINUTES,
            )

            escalation_raw = payload.get("escalationPercentage", Decimal("20"))
            escalation_percentage = _parse_percentage(
                escalation_raw,
                "escalationPercentage",
                Decimal("0"),
                Decimal("500"),
            )

            launched_by_user_id = None
            if payload.get("launchedByUserID"):
                launched_by_user_id = _parse_uuid(payload.get("launchedByUserID"), "launchedByUserID")
        except ValueError as error:
            return _json_error(str(error), 400)

        try:
            event = _fetch_event(event_id)
        except Exception as error:
            logger.exception("Failed to load event %s: %s", event_id, error)
            return _json_error("Failed to load event", 500)

        if not event:
            return _json_error("Event not found", 404)

        try:
            categories = _fetch_categories_for_event(event_id)
        except Exception as error:
            logger.exception("Failed to load categories for event %s: %s", event_id, error)
            return _json_error("Failed to load event categories", 500)

        if not categories:
            return _json_error("No categories found for event", 404)

        updates = _compute_discount_updates(categories, discount_percentage)

        starts_at = _utc_now()
        ends_at = starts_at + timedelta(minutes=duration_minutes)

        row = {
            "event_id": event_id,
            "discount_percentage": str(discount_percentage),
            "escalation_percentage": str(escalation_percentage),
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "status": "ACTIVE",
            "launched_by_user_id": launched_by_user_id,
            "config": {
                "durationMinutes": duration_minutes,
                "source": payload.get("source", "flash-sale-orchestrator"),
            },
        }

        try:
            flash_sale = _insert_flash_sale(row)
        except Exception as error:
            message = str(error).lower()
            logger.exception("Failed to create flash sale for event %s: %s", event_id, error)
            if (
                "flash_sales_active_event_uk" in message
                or "flash_sales_no_overlap_excl" in message
                or "overlap" in message
                or "duplicate key" in message
            ):
                return _json_error("An active flash sale already exists for this event", 409)
            return _json_error("Failed to create flash sale", 500)

        return (
            jsonify(
                {
                    "status": "success",
                    "eventID": event_id,
                    "flashSaleID": flash_sale.get("flash_sale_id"),
                    "discountPercentage": str(discount_percentage),
                    "escalationPercentage": str(escalation_percentage),
                    "expiresAt": flash_sale.get("ends_at"),
                    "updatedPrices": updates,
                }
            ),
            200,
        )

    @app.get("/pricing/<event_id>/flash-sale/active")
    def get_active_flash_sale(event_id: str):
        if not db_configured():
            return _json_error("Supabase is not configured", 503)

        try:
            parsed_event_id = _parse_uuid(event_id, "eventID")
        except ValueError as error:
            return _json_error(str(error), 400)

        try:
            active_sale = _find_active_flash_sale(parsed_event_id)
        except Exception as error:
            logger.exception("Failed to load active flash sale for %s: %s", parsed_event_id, error)
            return _json_error("Failed to load active flash sale", 500)

        if not active_sale:
            return _json_error("No active flash sale for event", 404)

        return (
            jsonify(
                {
                    "eventID": parsed_event_id,
                    "flashSaleID": active_sale.get("flash_sale_id"),
                    "discountPercentage": _to_money_str(active_sale.get("discount_percentage")),
                    "escalationPercentage": _to_money_str(active_sale.get("escalation_percentage")),
                    "startsAt": active_sale.get("starts_at"),
                    "expiresAt": active_sale.get("ends_at"),
                    "status": active_sale.get("status"),
                }
            ),
            200,
        )

    @app.get("/pricing/flash-sales/expired")
    def get_expired_active_flash_sales():
        if not db_configured():
            return _json_error("Supabase is not configured", 503)

        event_id_raw = request.args.get("eventID")
        limit_raw = request.args.get("limit", "100")
        include_ended_raw = str(request.args.get("includeEnded", "0")).strip().lower()
        include_ended = include_ended_raw in {"1", "true", "yes", "on"}
        ended_window_raw = request.args.get("endedWindowMinutes", "60")

        try:
            limit = _parse_positive_int(limit_raw, "limit", MAX_LIMIT)
        except ValueError as error:
            return _json_error(str(error), 400)

        try:
            ended_window_minutes = _parse_positive_int(
                ended_window_raw,
                "endedWindowMinutes",
                24 * 60,
            )
        except ValueError as error:
            return _json_error(str(error), 400)

        event_id = None
        if event_id_raw:
            try:
                event_id = _parse_uuid(event_id_raw, "eventID")
            except ValueError as error:
                return _json_error(str(error), 400)

        try:
            rows = _find_expired_active_flash_sales(
                event_id=event_id,
                limit=limit,
                include_ended=include_ended,
                ended_since_minutes=ended_window_minutes,
            )
        except Exception as error:
            logger.exception("Failed to load expired active flash sales: %s", error)
            return _json_error("Failed to load expired active flash sales", 500)

        return (
            jsonify(
                {
                    "flashSales": [
                        {
                            "flashSaleID": row.get("flash_sale_id"),
                            "eventID": row.get("event_id"),
                            "status": row.get("status"),
                            "startsAt": row.get("starts_at"),
                            "expiresAt": row.get("ends_at"),
                            "endedAt": row.get("ended_at"),
                        }
                        for row in rows
                    ],
                    "count": len(rows),
                }
            ),
            200,
        )

    @app.post("/pricing/escalate")
    def escalate_prices():
        if not db_configured():
            return _json_error("Supabase is not configured", 503)

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _json_error("Request body must be a JSON object", 400)

        remaining_categories_raw = payload.get("remainingCategories")
        if not isinstance(remaining_categories_raw, list):
            return _json_error("remainingCategories must be an array", 400)

        try:
            event_id = _parse_uuid(payload.get("eventID"), "eventID")
            sold_out_category = str(payload.get("soldOutCategory") or "").strip().upper()
            if not sold_out_category:
                raise ValueError("soldOutCategory is required")

            flash_sale_id = None
            if payload.get("flashSaleID"):
                flash_sale_id = _parse_uuid(payload.get("flashSaleID"), "flashSaleID")
        except ValueError as error:
            return _json_error(str(error), 400)

        try:
            active_sale = _find_active_flash_sale(event_id, flash_sale_id)
        except Exception as error:
            logger.exception("Failed to load active flash sale for escalation: %s", error)
            return _json_error("Failed to load active flash sale", 500)

        if not active_sale:
            return _json_error("No active flash sale available for escalation", 404)

        escalation_percentage_raw = payload.get("escalationPercentage", active_sale.get("escalation_percentage"))
        try:
            escalation_percentage = _parse_percentage(
                escalation_percentage_raw,
                "escalationPercentage",
                Decimal("0"),
                Decimal("500"),
            )
        except ValueError as error:
            return _json_error(str(error), 400)

        try:
            categories = _fetch_categories_for_event(event_id)
        except Exception as error:
            logger.exception("Failed to load categories for escalation: %s", error)
            return _json_error("Failed to load event categories", 500)

        if not categories:
            return _json_error("No categories found for event", 404)

        category_by_id = {row.get("category_id"): row for row in categories if row.get("category_id")}
        selected_categories: List[Dict[str, Any]] = []
        seen_ids = set()
        for row in remaining_categories_raw:
            if not isinstance(row, dict):
                return _json_error("remainingCategories items must be objects", 400)

            try:
                category_id = _parse_uuid(row.get("categoryID"), "remainingCategories.categoryID")
            except ValueError as error:
                return _json_error(str(error), 400)

            if category_id in seen_ids:
                continue
            seen_ids.add(category_id)

            category = category_by_id.get(category_id)
            if not category:
                return _json_error("remainingCategories contains category not found for event", 400)

            if category.get("is_active", True):
                selected_categories.append(category)

        updates = _compute_escalation_updates(
            categories=selected_categories,
            escalation_percentage=escalation_percentage,
        )

        return (
            jsonify(
                {
                    "eventID": event_id,
                    "flashSaleID": active_sale.get("flash_sale_id"),
                    "soldOutCategory": sold_out_category,
                    "escalationPercentage": str(escalation_percentage),
                    "updatedPrices": updates,
                    "count": len(updates),
                }
            ),
            200,
        )

    @app.put("/pricing/<flash_sale_id>/end")
    def end_flash_sale(flash_sale_id: str):
        if not db_configured():
            return _json_error("Supabase is not configured", 503)

        try:
            parsed_flash_sale_id = _parse_uuid(flash_sale_id, "flashSaleID")
        except ValueError as error:
            return _json_error(str(error), 400)

        try:
            current_result = (
                get_db()
                .table("flash_sales")
                .select("flash_sale_id,event_id,status,starts_at,ends_at,ended_at")
                .eq("flash_sale_id", parsed_flash_sale_id)
                .limit(1)
                .execute()
            )
            current_rows = current_result.data or []
        except Exception as error:
            logger.exception("Failed to load flash sale %s: %s", parsed_flash_sale_id, error)
            return _json_error("Failed to load flash sale", 500)

        if not current_rows:
            return _json_error("Flash sale not found", 404)

        current = current_rows[0]
        if current.get("status") == "ENDED":
            return (
                jsonify(
                    {
                        "flashSaleID": parsed_flash_sale_id,
                        "eventID": current.get("event_id"),
                        "status": "ENDED",
                        "endedAt": current.get("ended_at"),
                    }
                ),
                200,
            )

        ended_at = _iso_now()
        try:
            update_result = (
                get_db()
                .table("flash_sales")
                .update({"status": "ENDED", "ended_at": ended_at, "updated_at": ended_at})
                .eq("flash_sale_id", parsed_flash_sale_id)
                .eq("status", "ACTIVE")
                .execute()
            )
            rows = update_result.data or []
        except Exception as error:
            logger.exception("Failed to end flash sale %s: %s", parsed_flash_sale_id, error)
            return _json_error("Failed to end flash sale", 500)

        if not rows:
            return _json_error("Flash sale is not ACTIVE", 409)

        updated = rows[0]
        return (
            jsonify(
                {
                    "flashSaleID": updated.get("flash_sale_id"),
                    "eventID": updated.get("event_id"),
                    "status": updated.get("status"),
                    "endedAt": updated.get("ended_at"),
                }
            ),
            200,
        )

    @app.get("/pricing/<event_id>")
    def get_effective_pricing(event_id: str):
        if not db_configured():
            return _json_error("Supabase is not configured", 503)

        try:
            parsed_event_id = _parse_uuid(event_id, "eventID")
        except ValueError as error:
            return _json_error(str(error), 400)

        try:
            event = _fetch_event(parsed_event_id)
        except Exception as error:
            logger.exception("Failed to load event %s: %s", parsed_event_id, error)
            return _json_error("Failed to load event", 500)

        if not event:
            return _json_error("Event not found", 404)

        try:
            categories = _fetch_categories_for_event(parsed_event_id)
            active_sale = _find_active_flash_sale(parsed_event_id)
            seat_counts = _seat_counts_by_category(parsed_event_id)
        except Exception as error:
            logger.exception("Failed to load pricing snapshot for %s: %s", parsed_event_id, error)
            return _json_error("Failed to load pricing snapshot", 500)

        category_rows: List[Dict[str, Any]] = []
        for category in categories:
            category_id = category.get("category_id")
            normalized_category_id = str(category_id) if category_id is not None else ""
            category_counts = seat_counts.get(normalized_category_id, {"AVAILABLE": 0, "SOLD": 0})

            available_seats = _coerce_non_negative_int(category_counts.get("AVAILABLE"))
            sold_seats = _coerce_non_negative_int(category_counts.get("SOLD"))

            observed_total = available_seats + sold_seats
            total_seats = _coerce_non_negative_int(category.get("total_seats"))
            if total_seats <= 0:
                total_seats = observed_total
            else:
                total_seats = max(total_seats, observed_total)

            sold_out = available_seats <= 0

            if sold_out and sold_seats <= 0 and total_seats > 0:
                sold_seats = total_seats

            category_rows.append(
                {
                    "categoryID": category_id,
                    "category": category.get("category_code"),
                    "name": category.get("name"),
                    "basePrice": _to_money_str(category.get("base_price")),
                    "currentPrice": _to_money_str(category.get("current_price")),
                    "currency": category.get("currency", "SGD"),
                    "totalSeats": total_seats,
                    "availableSeats": available_seats,
                    "soldSeats": sold_seats,
                    "status": "SOLD_OUT" if sold_out else "AVAILABLE",
                    "isActive": bool(category.get("is_active", True)),
                }
            )

        return (
            jsonify(
                {
                    "eventID": parsed_event_id,
                    "eventStatus": event.get("status"),
                    "flashSaleActive": active_sale is not None,
                    "flashSaleID": active_sale.get("flash_sale_id") if active_sale else None,
                    "categories": category_rows,
                }
            ),
            200,
        )

    @app.get("/pricing/<event_id>/history")
    def get_pricing_history(event_id: str):
        if not db_configured():
            return _json_error("Supabase is not configured", 503)

        try:
            parsed_event_id = _parse_uuid(event_id, "eventID")
        except ValueError as error:
            return _json_error(str(error), 400)

        flash_sale_id_raw = request.args.get("flashSaleID")
        limit_raw = request.args.get("limit", "100")

        try:
            limit = _parse_positive_int(limit_raw, "limit", MAX_LIMIT)
        except ValueError as error:
            return _json_error(str(error), 400)

        flash_sale_id = None
        if flash_sale_id_raw:
            try:
                flash_sale_id = _parse_uuid(flash_sale_id_raw, "flashSaleID")
            except ValueError as error:
                return _json_error(str(error), 400)

        try:
            query = (
                get_db()
                .table("price_changes")
                .select(
                    "change_id,flash_sale_id,event_id,category_id,reason,old_price,new_price,"
                    "changed_at,changed_by,context"
                )
                .eq("event_id", parsed_event_id)
            )
            if flash_sale_id:
                query = query.eq("flash_sale_id", flash_sale_id)

            result = query.order("changed_at", desc=True).limit(limit).execute()
            rows = result.data or []
        except Exception as error:
            logger.exception("Failed to load pricing history for %s: %s", parsed_event_id, error)
            return _json_error("Failed to load pricing history", 500)

        history = [
            {
                "changeID": row.get("change_id"),
                "flashSaleID": row.get("flash_sale_id"),
                "eventID": row.get("event_id"),
                "categoryID": row.get("category_id"),
                "reason": row.get("reason"),
                "oldPrice": _to_money_str(row.get("old_price")),
                "newPrice": _to_money_str(row.get("new_price")),
                "changedAt": row.get("changed_at"),
                "changedBy": row.get("changed_by"),
                "context": row.get("context") or {},
            }
            for row in rows
        ]

        return jsonify({"eventID": parsed_event_id, "priceChanges": history, "count": len(history)}), 200

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
