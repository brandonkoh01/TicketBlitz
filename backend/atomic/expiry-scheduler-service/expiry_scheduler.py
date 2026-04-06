import logging
import math
import os
import random
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util import Retry

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def parse_int_env(name: str, default: int, minimum: Optional[int] = None) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        parsed = int(value)
    except ValueError:
        logger.warning("Invalid integer for %s=%s. Using default=%s", name, value, default)
        return default

    if minimum is not None and parsed < minimum:
        logger.warning("Value for %s=%s is below minimum=%s. Using minimum.", name, parsed, minimum)
        return minimum

    return parsed


def parse_float_env(name: str, default: float, minimum: Optional[float] = None) -> float:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        parsed = float(value)
    except ValueError:
        logger.warning("Invalid float for %s=%s. Using default=%s", name, value, default)
        return default

    if not math.isfinite(parsed):
        logger.warning("Non-finite float for %s=%s. Using default=%s", name, value, default)
        return default

    if minimum is not None and parsed < minimum:
        logger.warning("Value for %s=%s is below minimum=%s. Using minimum.", name, parsed, minimum)
        return minimum

    return parsed


def parse_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logger.warning("Invalid boolean for %s=%s. Using default=%s", name, value, default)
    return default


def validate_http_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be a valid http(s) URL")
    return value.rstrip("/")


@dataclass(frozen=True)
class SchedulerConfig:
    service_name: str
    inventory_service_url: str
    maintenance_path: str
    flash_sale_orchestrator_url: str
    flash_sale_reconcile_path: str
    flash_sale_reconcile_enabled: bool
    expiry_interval_seconds: int
    error_retry_delay_seconds: int
    error_retry_jitter_seconds: float
    request_connect_timeout_seconds: float
    request_read_timeout_seconds: float
    retry_total: int
    retry_backoff_factor: float
    internal_auth_header: str
    internal_service_token: str

    @staticmethod
    def from_env() -> "SchedulerConfig":
        inventory_service_url = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:5000").strip()
        if not inventory_service_url:
            inventory_service_url = "http://inventory-service:5000"
        inventory_service_url = validate_http_url("INVENTORY_SERVICE_URL", inventory_service_url)

        maintenance_path = os.getenv(
            "INVENTORY_EXPIRE_HOLDS_PATH",
            "/inventory/maintenance/expire-holds",
        ).strip()
        if not maintenance_path:
            maintenance_path = "/inventory/maintenance/expire-holds"

        if not maintenance_path.startswith("/"):
            maintenance_path = f"/{maintenance_path}"

        flash_sale_orchestrator_url = os.getenv(
            "FLASH_SALE_ORCHESTRATOR_URL",
            "http://flash-sale-orchestrator:5000",
        ).strip()
        if not flash_sale_orchestrator_url:
            flash_sale_orchestrator_url = "http://flash-sale-orchestrator:5000"
        flash_sale_orchestrator_url = validate_http_url(
            "FLASH_SALE_ORCHESTRATOR_URL",
            flash_sale_orchestrator_url,
        )

        flash_sale_reconcile_path = os.getenv(
            "FLASH_SALE_RECONCILE_PATH",
            "/internal/flash-sale/reconcile-expired",
        ).strip()
        if not flash_sale_reconcile_path:
            flash_sale_reconcile_path = "/internal/flash-sale/reconcile-expired"
        if not flash_sale_reconcile_path.startswith("/"):
            flash_sale_reconcile_path = f"/{flash_sale_reconcile_path}"

        internal_auth_header = os.getenv("INTERNAL_AUTH_HEADER", "X-Internal-Token").strip()
        internal_service_token = os.getenv("INTERNAL_SERVICE_TOKEN", "").strip()

        if internal_service_token and not internal_auth_header:
            raise ValueError("INTERNAL_AUTH_HEADER must be non-empty when INTERNAL_SERVICE_TOKEN is set")

        return SchedulerConfig(
            service_name=os.getenv("SERVICE_NAME", "expiry-scheduler-service"),
            inventory_service_url=inventory_service_url,
            maintenance_path=maintenance_path,
            flash_sale_orchestrator_url=flash_sale_orchestrator_url,
            flash_sale_reconcile_path=flash_sale_reconcile_path,
            flash_sale_reconcile_enabled=parse_bool_env("FLASH_SALE_RECONCILE_ENABLED", False),
            expiry_interval_seconds=parse_int_env("EXPIRY_INTERVAL_SECONDS", 60, minimum=1),
            error_retry_delay_seconds=parse_int_env(
                "EXPIRY_ERROR_RETRY_DELAY_SECONDS",
                5,
                minimum=1,
            ),
            error_retry_jitter_seconds=parse_float_env(
                "EXPIRY_ERROR_RETRY_JITTER_SECONDS",
                0.5,
                minimum=0.0,
            ),
            request_connect_timeout_seconds=parse_float_env(
                "EXPIRY_REQUEST_CONNECT_TIMEOUT_SECONDS",
                3.05,
                minimum=0.1,
            ),
            request_read_timeout_seconds=parse_float_env(
                "EXPIRY_REQUEST_READ_TIMEOUT_SECONDS",
                10.0,
                minimum=0.1,
            ),
            retry_total=parse_int_env("EXPIRY_HTTP_RETRY_TOTAL", 2, minimum=0),
            retry_backoff_factor=parse_float_env(
                "EXPIRY_HTTP_RETRY_BACKOFF_FACTOR",
                0.5,
                minimum=0.0,
            ),
            internal_auth_header=internal_auth_header,
            internal_service_token=internal_service_token,
        )


