import copy
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import Flask, Response, abort, jsonify, send_from_directory

SWAGGER_UI_STATIC_DIR = Path(__file__).resolve().parent / "static" / "swagger-ui"
SWAGGER_UI_REQUIRED_ASSETS = (
    "swagger-ui.css",
    "swagger-ui-bundle.js",
    "swagger-ui-standalone-preset.js",
)

BASE_COMPONENTS: Dict[str, Any] = {
    "schemas": {
        "HealthResponse": {
            "type": "object",
            "required": ["status", "service"],
            "properties": {
                "status": {"type": "string", "example": "ok"},
                "service": {"type": "string", "example": "event-service"},
            },
            "additionalProperties": True,
        },
        "ErrorResponse": {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {"type": "string", "example": "Not found"},
            },
        },
    },
    "parameters": {
        "UserIdPath": {
            "name": "user_id",
            "in": "path",
            "required": True,
            "schema": {"type": "string", "format": "uuid"},
        },
        "EventIdPath": {
            "name": "event_id",
            "in": "path",
            "required": True,
            "schema": {"type": "string", "format": "uuid"},
        },
        "SeatCategoryPath": {
            "name": "seat_category",
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        },
        "EventIdQuery": {
            "name": "eventID",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "format": "uuid"},
        },
    },
    "responses": {
        "BadRequest": {
            "description": "Bad request",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            },
        },
        "NotFound": {
            "description": "Resource not found",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            },
        },
        "InternalServerError": {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            },
        },
        "ServiceUnavailable": {
            "description": "Dependent service unavailable",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            },
        },
    },
}

SWAGGER_UI_HTML = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>API Documentation</title>
        <link rel=\"stylesheet\" href=\"__ASSETS_BASE__/swagger-ui.css\" />
    <style>
      body {
        margin: 0;
        background: #fafafa;
      }
      #swagger-ui {
        max-width: 1200px;
        margin: 0 auto;
      }
    </style>
  </head>
  <body>
    <div id=\"swagger-ui\"></div>
        <script src=\"__ASSETS_BASE__/swagger-ui-bundle.js\"></script>
        <script src=\"__ASSETS_BASE__/swagger-ui-standalone-preset.js\"></script>
    <script>
      window.onload = function () {
        window.ui = SwaggerUIBundle({
          url: "__OPENAPI_URL__",
          dom_id: '#swagger-ui',
          presets: [
            SwaggerUIBundle.presets.apis,
            SwaggerUIStandalonePreset,
          ],
          plugins: [SwaggerUIBundle.plugins.DownloadUrl],
          layout: 'StandaloneLayout',
          queryConfigEnabled: true,
        });
      };
    </script>
  </body>
</html>
"""


def _merge_components(
    base_components: Dict[str, Any], extra_components: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    components = copy.deepcopy(base_components)
    if not extra_components:
        return components

    for key, value in extra_components.items():
        if isinstance(value, dict) and isinstance(components.get(key), dict):
            components[key].update(value)
        else:
            components[key] = value

    return components


def build_openapi_spec(
    *,
    service_name: str,
    title: str,
    description: str,
    paths: Dict[str, Any],
    extra_components: Optional[Dict[str, Any]] = None,
    version: str = "1.0.0",
) -> Dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "version": version,
            "description": description,
        },
        "servers": [
            {
                "url": "/",
                "description": f"{service_name} root",
            }
        ],
        "paths": paths,
        "components": _merge_components(BASE_COMPONENTS, extra_components),
    }


def register_openapi_routes(
    app: Flask,
    spec_builder: Callable[[], Dict[str, Any]],
    *,
    openapi_path: str = "/openapi.json",
    docs_path: str = "/docs",
) -> None:
    normalized_docs_path = docs_path.rstrip("/") or "/docs"
    swagger_assets_path = f"{normalized_docs_path}/assets"

    @app.get(f"{swagger_assets_path}/<path:filename>")
    def swagger_asset(filename: str):
        if not filename or ".." in filename or filename.startswith("/"):
            abort(404)

        asset_path = SWAGGER_UI_STATIC_DIR / filename
        if not asset_path.is_file():
            abort(404)

        return send_from_directory(str(SWAGGER_UI_STATIC_DIR), filename)

    @app.get(openapi_path)
    def openapi_json():
        return jsonify(spec_builder()), 200

    @app.get(docs_path)
    def swagger_docs():
        missing_assets = [
            name
            for name in SWAGGER_UI_REQUIRED_ASSETS
            if not (SWAGGER_UI_STATIC_DIR / name).is_file()
        ]
        if missing_assets:
            return (
                jsonify(
                    {
                        "error": "Swagger UI assets are missing",
                        "missing": missing_assets,
                    }
                ),
                500,
            )

        html = (
            SWAGGER_UI_HTML.replace("__OPENAPI_URL__", openapi_path)
            .replace("__ASSETS_BASE__", swagger_assets_path)
        )
        return Response(html, mimetype="text/html")
