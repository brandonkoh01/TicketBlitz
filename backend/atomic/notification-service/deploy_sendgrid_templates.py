"""Create/update SendGrid dynamic templates for TicketBlitz notification emails.

Usage:
  python deploy_sendgrid_templates.py --env-file ../../.env.local
  python deploy_sendgrid_templates.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Dict, Iterable, List, Tuple

from sendgrid import SendGridAPIClient

# Ensure shared/ imports resolve when running this script directly.
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from shared.sendgrid_templates import build_notification_template_definitions


def _response_json(response) -> Dict[str, object]:
    body = response.body
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8")

    if not body:
        return {}

    return json.loads(body)


def _require_status(response, *, allowed: Iterable[int], operation: str) -> None:
    if int(response.status_code) in set(allowed):
        return

    raise RuntimeError(
        f"{operation} failed with status={response.status_code}, body={response.body}"
    )


def _list_templates(client: SendGridAPIClient) -> List[Dict[str, object]]:
    response = client.client.templates.get(query_params={"generations": "dynamic"})
    _require_status(response, allowed={200}, operation="list templates")
    payload = _response_json(response)
    templates = payload.get("templates", []) if isinstance(payload, dict) else []
    if not isinstance(templates, list):
        return []
    return templates


def _find_template_id(templates: List[Dict[str, object]], template_name: str) -> str:
    for template in templates:
        if template.get("name") == template_name and template.get("id"):
            return str(template["id"])
    return ""


def _ensure_template(
    client: SendGridAPIClient,
    templates: List[Dict[str, object]],
    template_name: str,
) -> Tuple[str, bool]:
    existing_id = _find_template_id(templates, template_name)
    if existing_id:
        return existing_id, False

    response = client.client.templates.post(
        request_body={"name": template_name, "generation": "dynamic"}
    )
    _require_status(response, allowed={200, 201}, operation=f"create template '{template_name}'")
    payload = _response_json(response)
    template_id = str(payload.get("id", "")) if isinstance(payload, dict) else ""
    if not template_id:
        raise RuntimeError(f"Created template '{template_name}' but no template id returned")

    templates.append({"name": template_name, "id": template_id})
    return template_id, True


def _create_active_version(client: SendGridAPIClient, template_id: str, definition) -> str:
    response = client.client.templates._(template_id).versions.post(
        request_body={
            "active": 1,
            "name": definition.version_name,
            "subject": definition.subject,
            "html_content": definition.html_content,
            "plain_content": definition.plain_content,
        }
    )
    _require_status(
        response,
        allowed={200, 201},
        operation=f"create template version for '{definition.template_name}'",
    )
    payload = _response_json(response)
    if isinstance(payload, dict) and payload.get("id"):
        return str(payload["id"])
    return ""


def _update_env_file(path: pathlib.Path, mapping: Dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    remaining = dict(mapping)

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue

        key, _ = line.split("=", 1)
        key = key.strip()
        if key in remaining:
            lines[idx] = f"{key}={remaining.pop(key)}"

    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create/update TicketBlitz SendGrid dynamic templates."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview template/env mappings without creating template versions.",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help="Optional .env file path to update with generated template IDs.",
    )
    args = parser.parse_args()

    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY is required")

    definitions = build_notification_template_definitions()
    if not definitions:
        raise RuntimeError("No template definitions were generated")

    client = SendGridAPIClient(api_key)
    templates = _list_templates(client)

    env_mapping: Dict[str, str] = {}
    for definition in definitions:
        if args.dry_run:
            existing_id = _find_template_id(templates, definition.template_name)
            if existing_id:
                env_mapping[definition.env_var] = existing_id
                print(
                    f"[dry-run] {definition.notification_type}: "
                    f"template_id={existing_id} created=False"
                )
            else:
                print(
                    f"[dry-run] {definition.notification_type}: "
                    "template_missing=True (would create template and active version)"
                )
            continue

        template_id, created = _ensure_template(client, templates, definition.template_name)
        env_mapping[definition.env_var] = template_id

        version_id = _create_active_version(client, template_id, definition)
        print(
            f"{definition.notification_type}: template_id={template_id} "
            f"version_id={version_id or 'unknown'} created={created}"
        )

    if args.env_file:
        env_path = pathlib.Path(args.env_file)
        if not env_path.is_absolute():
            env_path = pathlib.Path.cwd() / env_path
        _update_env_file(env_path, env_mapping)
        print(f"Updated env file: {env_path}")

    print("\nSet these env vars:")
    for key, value in env_mapping.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
