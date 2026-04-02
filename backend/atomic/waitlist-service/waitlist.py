from __future__ import annotations

import hmac
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from flask import Blueprint, Flask, Response, current_app, jsonify, request
from flask_cors import CORS
from postgrest.exceptions import APIError

from shared.db import db_configured, get_db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

WAITLIST_STATUSES = {"WAITING", "HOLD_OFFERED", "CONFIRMED", "EXPIRED", "CANCELLED"}
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SENSITIVE_READ_ENDPOINTS = {
    "waitlist_service.list_waitlist_entries",
    "waitlist_service.get_next_waitlist_entry",
    "waitlist_service.get_waitlist_by_hold",
    "waitlist_service.get_waitlist_status_for_hold",
}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    return default


class BaseConfig:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "waitlist-service")
    WAITLIST_DEFAULT_LIMIT = max(_env_int("WAITLIST_DEFAULT_LIMIT", 50), 1)
    WAITLIST_MAX_LIMIT = max(_env_int("WAITLIST_MAX_LIMIT", 200), WAITLIST_DEFAULT_LIMIT)
    INTERNAL_AUTH_HEADER = os.getenv("WAITLIST_SERVICE_AUTH_HEADER", "X-Internal-Token")
    INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "")
    REQUIRE_INTERNAL_AUTH = _env_bool("REQUIRE_INTERNAL_AUTH", True)


class WaitlistNotFoundError(Exception):
    pass


class WaitlistConflictError(Exception):
    pass


class WaitlistValidationError(Exception):
    pass


