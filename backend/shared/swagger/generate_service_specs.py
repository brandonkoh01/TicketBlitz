from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = Path(__file__).resolve().parent / "ticketblitz-service-specs.json"


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_default_env() -> None:
    os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "doc-build-token")
    os.environ.setdefault("USER_SERVICE_URL", "http://user-service:5000")
    os.environ.setdefault("INVENTORY_SERVICE_URL", "http://inventory-service:5000")
    os.environ.setdefault("PAYMENT_SERVICE_URL", "http://payment-service:5000")
    os.environ.setdefault("WAITLIST_SERVICE_URL", "http://waitlist-service:5000")
    os.environ.setdefault("EVENT_SERVICE_URL", "http://event-service:5000")


def build_service_specs() -> dict[str, Any]:
    _set_default_env()

    specs: dict[str, Any] = {}

    user_mod = _load_module("user_service_doc_src", BACKEND_ROOT / "atomic/user-service/user.py")
    specs["user-service"] = user_mod._build_openapi_spec("http://localhost:5000")

    waitlist_mod = _load_module("waitlist_service_doc_src", BACKEND_ROOT / "atomic/waitlist-service/waitlist.py")
    specs["waitlist-service"] = waitlist_mod._build_openapi_spec("http://localhost:5000", "X-Internal-Token")

    payment_mod = _load_module("payment_service_doc_src", BACKEND_ROOT / "atomic/payment-service/payment.py")
    specs["payment-service"] = payment_mod._build_openapi_spec()

    booking_mod = _load_module("booking_status_doc_src", BACKEND_ROOT / "composite/booking-status-service/booking_status.py")
    specs["booking-status-service"] = booking_mod._build_openapi_spec("http://localhost:5000")

    cancellation_mod = _load_module(
        "cancellation_doc_src",
        BACKEND_ROOT / "composite/cancellation-orchestrator/cancellation_orchestrator.py",
    )
    specs["cancellation-orchestrator"] = cancellation_mod._build_openapi_spec("http://localhost:5000")

    reservation_mod = _load_module("reservation_doc_src", BACKEND_ROOT / "composite/reservation-orchestrator/app.py")
    specs["reservation-orchestrator"] = reservation_mod._build_openapi("reservation-orchestrator")

    inventory_mod = _load_module("inventory_doc_src", BACKEND_ROOT / "atomic/inventory-service/inventory.py")
    inventory_app = inventory_mod.create_app()
    inventory_response = inventory_app.test_client().get("/inventory/openapi.json")
    if inventory_response.status_code == 200:
        specs["inventory-service"] = inventory_response.get_json()

    event_mod = _load_module("event_doc_src", BACKEND_ROOT / "atomic/event-service/event.py")
    event_app = event_mod.create_app()
    event_response = event_app.test_client().get("/apispec_1.json")
    if event_response.status_code == 200:
        specs["event-service"] = event_response.get_json()

    return specs


def main() -> None:
    specs = build_service_specs()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(specs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(specs)} service specs")


if __name__ == "__main__":
    main()
