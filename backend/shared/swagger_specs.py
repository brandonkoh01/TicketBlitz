from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

SWAGGER_SPECS_PATH = Path(__file__).resolve().parent / "swagger" / "ticketblitz-service-specs.json"


@lru_cache(maxsize=1)
def _load_swagger_specs() -> dict[str, Any]:
    with SWAGGER_SPECS_PATH.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)

    if not isinstance(loaded, dict):
        raise ValueError("Centralized swagger specs file must contain a JSON object")

    return loaded


def get_service_swagger_spec(service_name: str) -> dict[str, Any]:
    specs = _load_swagger_specs()
    if service_name not in specs:
        raise KeyError(f"Unknown service spec: {service_name}")

    spec = specs[service_name]
    if not isinstance(spec, dict):
        raise ValueError(f"Invalid swagger spec format for service: {service_name}")

    return deepcopy(spec)