class WaitlistRepository:
    ENTRY_COLUMNS = (
        "waitlist_id,event_id,category_id,user_id,hold_id,status,joined_at,offered_at,"
        "confirmed_at,expired_at,priority_score,source,metadata,created_at,updated_at"
    )

    def __init__(self):
        self._client = get_db()

    def resolve_category(self, event_id: str, seat_category: str) -> dict[str, Any] | None:
        result = (
            self._client.table("seat_categories")
            .select("category_id,event_id,category_code,name")
            .eq("event_id", event_id)
            .eq("category_code", seat_category)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def get_category_map(self, category_ids: set[str]) -> dict[str, dict[str, Any]]:
        if not category_ids:
            return {}

        result = (
            self._client.table("seat_categories")
            .select("category_id,event_id,category_code,name")
            .in_("category_id", list(category_ids))
            .execute()
        )

        rows = result.data or []
        return {row["category_id"]: row for row in rows}

    def get_user_email_map(self, user_ids: set[str]) -> dict[str, str]:
        if not user_ids:
            return {}

        result = (
            self._client.table("users")
            .select("user_id,email")
            .in_("user_id", list(user_ids))
            .is_("deleted_at", "null")
            .execute()
        )

        rows = result.data or []
        return {row["user_id"]: row.get("email") for row in rows}

    def list_entries(
        self,
        *,
        event_id: str | None,
        category_id: str | None,
        user_id: str | None,
        status: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = (
            self._client.table("waitlist_entries")
            .select(self.ENTRY_COLUMNS)
            .order("joined_at", desc=False)
            .order("waitlist_id", desc=False)
            .limit(limit)
        )

        if event_id:
            query = query.eq("event_id", event_id)
        if category_id:
            query = query.eq("category_id", category_id)
        if user_id:
            query = query.eq("user_id", user_id)
        if status:
            query = query.eq("status", status)

        result = query.execute()
        return result.data or []

    def join_waitlist(
        self,
        *,
        event_id: str,
        category_id: str,
        user_id: str,
        priority_score: float,
        source: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "event_id": event_id,
            "category_id": category_id,
            "user_id": user_id,
            "status": "WAITING",
            "priority_score": priority_score,
            "source": source,
            "metadata": metadata,
        }

        result = self._client.table("waitlist_entries").insert(payload).execute()
        rows = result.data or []
        if not rows:
            raise RuntimeError("Waitlist entry insert did not return a row")
        return rows[0]

    def get_entry(self, waitlist_id: str) -> dict[str, Any] | None:
        result = (
            self._client.table("waitlist_entries")
            .select(self.ENTRY_COLUMNS)
            .eq("waitlist_id", waitlist_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def get_positions(self, waitlist_ids: list[str]) -> dict[str, int]:
        if not waitlist_ids:
            return {}

        result = (
            self._client.table("v_waitlist_ranked")
            .select("waitlist_id,queue_position")
            .in_("waitlist_id", waitlist_ids)
            .execute()
        )

        rows = result.data or []
        return {row["waitlist_id"]: row["queue_position"] for row in rows}

    def get_next_waiting(self, event_id: str, category_id: str) -> dict[str, Any] | None:
        result = (
            self._client.table("waitlist_entries")
            .select(self.ENTRY_COLUMNS)
            .eq("event_id", event_id)
            .eq("category_id", category_id)
            .eq("status", "WAITING")
            .order("joined_at", desc=False)
            .order("waitlist_id", desc=False)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def get_by_hold(self, hold_id: str) -> dict[str, Any] | None:
        result = (
            self._client.table("waitlist_entries")
            .select(self.ENTRY_COLUMNS)
            .eq("hold_id", hold_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def update_entry(self, waitlist_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        result = self._client.table("waitlist_entries").update(payload).eq("waitlist_id", waitlist_id).execute()
        rows = result.data or []
        return rows[0] if rows else None

    def update_entry_if_status(
        self,
        waitlist_id: str,
        *,
        expected_statuses: list[str],
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not expected_statuses:
            raise ValueError("expected_statuses must not be empty")

        query = self._client.table("waitlist_entries").update(payload).eq("waitlist_id", waitlist_id)
        if len(expected_statuses) == 1:
            query = query.eq("status", expected_statuses[0])
        else:
            query = query.in_("status", expected_statuses)

        result = query.execute()
        rows = result.data or []
        return rows[0] if rows else None

    def get_hold_context(self, hold_id: str) -> dict[str, Any] | None:
        result = (
            self._client.table("seat_holds")
            .select("hold_id,event_id,category_id")
            .eq("hold_id", hold_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def get_waiting_for_context(self, event_id: str, category_id: str, limit: int) -> list[dict[str, Any]]:
        result = (
            self._client.table("waitlist_entries")
            .select(self.ENTRY_COLUMNS)
            .eq("event_id", event_id)
            .eq("category_id", category_id)
            .eq("status", "WAITING")
            .order("joined_at", desc=False)
            .order("waitlist_id", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def get_active_entry_for_user(
        self,
        *,
        user_id: str,
        event_id: str,
        category_id: str,
        active_statuses: list[str],
    ) -> dict[str, Any] | None:
        result = (
            self._client.table("waitlist_entries")
            .select(self.ENTRY_COLUMNS)
            .eq("user_id", user_id)
            .eq("event_id", event_id)
            .eq("category_id", category_id)
            .in_("status", active_statuses)
            .order("joined_at", desc=False)
            .order("waitlist_id", desc=False)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None


waitlist_bp = Blueprint("waitlist_service", __name__)


def _json_error(message: str, status_code: int, details: Any | None = None):
    payload = {"error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


def _extract(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _parse_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a valid UUID")

    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid UUID")


def _parse_bool(value: str | None, *, field_name: str, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(f"{field_name} must be one of true/false")


def _parse_positive_int(
    value: str | None,
    *,
    field_name: str,
    default: int,
    max_value: int | None = None,
) -> int:
    if value is None:
        parsed = default
    else:
        try:
            parsed = int(value)
        except ValueError:
            raise ValueError(f"{field_name} must be an integer")

    if parsed < 1:
        raise ValueError(f"{field_name} must be >= 1")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{field_name} must be <= {max_value}")
    return parsed


def _parse_status(value: str | None, *, field_name: str = "status") -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    normalized = value.strip().upper()
    if normalized not in WAITLIST_STATUSES:
        allowed = ", ".join(sorted(WAITLIST_STATUSES))
        raise ValueError(f"{field_name} must be one of {allowed}")
    return normalized


def _parse_seat_category(value: Any, *, field_name: str = "seatCategory") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    normalized = value.strip().upper()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if len(normalized) > 50:
        raise ValueError(f"{field_name} must be <= 50 characters")
    return normalized


def _parse_optional_hold_id(payload: dict[str, Any]) -> str | None:
    hold_raw = _extract(payload, "holdID", "hold_id")
    if hold_raw is None:
        return None
    return _parse_uuid(hold_raw, "holdID")


def _serialize_entry(
    row: dict[str, Any],
    *,
    category_map: dict[str, dict[str, Any]],
    email_map: dict[str, str],
    position_map: dict[str, int],
    include_email: bool,
) -> dict[str, Any]:
    category = category_map.get(row.get("category_id"), {})
    waitlist_id = row.get("waitlist_id")
    status = row.get("status")

    payload = {
        "waitlistID": waitlist_id,
        "eventID": row.get("event_id"),
        "categoryID": row.get("category_id"),
        "seatCategory": category.get("category_code"),
        "userID": row.get("user_id"),
        "holdID": row.get("hold_id"),
        "status": status,
        "position": position_map.get(waitlist_id) if status == "WAITING" else None,
        "joinedAt": row.get("joined_at"),
        "offeredAt": row.get("offered_at"),
        "confirmedAt": row.get("confirmed_at"),
        "expiredAt": row.get("expired_at"),
        "priorityScore": row.get("priority_score"),
        "source": row.get("source"),
        "metadata": row.get("metadata") or {},
    }

    if include_email:
        payload["email"] = email_map.get(row.get("user_id"))

    return payload


def _decorate_entries(
    repo: WaitlistRepository,
    rows: list[dict[str, Any]],
    *,
    include_email: bool,
) -> list[dict[str, Any]]:
    if not rows:
        return []

    category_ids = {row["category_id"] for row in rows if row.get("category_id")}
    user_ids = {row["user_id"] for row in rows if row.get("user_id")}
    waiting_ids = [row["waitlist_id"] for row in rows if row.get("status") == "WAITING"]

    category_map = repo.get_category_map(category_ids)
    email_map = repo.get_user_email_map(user_ids) if include_email else {}
    position_map = repo.get_positions(waiting_ids)

    return [
        _serialize_entry(
            row,
            category_map=category_map,
            email_map=email_map,
            position_map=position_map,
            include_email=include_email,
        )
        for row in rows
    ]


def _get_repo() -> WaitlistRepository:
    repo = current_app.config.get("WAITLIST_REPOSITORY")
    if repo is None:
        repo = WaitlistRepository()
        current_app.config["WAITLIST_REPOSITORY"] = repo
    return repo


def _handle_repo_error(error: Exception):
    if isinstance(error, WaitlistNotFoundError):
        return _json_error(str(error), 404)
    if isinstance(error, WaitlistConflictError):
        return _json_error(str(error), 409)
    if isinstance(error, WaitlistValidationError):
        return _json_error(str(error), 400)

    if isinstance(error, APIError):
        code = getattr(error, "code", None)
        details = getattr(error, "details", None)

        if code == "23505":
            return _json_error("User is already on the waitlist for this category", 409, details=details)
        if code in {"22P02", "23503"}:
            return _json_error("Invalid request data", 400, details=details)
        if code == "23514":
            return _json_error("Request violates waitlist constraints", 409, details=details)

    message = str(error).lower()
    if "duplicate" in message and "key" in message:
        return _json_error("User is already on the waitlist for this category", 409)

    logger.exception("Waitlist repository operation failed: %s", error)
    return _json_error("Failed to process waitlist request", 500)


def _transition_waitlist_entry(
    repo: WaitlistRepository,
    *,
    waitlist_id: str,
    target_status: str,
    hold_id: str | None,
) -> dict[str, Any]:
    entry = repo.get_entry(waitlist_id)
    if entry is None:
        raise WaitlistNotFoundError("Waitlist entry not found")

    current_status = entry.get("status")
    current_hold = entry.get("hold_id")

    if hold_id and current_hold and hold_id != current_hold:
        raise WaitlistConflictError("holdID does not match current waitlist hold")

    if current_status == target_status:
        if hold_id and not current_hold:
            updated = repo.update_entry_if_status(
                waitlist_id,
                expected_statuses=[current_status],
                payload={"hold_id": hold_id},
            )
            if updated is not None:
                return updated

            latest = repo.get_entry(waitlist_id)
            if latest is None:
                raise WaitlistNotFoundError("Waitlist entry not found")

            latest_hold = latest.get("hold_id")
            if latest_hold and latest_hold != hold_id:
                raise WaitlistConflictError("holdID does not match current waitlist hold")
            return latest
        return entry

    allowed_transitions = {
        "HOLD_OFFERED": {"WAITING"},
        "CONFIRMED": {"HOLD_OFFERED"},
        "EXPIRED": {"HOLD_OFFERED"},
    }

    if current_status not in allowed_transitions.get(target_status, set()):
        raise WaitlistConflictError(f"Cannot transition waitlist entry from {current_status} to {target_status}")

    now_iso = datetime.now(timezone.utc).isoformat()
    update_payload: dict[str, Any] = {"status": target_status}

    if target_status == "HOLD_OFFERED":
        if hold_id is None:
            raise WaitlistValidationError("holdID is required when offering a waitlist entry")
        update_payload["offered_at"] = now_iso
    elif target_status == "CONFIRMED":
        update_payload["confirmed_at"] = now_iso
    elif target_status == "EXPIRED":
        update_payload["expired_at"] = now_iso

    if hold_id:
        update_payload["hold_id"] = hold_id

    updated = repo.update_entry_if_status(
        waitlist_id,
        expected_statuses=[current_status],
        payload=update_payload,
    )
    if updated is not None:
        return updated

    latest = repo.get_entry(waitlist_id)
    if latest is None:
        raise WaitlistNotFoundError("Waitlist entry not found")

    latest_status = latest.get("status")
    latest_hold = latest.get("hold_id")
    if latest_status == target_status:
        if hold_id and latest_hold and hold_id != latest_hold:
            raise WaitlistConflictError("holdID does not match current waitlist hold")
        return latest

    raise WaitlistConflictError(
        f"Cannot transition waitlist entry from {latest_status} to {target_status} due to a concurrent update"
    )


def _authorize_internal_request():
    if not current_app.config.get("REQUIRE_INTERNAL_AUTH", True):
        return None

    expected_token = current_app.config.get("INTERNAL_SERVICE_TOKEN", "")
    if not expected_token:
        logger.error("INTERNAL_SERVICE_TOKEN is required when REQUIRE_INTERNAL_AUTH is enabled")
        return _json_error("Service authentication is not configured", 503)

    header_name = current_app.config.get("INTERNAL_AUTH_HEADER", "X-Internal-Token")
    provided_token = request.headers.get(header_name, "")

    if not hmac.compare_digest(provided_token, expected_token):
        return _json_error("Unauthorized", 401)

    return None


@waitlist_bp.before_request
def _require_internal_auth():
    if request.method == "OPTIONS":
        return None

    endpoint = request.endpoint or ""

    if request.method in MUTATING_METHODS:
        return _authorize_internal_request()

    if request.method in {"GET", "HEAD"} and endpoint in SENSITIVE_READ_ENDPOINTS:
        return _authorize_internal_request()

    if request.method in {"GET", "HEAD"} and endpoint == "waitlist_service.get_waitlist_entry":
        try:
            include_email = _parse_bool(request.args.get("includeEmail"), field_name="includeEmail", default=False)
        except ValueError as error:
            return _json_error(str(error), 400)

        if include_email:
            return _authorize_internal_request()

    return None


@waitlist_bp.get("/health")
def health():
    return (
        jsonify(
            {
                "status": "ok",
                "service": current_app.config.get("SERVICE_NAME", "waitlist-service"),
                "supabaseConfigured": db_configured(),
            }
        ),
        200,
    )


@waitlist_bp.get("/waitlist")
def list_waitlist_entries():
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    try:
        event_raw = request.args.get("eventID")
        user_raw = request.args.get("userID")
        status_raw = request.args.get("status")
        seat_category_raw = request.args.get("seatCategory")
        include_email = _parse_bool(request.args.get("includeEmail"), field_name="includeEmail", default=False)
        limit = _parse_positive_int(
            request.args.get("limit"),
            field_name="limit",
            default=current_app.config["WAITLIST_DEFAULT_LIMIT"],
            max_value=current_app.config["WAITLIST_MAX_LIMIT"],
        )

        event_id = _parse_uuid(event_raw, "eventID") if event_raw else None
        user_id = _parse_uuid(user_raw, "userID") if user_raw else None
        status = _parse_status(status_raw, field_name="status")

        repo = _get_repo()
        category_id = None

        if seat_category_raw:
            if not event_id:
                raise ValueError("eventID is required when seatCategory is provided")

            seat_category = _parse_seat_category(seat_category_raw)
            category = repo.resolve_category(event_id, seat_category)
            if category is None:
                return _json_error("Seat category not found for event", 404)

            category_id = category["category_id"]

        rows = repo.list_entries(
            event_id=event_id,
            category_id=category_id,
            user_id=user_id,
            status=status,
            limit=limit,
        )
        entries = _decorate_entries(repo, rows, include_email=include_email)
        return jsonify({"entries": entries, "count": len(entries)}), 200
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


@waitlist_bp.post("/waitlist/join")
def join_waitlist():
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("Request body must be a JSON object", 400)

    try:
        user_id = _parse_uuid(_extract(payload, "userID", "user_id"), "userID")
        event_id = _parse_uuid(_extract(payload, "eventID", "event_id"), "eventID")
        seat_category = _parse_seat_category(_extract(payload, "seatCategory", "seat_category"))

        qty = _extract(payload, "qty", "quantity")
        if qty is not None:
            try:
                qty_value = int(qty)
            except (TypeError, ValueError):
                raise ValueError("qty must be an integer")

            if qty_value != 1:
                raise ValueError("Only qty=1 is supported for waitlist joins")

        source = _extract(payload, "source")
        if source is None:
            source = "PUBLIC"
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be a non-empty string")

        metadata = _extract(payload, "metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")

        priority_raw = _extract(payload, "priorityScore", "priority_score")
        if priority_raw is None:
            priority_score = 0.0
        else:
            try:
                priority_score = float(priority_raw)
            except (TypeError, ValueError):
                raise ValueError("priorityScore must be a number")

        repo = _get_repo()
        category = repo.resolve_category(event_id, seat_category)
        if category is None:
            return _json_error("Seat category not found for event", 404)

        row = repo.join_waitlist(
            event_id=event_id,
            category_id=category["category_id"],
            user_id=user_id,
            priority_score=priority_score,
            source=source.strip(),
            metadata=metadata,
        )
        entry = _decorate_entries(repo, [row], include_email=False)[0]

        return (
            jsonify(
                {
                    "waitlistID": entry["waitlistID"],
                    "position": entry["position"],
                    "status": entry["status"],
                    "entry": entry,
                }
            ),
            201,
        )
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


@waitlist_bp.get("/waitlist/next")
def get_next_waitlist_entry():
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    event_raw = request.args.get("eventID")
    seat_category_raw = request.args.get("seatCategory")

    try:
        if not event_raw:
            raise ValueError("eventID is required")
        if not seat_category_raw:
            raise ValueError("seatCategory is required")

        event_id = _parse_uuid(event_raw, "eventID")
        seat_category = _parse_seat_category(seat_category_raw)

        repo = _get_repo()
        category = repo.resolve_category(event_id, seat_category)
        if category is None:
            return _json_error("Seat category not found for event", 404)

        row = repo.get_next_waiting(event_id=event_id, category_id=category["category_id"])
        if row is None:
            return _json_error("No waiting users for event and seatCategory", 404)

        entry = _decorate_entries(repo, [row], include_email=False)[0]
        return jsonify(entry), 200
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


@waitlist_bp.get("/waitlist/by-hold/<hold_id>")
def get_waitlist_by_hold(hold_id: str):
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    try:
        hold_uuid = _parse_uuid(hold_id, "holdID")

        repo = _get_repo()
        row = repo.get_by_hold(hold_uuid)
        if row is None:
            return _json_error("Waitlist entry not found for holdID", 404)

        entry = _decorate_entries(repo, [row], include_email=False)[0]
        return jsonify(entry), 200
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


@waitlist_bp.get("/waitlist/status/<hold_id>")
def get_waitlist_status_for_hold(hold_id: str):
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    try:
        hold_uuid = _parse_uuid(hold_id, "holdID")
        limit = _parse_positive_int(
            request.args.get("limit"),
            field_name="limit",
            default=20,
            max_value=current_app.config["WAITLIST_MAX_LIMIT"],
        )

        repo = _get_repo()
        context = repo.get_hold_context(hold_uuid)
        if context is None:
            return _json_error("Hold not found", 404)

        rows = repo.get_waiting_for_context(
            event_id=context["event_id"],
            category_id=context["category_id"],
            limit=limit,
        )
        entries = _decorate_entries(repo, rows, include_email=False)

        category_map = repo.get_category_map({context["category_id"]})
        category = category_map.get(context["category_id"], {})

        return (
            jsonify(
                {
                    "holdID": hold_uuid,
                    "eventID": context["event_id"],
                    "categoryID": context["category_id"],
                    "seatCategory": category.get("category_code"),
                    "hasWaitlist": bool(entries),
                    "count": len(entries),
                    "nextUser": entries[0] if entries else None,
                    "entries": entries,
                }
            ),
            200,
        )
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


@waitlist_bp.delete("/waitlist/users/<user_id>")
def dequeue_waitlist_user(user_id: str):
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    hold_raw = request.args.get("holdID")
    if not hold_raw:
        return _json_error("holdID query parameter is required", 400)

    try:
        user_uuid = _parse_uuid(user_id, "userID")
        hold_uuid = _parse_uuid(hold_raw, "holdID")

        repo = _get_repo()
        context = repo.get_hold_context(hold_uuid)
        if context is None:
            return _json_error("Hold not found", 404)

        entry = repo.get_active_entry_for_user(
            user_id=user_uuid,
            event_id=context["event_id"],
            category_id=context["category_id"],
            active_statuses=["WAITING"],
        )
        if entry is None:
            return _json_error("Active waitlist entry not found for user and hold context", 404)

        updated = repo.update_entry(
            entry["waitlist_id"],
            {
                "status": "CANCELLED",
                "hold_id": entry.get("hold_id") or hold_uuid,
            },
        )
        if updated is None:
            raise WaitlistNotFoundError("Waitlist entry not found")

        decorated = _decorate_entries(repo, [updated], include_email=False)[0]
        return (
            jsonify(
                {
                    "waitlistID": decorated["waitlistID"],
                    "userID": decorated["userID"],
                    "status": decorated["status"],
                    "holdID": decorated["holdID"],
                }
            ),
            200,
        )
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


@waitlist_bp.get("/waitlist/<waitlist_id>")
def get_waitlist_entry(waitlist_id: str):
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    try:
        waitlist_uuid = _parse_uuid(waitlist_id, "waitlistID")
        include_email = _parse_bool(request.args.get("includeEmail"), field_name="includeEmail", default=False)

        repo = _get_repo()
        row = repo.get_entry(waitlist_uuid)
        if row is None:
            return _json_error("Waitlist entry not found", 404)

        entry = _decorate_entries(repo, [row], include_email=include_email)[0]
        return jsonify(entry), 200
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


@waitlist_bp.put("/waitlist/<waitlist_id>/offer")
def mark_waitlist_offered(waitlist_id: str):
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("Request body must be a JSON object", 400)

    try:
        waitlist_uuid = _parse_uuid(waitlist_id, "waitlistID")
        hold_uuid = _parse_optional_hold_id(payload)

        repo = _get_repo()
        updated = _transition_waitlist_entry(
            repo,
            waitlist_id=waitlist_uuid,
            target_status="HOLD_OFFERED",
            hold_id=hold_uuid,
        )

        entry = _decorate_entries(repo, [updated], include_email=False)[0]
        return jsonify({"waitlistID": entry["waitlistID"], "status": entry["status"], "holdID": entry["holdID"]}), 200
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


@waitlist_bp.put("/waitlist/<waitlist_id>/confirm")
def mark_waitlist_confirmed(waitlist_id: str):
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return _json_error("Request body must be a JSON object", 400)

    try:
        waitlist_uuid = _parse_uuid(waitlist_id, "waitlistID")
        hold_uuid = _parse_optional_hold_id(payload)

        repo = _get_repo()
        updated = _transition_waitlist_entry(
            repo,
            waitlist_id=waitlist_uuid,
            target_status="CONFIRMED",
            hold_id=hold_uuid,
        )

        entry = _decorate_entries(repo, [updated], include_email=False)[0]
        return jsonify({"waitlistID": entry["waitlistID"], "status": entry["status"], "holdID": entry["holdID"]}), 200
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


@waitlist_bp.put("/waitlist/<waitlist_id>/expire")
def mark_waitlist_expired(waitlist_id: str):
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return _json_error("Request body must be a JSON object", 400)

    try:
        waitlist_uuid = _parse_uuid(waitlist_id, "waitlistID")
        hold_uuid = _parse_optional_hold_id(payload)

        repo = _get_repo()
        updated = _transition_waitlist_entry(
            repo,
            waitlist_id=waitlist_uuid,
            target_status="EXPIRED",
            hold_id=hold_uuid,
        )

        entry = _decorate_entries(repo, [updated], include_email=False)[0]
        return jsonify({"waitlistID": entry["waitlistID"], "status": entry["status"], "holdID": entry["holdID"]}), 200
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _handle_repo_error(error)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_error):
        return _json_error("Not found", 404)

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return _json_error("Method not allowed", 405)

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Unhandled error: %s", error)
        return _json_error("Internal server error", 500)


def _build_openapi_spec(base_url: str, auth_header_name: str) -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "TicketBlitz Waitlist Service API",
            "version": "1.0.0",
            "description": "Waitlist management endpoints for queue operations and hold lifecycle transitions.",
        },
        "servers": [{"url": base_url}],
        "components": {
            "securitySchemes": {
                "InternalToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": auth_header_name,
                    "description": "Internal service token required for protected endpoints.",
                }
            },
            "schemas": {
                "HealthResponse": {
                    "type": "object",
                    "required": ["status", "service", "supabaseConfigured"],
                    "properties": {
                        "status": {"type": "string", "example": "ok"},
                        "service": {"type": "string", "example": "waitlist-service"},
                        "supabaseConfigured": {"type": "boolean", "example": True},
                    },
                },
                "ErrorResponse": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {"type": "string"},
                        "details": {"type": "string"},
                    },
                },
                "WaitlistEntry": {
                    "type": "object",
                    "required": [
                        "waitlistID",
                        "eventID",
                        "categoryID",
                        "userID",
                        "status",
                        "metadata",
                    ],
                    "properties": {
                        "waitlistID": {"type": "string", "format": "uuid"},
                        "eventID": {"type": "string", "format": "uuid"},
                        "categoryID": {"type": "string", "format": "uuid"},
                        "seatCategory": {"type": "string", "nullable": True},
                        "userID": {"type": "string", "format": "uuid"},
                        "holdID": {"type": "string", "format": "uuid", "nullable": True},
                        "status": {
                            "type": "string",
                            "enum": ["WAITING", "HOLD_OFFERED", "CONFIRMED", "EXPIRED", "CANCELLED"],
                        },
                        "position": {"type": "integer", "nullable": True},
                        "joinedAt": {"type": "string", "format": "date-time", "nullable": True},
                        "offeredAt": {"type": "string", "format": "date-time", "nullable": True},
                        "confirmedAt": {"type": "string", "format": "date-time", "nullable": True},
                        "expiredAt": {"type": "string", "format": "date-time", "nullable": True},
                        "priorityScore": {"type": "number"},
                        "source": {"type": "string", "nullable": True},
                        "metadata": {"type": "object"},
                        "email": {"type": "string", "format": "email", "nullable": True},
                    },
                },
                "WaitlistListResponse": {
                    "type": "object",
                    "required": ["entries", "count"],
                    "properties": {
                        "entries": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/WaitlistEntry"},
                        },
                        "count": {"type": "integer", "minimum": 0},
                    },
                },
                "JoinWaitlistRequest": {
                    "type": "object",
                    "required": ["userID", "eventID", "seatCategory"],
                    "properties": {
                        "userID": {"type": "string", "format": "uuid"},
                        "eventID": {"type": "string", "format": "uuid"},
                        "seatCategory": {"type": "string", "maxLength": 50},
                        "qty": {
                            "type": "integer",
                            "description": "Only qty=1 is currently supported.",
                            "default": 1,
                            "enum": [1],
                        },
                        "source": {"type": "string", "default": "PUBLIC"},
                        "priorityScore": {"type": "number", "default": 0},
                        "metadata": {"type": "object"},
                    },
                },
                "JoinWaitlistResponse": {
                    "type": "object",
                    "required": ["waitlistID", "position", "status", "entry"],
                    "properties": {
                        "waitlistID": {"type": "string", "format": "uuid"},
                        "position": {"type": "integer", "nullable": True},
                        "status": {"type": "string"},
                        "entry": {"$ref": "#/components/schemas/WaitlistEntry"},
                    },
                },
                "HoldTransitionRequest": {
                    "type": "object",
                    "properties": {
                        "holdID": {"type": "string", "format": "uuid"},
                    },
                },
                "TransitionResponse": {
                    "type": "object",
                    "required": ["waitlistID", "status", "holdID"],
                    "properties": {
                        "waitlistID": {"type": "string", "format": "uuid"},
                        "status": {
                            "type": "string",
                            "enum": ["WAITING", "HOLD_OFFERED", "CONFIRMED", "EXPIRED", "CANCELLED"],
                        },
                        "holdID": {"type": "string", "format": "uuid", "nullable": True},
                    },
                },
                "WaitlistStatusResponse": {
                    "type": "object",
                    "required": [
                        "holdID",
                        "eventID",
                        "categoryID",
                        "hasWaitlist",
                        "count",
                        "nextUser",
                        "entries",
                    ],
                    "properties": {
                        "holdID": {"type": "string", "format": "uuid"},
                        "eventID": {"type": "string", "format": "uuid"},
                        "categoryID": {"type": "string", "format": "uuid"},
                        "seatCategory": {"type": "string", "nullable": True},
                        "hasWaitlist": {"type": "boolean"},
                        "count": {"type": "integer", "minimum": 0},
                        "nextUser": {
                            "allOf": [{"$ref": "#/components/schemas/WaitlistEntry"}],
                            "nullable": True,
                        },
                        "entries": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/WaitlistEntry"},
                        },
                    },
                },
                "DequeueResponse": {
                    "type": "object",
                    "required": ["waitlistID", "userID", "status", "holdID"],
                    "properties": {
                        "waitlistID": {"type": "string", "format": "uuid"},
                        "userID": {"type": "string", "format": "uuid"},
                        "status": {
                            "type": "string",
                            "enum": ["WAITING", "HOLD_OFFERED", "CONFIRMED", "EXPIRED", "CANCELLED"],
                        },
                        "holdID": {"type": "string", "format": "uuid", "nullable": True},
                    },
                },
            },
        },
        "paths": {
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
            "/waitlist": {
                "get": {
                    "summary": "List waitlist entries",
                    "tags": ["Waitlist"],
                    "security": [{"InternalToken": []}],
                    "parameters": [
                        {
                            "name": "eventID",
                            "in": "query",
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "userID",
                            "in": "query",
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["WAITING", "HOLD_OFFERED", "CONFIRMED", "EXPIRED", "CANCELLED"],
                            },
                        },
                        {
                            "name": "seatCategory",
                            "in": "query",
                            "schema": {"type": "string", "maxLength": 50},
                        },
                        {
                            "name": "includeEmail",
                            "in": "query",
                            "schema": {"type": "boolean", "default": False},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "default": BaseConfig.WAITLIST_DEFAULT_LIMIT,
                                "maximum": BaseConfig.WAITLIST_MAX_LIMIT,
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Waitlist entries response",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/WaitlistListResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Supabase unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/waitlist/join": {
                "post": {
                    "summary": "Join waitlist",
                    "tags": ["Waitlist"],
                    "security": [{"InternalToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/JoinWaitlistRequest"}
                            }
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "Created waitlist entry",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/JoinWaitlistResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Seat category not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "409": {
                            "description": "Conflict",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Supabase unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/waitlist/next": {
                "get": {
                    "summary": "Get next waiting user for event and seat category",
                    "tags": ["Waitlist"],
                    "security": [{"InternalToken": []}],
                    "parameters": [
                        {
                            "name": "eventID",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "seatCategory",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "maxLength": 50},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Next waitlist entry",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/WaitlistEntry"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "No matching waitlist user",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Supabase unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/waitlist/by-hold/{hold_id}": {
                "get": {
                    "summary": "Get waitlist entry by hold ID",
                    "tags": ["Waitlist"],
                    "security": [{"InternalToken": []}],
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
                            "description": "Waitlist entry",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/WaitlistEntry"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Entry not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Supabase unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/waitlist/status/{hold_id}": {
                "get": {
                    "summary": "Get waitlist summary for a hold context",
                    "tags": ["Waitlist"],
                    "security": [{"InternalToken": []}],
                    "parameters": [
                        {
                            "name": "hold_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "default": 20,
                                "maximum": BaseConfig.WAITLIST_MAX_LIMIT,
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Waitlist summary",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/WaitlistStatusResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
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
                            "description": "Supabase unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/waitlist/users/{user_id}": {
                "delete": {
                    "summary": "Dequeue a user from waitlist in hold context",
                    "tags": ["Waitlist"],
                    "security": [{"InternalToken": []}],
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "holdID",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Dequeued user",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/DequeueResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Supabase unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/waitlist/{waitlist_id}": {
                "get": {
                    "summary": "Get one waitlist entry",
                    "description": "includeEmail=true requires the internal token header.",
                    "tags": ["Waitlist"],
                    "parameters": [
                        {
                            "name": "waitlist_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "includeEmail",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "boolean", "default": False},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Waitlist entry",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/WaitlistEntry"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Entry not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Supabase unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/waitlist/{waitlist_id}/offer": {
                "put": {
                    "summary": "Transition WAITING to HOLD_OFFERED",
                    "tags": ["Waitlist"],
                    "security": [{"InternalToken": []}],
                    "parameters": [
                        {
                            "name": "waitlist_id",
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
                                    "allOf": [
                                        {"$ref": "#/components/schemas/HoldTransitionRequest"},
                                        {"required": ["holdID"]},
                                    ]
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Updated waitlist state",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/TransitionResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Entry not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "409": {
                            "description": "Invalid status transition or conflicting hold",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Supabase unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/waitlist/{waitlist_id}/confirm": {
                "put": {
                    "summary": "Transition HOLD_OFFERED to CONFIRMED",
                    "tags": ["Waitlist"],
                    "security": [{"InternalToken": []}],
                    "parameters": [
                        {
                            "name": "waitlist_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/HoldTransitionRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Updated waitlist state",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/TransitionResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Entry not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "409": {
                            "description": "Invalid status transition or conflicting hold",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Supabase unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/waitlist/{waitlist_id}/expire": {
                "put": {
                    "summary": "Transition HOLD_OFFERED to EXPIRED",
                    "tags": ["Waitlist"],
                    "security": [{"InternalToken": []}],
                    "parameters": [
                        {
                            "name": "waitlist_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/HoldTransitionRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Updated waitlist state",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/TransitionResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "404": {
                            "description": "Entry not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "409": {
                            "description": "Invalid status transition or conflicting hold",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                        "503": {
                            "description": "Supabase unavailable",
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
    }


def _build_swagger_ui_html(openapi_url: str) -> str:
    return """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>TicketBlitz Waitlist Service API Docs</title>
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
        persistAuthorization: true,
      }});
    </script>
  </body>
</html>
""".format(openapi_url=openapi_url)


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    load_dotenv(override=False)

    app = Flask(__name__)
    app.config.from_object(BaseConfig)

    if test_config:
        app.config.update(test_config)

    CORS(app)
    app.register_blueprint(waitlist_bp)

    @app.get("/openapi.json")
    def openapi_json():
        base_url = request.host_url.rstrip("/")
        return jsonify(_build_openapi_spec(base_url, app.config.get("INTERNAL_AUTH_HEADER", "X-Internal-Token")))

    @app.get("/docs")
    def swagger_docs():
        return Response(_build_swagger_ui_html("/openapi.json"), mimetype="text/html")

    _register_error_handlers(app)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
