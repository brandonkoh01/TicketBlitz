from __future__ import annotations

import hmac
import logging
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from flask import Blueprint, Flask, current_app, jsonify, request
from flask_cors import CORS
from postgrest.exceptions import APIError

from shared.db import db_configured, get_db
from shared.openapi import register_openapi_routes
from shared.swagger_specs import get_service_swagger_spec

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


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
    SERVICE_NAME = os.getenv("SERVICE_NAME", "user-service")
    USERS_DEFAULT_PAGE_SIZE = max(_env_int("USERS_DEFAULT_PAGE_SIZE", 20), 1)
    USERS_MAX_PAGE_SIZE = max(_env_int("USERS_MAX_PAGE_SIZE", 100), USERS_DEFAULT_PAGE_SIZE)
    INTERNAL_AUTH_HEADER = os.getenv("USER_SERVICE_AUTH_HEADER", "X-Internal-Token")
    INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "")
    REQUIRE_INTERNAL_AUTH = _env_bool("REQUIRE_INTERNAL_AUTH", True)


class UserRepository:
    SELECT_COLUMNS = "user_id,full_name,email,phone,metadata,created_at,updated_at,deleted_at"

    def __init__(self):
        self._client = get_db()

    def get_by_id(self, user_id: str, include_deleted: bool = False) -> dict[str, Any] | None:
        query = self._client.table("users").select(self.SELECT_COLUMNS).eq("user_id", user_id).limit(1)
        if not include_deleted:
            query = query.is_("deleted_at", "null")

        result = query.execute()
        rows = result.data or []
        return rows[0] if rows else None

    def list_users(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        query = (
            self._client.table("users")
            .select(self.SELECT_COLUMNS, count="exact")
            .order("created_at", desc=False)
        )

        if not include_deleted:
            query = query.is_("deleted_at", "null")

        if search:
            pattern = f"%{search.strip()}%"
            if "@" in search:
                query = query.ilike("email", pattern)
            else:
                query = query.ilike("full_name", pattern)

        offset = (page - 1) * page_size
        result = query.range(offset, offset + page_size - 1).execute()

        rows = result.data or []
        total = result.count if result.count is not None else len(rows)
        return rows, total

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        result = self._client.table("users").insert(payload).execute()
        rows = result.data or []
        return rows[0] if rows else None

    def update_user(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = (
            self._client.table("users")
            .update(payload)
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None


user_bp = Blueprint("user_service", __name__)


def _json_error(message: str, status_code: int, details: Any | None = None):
    payload = {"error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


def _parse_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError):
        raise ValueError("userID must be a valid UUID")


def _parse_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError("Boolean query parameter must be one of true/false")


def _parse_positive_int(
    raw: str | None,
    field_name: str,
    *,
    default: int,
    max_value: int | None = None,
) -> int:
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(f"{field_name} must be an integer")

    if value < 1:
        raise ValueError(f"{field_name} must be >= 1")

    if max_value is not None and value > max_value:
        raise ValueError(f"{field_name} must be <= {max_value}")

    return value


def _normalize_name(name: Any) -> str:
    if not isinstance(name, str):
        raise ValueError("name must be a string")

    normalized = name.strip()
    if not normalized:
        raise ValueError("name must not be empty")

    if len(normalized) > 100:
        raise ValueError("name must be <= 100 characters")

    return normalized


def _normalize_email(email: Any) -> str:
    if not isinstance(email, str):
        raise ValueError("email must be a string")

    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("email must be a valid address")

    return normalized


def _normalize_phone(phone: Any) -> str | None:
    if phone is None:
        return None
    if not isinstance(phone, str):
        raise ValueError("phone must be a string")

    normalized = phone.strip()
    if not normalized:
        return None

    if len(normalized) > 20:
        raise ValueError("phone must be <= 20 characters")

    return normalized


def _extract_field(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _parse_user_payload(payload: Any, *, partial: bool) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")

    parsed: dict[str, Any] = {}

    name = _extract_field(payload, "name", "fullName", "full_name")
    email = _extract_field(payload, "email")
    phone = _extract_field(payload, "phone")
    metadata = _extract_field(payload, "metadata")

    if name is None and not partial:
        raise ValueError("name is required")
    if email is None and not partial:
        raise ValueError("email is required")

    if name is not None:
        parsed["full_name"] = _normalize_name(name)
    if email is not None:
        parsed["email"] = _normalize_email(email)
    if phone is not None:
        parsed["phone"] = _normalize_phone(phone)

    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")
        parsed["metadata"] = metadata
    elif not partial:
        parsed["metadata"] = {}

    if partial and not parsed:
        raise ValueError("At least one updatable field is required")

    return parsed


def _serialize_user_contract(row: dict[str, Any]) -> dict[str, Any]:
    user_id = row.get("user_id")
    full_name = row.get("full_name")

    return {
        "userID": user_id,
        "name": full_name,
        "email": row.get("email"),
    }


def _serialize_user_detail(row: dict[str, Any]) -> dict[str, Any]:
    payload = _serialize_user_contract(row)
    payload.update(
        {
            "phone": row.get("phone"),
            "metadata": row.get("metadata") or {},
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
            "deletedAt": row.get("deleted_at"),
        }
    )
    return payload


def _get_repo() -> UserRepository:
    repo = current_app.config.get("USER_REPOSITORY")
    if repo is None:
        repo = UserRepository()
        current_app.config["USER_REPOSITORY"] = repo
    return repo


def _handle_repo_error(error: Exception):
    if isinstance(error, APIError):
        code = getattr(error, "code", None)

        if code == "23505":
            return _json_error("User already exists", 409)

        if code in {"22P02", "23514"}:
            return _json_error("Invalid request data", 400, details=getattr(error, "details", None))

    message = str(error).lower()
    if "duplicate" in message and "key" in message:
        return _json_error("User already exists", 409)

    logger.exception("Repository operation failed: %s", error)
    return _json_error("Failed to process user request", 500)


@user_bp.before_request
def _require_internal_auth():
    if request.endpoint == "user_service.health":
        return None

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


@user_bp.get("/health")
def health():
    return (
        jsonify(
            {
                "status": "ok",
                "service": current_app.config.get("SERVICE_NAME", "user-service"),
                "supabaseConfigured": db_configured(),
            }
        ),
        200,
    )


@user_bp.get("/user/<user_id>")
def get_user(user_id: str):
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    try:
        user_uuid = _parse_uuid(user_id)
        include_deleted = _parse_bool(
            request.args.get("includeDeleted", request.args.get("include_deleted")), default=False
        )
    except ValueError as error:
        return _json_error(str(error), 400)

    try:
        user = _get_repo().get_by_id(user_uuid, include_deleted=include_deleted)
    except Exception as error:
        return _handle_repo_error(error)

    if user is None:
        return _json_error("User not found", 404)

    return jsonify(_serialize_user_contract(user)), 200


@user_bp.get("/users")
def list_users():
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    try:
        page = _parse_positive_int(request.args.get("page"), "page", default=1)
        page_size = _parse_positive_int(
            request.args.get("pageSize", request.args.get("page_size")),
            "pageSize",
            default=current_app.config["USERS_DEFAULT_PAGE_SIZE"],
            max_value=current_app.config["USERS_MAX_PAGE_SIZE"],
        )
        include_deleted = _parse_bool(
            request.args.get("includeDeleted", request.args.get("include_deleted")), default=False
        )
        search = (request.args.get("search") or "").strip()
        if len(search) > 120:
            raise ValueError("search must be <= 120 characters")
    except ValueError as error:
        return _json_error(str(error), 400)

    try:
        users, total = _get_repo().list_users(
            page=page,
            page_size=page_size,
            search=search or None,
            include_deleted=include_deleted,
        )
    except Exception as error:
        return _handle_repo_error(error)

    total_pages = math.ceil(total / page_size) if total else 0
    return (
        jsonify(
            {
                "users": [_serialize_user_detail(user) for user in users],
                "pagination": {
                    "page": page,
                    "pageSize": page_size,
                    "total": total,
                    "totalPages": total_pages,
                },
            }
        ),
        200,
    )


@user_bp.post("/users")
def create_user():
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    payload = request.get_json(silent=True)
    try:
        create_payload = _parse_user_payload(payload, partial=False)
    except ValueError as error:
        return _json_error(str(error), 400)

    try:
        created = _get_repo().create_user(create_payload)
    except Exception as error:
        return _handle_repo_error(error)

    if created is None:
        return _json_error("User could not be created", 500)

    return jsonify(_serialize_user_detail(created)), 201


@user_bp.put("/user/<user_id>")
def update_user(user_id: str):
    if not db_configured():
        return _json_error("Supabase is not configured", 503)

    try:
        user_uuid = _parse_uuid(user_id)
    except ValueError as error:
        return _json_error(str(error), 400)

    payload = request.get_json(silent=True)
    try:
        update_payload = _parse_user_payload(payload, partial=True)
    except ValueError as error:
        return _json_error(str(error), 400)

    try:
        updated = _get_repo().update_user(user_uuid, update_payload)
    except Exception as error:
        return _handle_repo_error(error)

    if updated is None:
        return _json_error("User not found", 404)

    return jsonify(_serialize_user_detail(updated)), 200


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


def _build_openapi_spec(base_url: str) -> dict[str, Any]:
    spec = get_service_swagger_spec("user-service")
    spec["servers"] = [{"url": base_url}]
    return spec


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    load_dotenv(override=False)

    app = Flask(__name__)
    app.config.from_object(BaseConfig)

    if test_config:
        app.config.update(test_config)

    CORS(app)
    app.register_blueprint(user_bp)

    register_openapi_routes(app, lambda: _build_openapi_spec(request.host_url.rstrip("/")))

    _register_error_handlers(app)
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