def build_http_session(config: SchedulerConfig) -> requests.Session:
    retry = Retry(
        total=config.retry_total,
        connect=config.retry_total,
        read=config.retry_total,
        status=config.retry_total,
        backoff_factor=config.retry_backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"POST"}),
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"Accept": "application/json"})
    return session


class ExpiryScheduler:
    def __init__(
        self,
        config: SchedulerConfig,
        session: Optional[requests.Session] = None,
        sleeper: Callable[[float], None] = time.sleep,
        jitterer: Callable[[float, float], float] = random.uniform,
    ):
        self.config = config
        self._session = session or build_http_session(config)
        self._sleeper = sleeper
        self._jitterer = jitterer
        self._shutdown_requested = False
        self.last_success_at: Optional[str] = None

    def request_shutdown(self) -> None:
        self._shutdown_requested = True
        logger.info("Shutdown requested for %s", self.config.service_name)

    @property
    def maintenance_url(self) -> str:
        return f"{self.config.inventory_service_url}{self.config.maintenance_path}"

    @property
    def flash_sale_reconcile_url(self) -> str:
        return f"{self.config.flash_sale_orchestrator_url}{self.config.flash_sale_reconcile_path}"

    def run_once(self) -> bool:
        headers = {"Content-Type": "application/json"}
        if self.config.internal_service_token:
            headers[self.config.internal_auth_header] = self.config.internal_service_token

        success = self._run_inventory_expiry(headers)
        if not success:
            return False

        if self.config.flash_sale_reconcile_enabled:
            success = self._run_flash_sale_reconcile(headers)
            if not success:
                return False

        self.last_success_at = datetime.now(timezone.utc).isoformat()
        return True

    def _run_inventory_expiry(self, headers: dict[str, str]) -> bool:
        try:
            response = self._session.post(
                self.maintenance_url,
                json={},
                headers=headers,
                timeout=(
                    self.config.request_connect_timeout_seconds,
                    self.config.request_read_timeout_seconds,
                ),
            )
        except RequestException as error:
            logger.warning("Expiry batch failed to reach inventory service: %s", error)
            return False

        if response.status_code != 200:
            body = response.text.strip().replace("\n", " ")[:300]
            logger.warning(
                "Inventory maintenance returned status=%s body=%s",
                response.status_code,
                body,
            )
            return False

        try:
            payload = response.json()
        except ValueError as error:
            logger.warning("Inventory maintenance returned invalid JSON: %s", error)
            return False

        if not isinstance(payload, dict):
            logger.warning("Inventory maintenance returned non-object payload: %r", payload)
            return False

        expired_holds = payload.get("expiredHolds")
        count = payload.get("count")
        if not isinstance(count, int):
            count = len(expired_holds) if isinstance(expired_holds, list) else 0

        publish_failures = payload.get("publishFailures", 0)
        if not isinstance(publish_failures, int) or publish_failures < 0:
            logger.warning(
                "Inventory maintenance returned invalid publishFailures=%r. Treating as 0.",
                publish_failures,
            )
            publish_failures = 0

        sample_hold_ids: list[str] = []
        if isinstance(expired_holds, list):
            for item in expired_holds[:3]:
                if isinstance(item, dict) and item.get("holdID"):
                    sample_hold_ids.append(str(item["holdID"]))

        if publish_failures > 0:
            publish_failure_hold_ids = payload.get("publishFailureHoldIDs")
            if not isinstance(publish_failure_hold_ids, list):
                publish_failure_hold_ids = []

            logger.warning(
                "Expiry batch completed with publishFailures=%s publishFailureHoldIDs=%s",
                publish_failures,
                publish_failure_hold_ids[:10],
            )
            return False

        logger.info(
            "Expiry batch completed count=%s sampleHoldIDs=%s lastSuccessAt=%s",
            count,
            sample_hold_ids,
            datetime.now(timezone.utc).isoformat(),
        )
        return True

    def _run_flash_sale_reconcile(self, headers: dict[str, str]) -> bool:
        try:
            response = self._session.post(
                self.flash_sale_reconcile_url,
                json={},
                headers=headers,
                timeout=(
                    self.config.request_connect_timeout_seconds,
                    self.config.request_read_timeout_seconds,
                ),
            )
        except RequestException as error:
            logger.warning("Flash sale reconciliation request failed: %s", error)
            return False

        if response.status_code != 200:
            body = response.text.strip().replace("\n", " ")[:300]
            logger.warning(
                "Flash sale reconciliation returned status=%s body=%s",
                response.status_code,
                body,
            )
            return False

        try:
            payload = response.json()
        except ValueError as error:
            logger.warning("Flash sale reconciliation returned invalid JSON: %s", error)
            return False

        if not isinstance(payload, dict):
            logger.warning("Flash sale reconciliation returned non-object payload: %r", payload)
            return False

        if payload.get("status") != "success":
            logger.warning(
                "Flash sale reconciliation payload indicates failure: %r",
                payload,
            )
            return False

        ended_count = payload.get("endedCount", 0)
        skipped_count = payload.get("skippedCount", 0)
        logger.info(
            "Flash sale reconciliation completed endedCount=%s skippedCount=%s",
            ended_count,
            skipped_count,
        )
        return True

    def _sleep_interruptibly(self, seconds: float) -> None:
        remaining = max(0.0, seconds)
        while remaining > 0 and not self._shutdown_requested:
            chunk = min(1.0, remaining)
            self._sleeper(chunk)
            remaining -= chunk

    def close(self) -> None:
        self._session.close()

    def run_forever(self) -> None:
        logger.info(
            "Starting %s with interval=%ss url=%s",
            self.config.service_name,
            self.config.expiry_interval_seconds,
            self.maintenance_url,
        )

        while not self._shutdown_requested:
            started_at = time.monotonic()
            success = False

            try:
                success = self.run_once()
            except Exception as error:  # pragma: no cover - defensive runtime guard
                logger.exception("Unhandled scheduler error: %s", error)

            if self._shutdown_requested:
                break

            delay_seconds = (
                self.config.expiry_interval_seconds
                if success
                else self.config.error_retry_delay_seconds
            )
            elapsed = time.monotonic() - started_at
            sleep_for = max(0.0, delay_seconds - elapsed)

            if not success and self.config.error_retry_jitter_seconds > 0:
                sleep_for += self._jitterer(0.0, self.config.error_retry_jitter_seconds)

            if sleep_for > 0:
                self._sleep_interruptibly(sleep_for)

        logger.info("%s stopped", self.config.service_name)


def install_signal_handlers(scheduler: ExpiryScheduler) -> None:
    def _handle_signal(signal_number: int, _frame: Any) -> None:
        logger.info("Received signal=%s", signal_number)
        scheduler.request_shutdown()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


def main() -> None:
    try:
        config = SchedulerConfig.from_env()
    except ValueError as error:
        logger.error("Invalid scheduler configuration: %s", error)
        raise SystemExit(1) from error

    scheduler = ExpiryScheduler(config)
    install_signal_handlers(scheduler)

    try:
        scheduler.run_forever()
    finally:
        scheduler.close()


if __name__ == "__main__":
    main()
