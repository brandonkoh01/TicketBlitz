import hashlib
import json
import logging
import math
import os
import signal
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlencode, urlparse

import pika
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util import Retry

from shared.mq import get_connection, publish_json, rabbitmq_configured

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


def validate_http_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be a valid http(s) URL")
    return value.rstrip("/")


class ProcessingError(Exception):
    """Base processing error."""


class PermanentProcessingError(ProcessingError):
    """Non-retryable processing error."""


class TransientProcessingError(ProcessingError):
    """Retryable processing error."""


@dataclass(frozen=True)
class WorkerConfig:
    service_name: str
    topic_exchange: str
    seat_released_routing_key: str
    seat_released_queue: str
    seat_released_retry_queue: str
    retry_header_name: str
    retry_delay_ms: int
    max_retry_attempts: int
    reconnect_delay_seconds: int
    inventory_service_url: str
    waitlist_service_url: str
    user_service_url: str
    request_connect_timeout_seconds: float
    request_read_timeout_seconds: float
    http_retry_total: int
    http_retry_backoff_factor: float
    internal_auth_header: str
    internal_service_token: str
    waitlist_payment_url_template: str

    @staticmethod
    def from_env() -> "WorkerConfig":
        service_name = os.getenv("SERVICE_NAME", "waitlist-promotion-orchestrator").strip()
        if not service_name:
            service_name = "waitlist-promotion-orchestrator"

        inventory_service_url = validate_http_url(
            "INVENTORY_SERVICE_URL",
            os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:5000").strip() or "http://inventory-service:5000",
        )
        waitlist_service_url = validate_http_url(
            "WAITLIST_SERVICE_URL",
            os.getenv("WAITLIST_SERVICE_URL", "http://waitlist-service:5000").strip() or "http://waitlist-service:5000",
        )
        user_service_url = validate_http_url(
            "USER_SERVICE_URL",
            os.getenv("USER_SERVICE_URL", "http://user-service:5000").strip() or "http://user-service:5000",
        )

        internal_auth_header = os.getenv("INTERNAL_AUTH_HEADER", "X-Internal-Token").strip()
        internal_service_token = os.getenv("INTERNAL_SERVICE_TOKEN", "").strip()

        if internal_service_token and not internal_auth_header:
            raise ValueError("INTERNAL_AUTH_HEADER must be non-empty when INTERNAL_SERVICE_TOKEN is set")

        return WorkerConfig(
            service_name=service_name,
            topic_exchange=os.getenv("RABBITMQ_EXCHANGE", "ticketblitz"),
            seat_released_routing_key=os.getenv("WAITLIST_PROMOTION_ROUTING_KEY", "seat.released"),
            seat_released_queue=os.getenv(
                "WAITLIST_PROMOTION_QUEUE",
                f"{service_name}.seat.released",
            ),
            seat_released_retry_queue=os.getenv(
                "WAITLIST_PROMOTION_RETRY_QUEUE",
                f"{service_name}.seat.released.retry",
            ),
            retry_header_name=os.getenv("WAITLIST_PROMOTION_RETRY_HEADER", "x-waitlist-promotion-retry"),
            retry_delay_ms=max(100, parse_int_env("WAITLIST_PROMOTION_RETRY_DELAY_MS", 5000)),
            max_retry_attempts=max(0, parse_int_env("WAITLIST_PROMOTION_MAX_RETRIES", 3)),
            reconnect_delay_seconds=max(1, parse_int_env("RABBITMQ_RECONNECT_DELAY", 5)),
            inventory_service_url=inventory_service_url,
            waitlist_service_url=waitlist_service_url,
            user_service_url=user_service_url,
            request_connect_timeout_seconds=parse_float_env(
                "WAITLIST_PROMOTION_REQUEST_CONNECT_TIMEOUT_SECONDS",
                3.05,
                minimum=0.1,
            ),
            request_read_timeout_seconds=parse_float_env(
                "WAITLIST_PROMOTION_REQUEST_READ_TIMEOUT_SECONDS",
                10.0,
                minimum=0.1,
            ),
            http_retry_total=parse_int_env("WAITLIST_PROMOTION_HTTP_RETRY_TOTAL", 2, minimum=0),
            http_retry_backoff_factor=parse_float_env(
                "WAITLIST_PROMOTION_HTTP_RETRY_BACKOFF_FACTOR",
                0.5,
                minimum=0.0,
            ),
            internal_auth_header=internal_auth_header,
            internal_service_token=internal_service_token,
            waitlist_payment_url_template=os.getenv(
                "WAITLIST_PAYMENT_URL_TEMPLATE",
                "/waitlist/confirm/{holdID}",
            ).strip()
            or "/waitlist/confirm/{holdID}",
        )


def build_http_session(config: WorkerConfig) -> requests.Session:
    retry = Retry(
        total=config.http_retry_total,
        connect=config.http_retry_total,
        read=config.http_retry_total,
        status=config.http_retry_total,
        backoff_factor=config.http_retry_backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST", "PUT"}),
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"Accept": "application/json"})
    return session


class WaitlistPromotionWorker:
    def __init__(
        self,
        config: WorkerConfig,
        session: Optional[requests.Session] = None,
        publisher: Callable[..., None] = publish_json,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        self._shutdown_requested = False
        self._session = session or build_http_session(config)
        self._publisher = publisher
        self._sleeper = sleeper

    def request_shutdown(self) -> None:
        self._shutdown_requested = True
        logger.info("Shutdown requested for %s", self.config.service_name)

        if self._connection and self._connection.is_open:
            self._connection.add_callback_threadsafe(self._stop_consuming)

    def _stop_consuming(self) -> None:
        if self._channel and self._channel.is_open:
            try:
                self._channel.stop_consuming()
            except Exception as error:  # pragma: no cover - defensive path
                logger.warning("Unable to stop consuming cleanly: %s", error)

    def run_forever(self) -> None:
        if not rabbitmq_configured():
            raise RuntimeError("RABBITMQ_URL must be set before starting waitlist promotion worker")

        while not self._shutdown_requested:
            try:
                self._connect()
                self._consume()
            except pika.exceptions.ConnectionClosedByBroker as error:
                logger.error("RabbitMQ connection closed by broker: %s", error)
            except pika.exceptions.AMQPChannelError as error:
                logger.error("RabbitMQ channel error: %s", error)
                break
            except pika.exceptions.AMQPConnectionError as error:
                logger.warning("RabbitMQ connection error: %s", error)
            except KeyboardInterrupt:
                self.request_shutdown()
            finally:
                self._cleanup_connection()

            if not self._shutdown_requested:
                logger.info(
                    "Retrying RabbitMQ connection in %s second(s)",
                    self.config.reconnect_delay_seconds,
                )
                self._sleeper(self.config.reconnect_delay_seconds)

        logger.info("%s stopped", self.config.service_name)

    def _connect(self) -> None:
        logger.info("Connecting to RabbitMQ for %s", self.config.service_name)
        self._connection = get_connection()
        self._channel = self._connection.channel()

        self._channel.exchange_declare(
            exchange=self.config.topic_exchange,
            exchange_type="topic",
            durable=True,
        )
        self._channel.queue_declare(queue=self.config.seat_released_queue, durable=True)
        self._channel.queue_declare(
            queue=self.config.seat_released_retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": self.config.retry_delay_ms,
                "x-dead-letter-exchange": self.config.topic_exchange,
                "x-dead-letter-routing-key": self.config.seat_released_routing_key,
            },
        )
        self._channel.queue_bind(
            exchange=self.config.topic_exchange,
            queue=self.config.seat_released_queue,
            routing_key=self.config.seat_released_routing_key,
        )

        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(
            queue=self.config.seat_released_queue,
            on_message_callback=self._handle_delivery,
            auto_ack=False,
        )

        logger.info(
            "Listening on queue=%s routing_key=%s retry_delay=%sms",
            self.config.seat_released_queue,
            self.config.seat_released_routing_key,
            self.config.retry_delay_ms,
        )

    def _consume(self) -> None:
        if not self._channel:
            raise RuntimeError("RabbitMQ channel not initialized")
        self._channel.start_consuming()

    def _cleanup_connection(self) -> None:
        if self._channel:
            try:
                if self._channel.is_open:
                    self._channel.close()
            except Exception:
                pass
            self._channel = None

        if self._connection:
            try:
                if self._connection.is_open:
                    self._connection.close()
            except Exception:
                pass
            self._connection = None

    def close(self) -> None:
        self._session.close()

    def _extract_retry_count(self, properties: pika.BasicProperties) -> int:
        if not properties or not properties.headers:
            return 0

        raw_value = properties.headers.get(self.config.retry_header_name, 0)
        if isinstance(raw_value, int):
            return max(0, raw_value)

        if isinstance(raw_value, str) and raw_value.isdigit():
            return int(raw_value)

        return 0

    def _enqueue_retry(
        self,
        properties: pika.BasicProperties,
        body: bytes,
        retry_count: int,
    ) -> bool:
        if not self._channel or not self._channel.is_open:
            return False

        headers = dict(properties.headers or {})
        headers[self.config.retry_header_name] = retry_count

        next_properties = pika.BasicProperties(
            content_type=properties.content_type or "application/json",
            delivery_mode=properties.delivery_mode or 2,
            headers=headers,
            correlation_id=properties.correlation_id,
            message_id=properties.message_id,
            type=properties.type,
            timestamp=properties.timestamp,
        )

        try:
            self._channel.basic_publish(
                exchange="",
                routing_key=self.config.seat_released_retry_queue,
                body=body,
                properties=next_properties,
                mandatory=False,
            )
            return True
        except Exception as error:
            logger.warning("Unable to republish retry message: %s", error)
            return False

    def _handle_delivery(self, channel, method, properties, body: bytes) -> None:
        delivery_tag = method.delivery_tag
        retry_count = self._extract_retry_count(properties)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Dropping malformed JSON payload: %s", body)
            channel.basic_ack(delivery_tag=delivery_tag)
            return

        if not isinstance(payload, dict):
            logger.error("Dropping non-object payload: %s", payload)
            channel.basic_ack(delivery_tag=delivery_tag)
            return

        try:
            self.process_payload(payload)
            channel.basic_ack(delivery_tag=delivery_tag)
        except PermanentProcessingError as error:
            logger.error("Permanent failure: %s payload=%s", error, payload)
            channel.basic_ack(delivery_tag=delivery_tag)
        except TransientProcessingError as error:
            if retry_count < self.config.max_retry_attempts:
                next_retry_count = retry_count + 1
                if self._enqueue_retry(properties, body, next_retry_count):
                    logger.warning(
                        "Transient failure retry=%s/%s delay=%sms error=%s",
                        next_retry_count,
                        self.config.max_retry_attempts,
                        self.config.retry_delay_ms,
                        error,
                    )
                    channel.basic_ack(delivery_tag=delivery_tag)
                    return

                logger.warning("Retry scheduling failed. Requeueing original delivery: %s", error)
                channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
                return

            logger.error("Retry limit reached. Dropping message: %s", error)
            channel.basic_ack(delivery_tag=delivery_tag)
        except Exception as error:
            logger.exception("Unexpected failure: %s", error)
            channel.basic_ack(delivery_tag=delivery_tag)

    def process_payload(self, payload: dict[str, Any]) -> None:
        event_id = self._require_uuid_like(payload.get("eventID"), "eventID")
        seat_id = self._require_uuid_like(payload.get("seatID"), "seatID")
        seat_category = self._require_non_empty_str(payload.get("seatCategory"), "seatCategory").upper()
        reason = self._require_non_empty_str(payload.get("reason"), "reason").upper()
        expired_hold_id_raw = payload.get("expiredHoldID")
        expired_hold_id = None
        if expired_hold_id_raw is not None and str(expired_hold_id_raw).strip():
            expired_hold_id = self._require_uuid_like(expired_hold_id_raw, "expiredHoldID")
        correlation_id = payload.get("correlationID")

        if reason == "PAYMENT_TIMEOUT" and expired_hold_id:
            self._handle_expired_offer(expired_hold_id, correlation_id)

        next_entry = self._get_next_waitlist_entry(event_id, seat_category)
        if next_entry is None:
            self._set_seat_available(seat_id)
            return

        waitlist_id = self._require_uuid_like(next_entry.get("waitlistID"), "waitlistID")
        user_id = self._require_uuid_like(next_entry.get("userID"), "userID")

        user_email = self._get_user_email(user_id)

        hold = self._create_hold(
            event_id=event_id,
            seat_category=seat_category,
            seat_id=seat_id,
            user_id=user_id,
            waitlist_id=waitlist_id,
        )

        if hold is None:
            return

        hold_id = self._require_uuid_like(hold.get("holdID"), "holdID")
        hold_expiry = self._require_non_empty_str(hold.get("holdExpiry"), "holdExpiry")

        offered = self._mark_waitlist_offered(waitlist_id, hold_id)
        if not offered:
            self._release_hold_cleanup(hold_id)
            return

        payment_url = self._build_payment_url(hold_id)
        self._publish_notification(
            {
                "type": "SEAT_AVAILABLE",
                "email": user_email,
                "holdID": hold_id,
                "holdExpiry": hold_expiry,
                "paymentURL": payment_url,
                "correlationID": correlation_id,
            }
        )

    def _build_payment_url(self, hold_id: str) -> str:
        template = self.config.waitlist_payment_url_template
        if "{holdID}" in template:
            return template.replace("{holdID}", hold_id)
        return f"{template.rstrip('/')}/{hold_id}"

    def _handle_expired_offer(self, expired_hold_id: str, correlation_id: Any) -> None:
        entry = self._get_waitlist_entry_by_hold(expired_hold_id)
        if entry is None:
            return

        waitlist_id = self._require_uuid_like(entry.get("waitlistID"), "waitlistID")
        user_id = self._require_uuid_like(entry.get("userID"), "userID")

        expired_entry = self._mark_waitlist_expired(waitlist_id, expired_hold_id)
        if expired_entry is None:
            return

        user_email = self._get_user_email(user_id)
        self._publish_notification(
            {
                "type": "HOLD_EXPIRED",
                "email": user_email,
                "holdID": expired_hold_id,
                "correlationID": correlation_id,
            }
        )

    def _require_non_empty_str(self, value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise PermanentProcessingError(f"Payload requires non-empty string field '{field_name}'")
        return value.strip()

    def _require_uuid_like(self, value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise PermanentProcessingError(f"Payload requires field '{field_name}'")
        normalized = value.strip()
        try:
            return str(uuid.UUID(normalized))
        except ValueError as error:
            raise PermanentProcessingError(f"Payload field '{field_name}' must be a valid UUID") from error

    def _internal_auth_headers(self) -> dict[str, str]:
        token = self.config.internal_service_token
        if not token:
            return {}
        return {self.config.internal_auth_header: token}

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        internal_auth: bool = False,
        body: Optional[dict[str, Any]] = None,
    ) -> tuple[int, dict[str, Any] | None]:
        headers: dict[str, str] = {}
        if internal_auth:
            headers.update(self._internal_auth_headers())

        try:
            response = self._session.request(
                method,
                url,
                json=body,
                headers=headers,
                timeout=(
                    self.config.request_connect_timeout_seconds,
                    self.config.request_read_timeout_seconds,
                ),
            )
        except RequestException as error:
            raise TransientProcessingError(f"HTTP request failed {method} {url}: {error}") from error

        if not response.text:
            return response.status_code, None

        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}

        if isinstance(payload, dict):
            return response.status_code, payload

        return response.status_code, {"data": payload}

    def _join(self, base_url: str, path: str) -> str:
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    def _get_next_waitlist_entry(self, event_id: str, seat_category: str) -> dict[str, Any] | None:
        query = urlencode({"eventID": event_id, "seatCategory": seat_category})
        url = self._join(self.config.waitlist_service_url, f"/waitlist/next?{query}")
        status_code, payload = self._request_json("GET", url, internal_auth=True)

        if status_code == 404:
            return None
        if status_code == 200 and isinstance(payload, dict):
            return payload
        if status_code >= 500:
            raise TransientProcessingError("Waitlist service unavailable while fetching next entry")

        raise PermanentProcessingError(
            f"Waitlist next lookup failed status={status_code} payload={payload}"
        )

    def _get_waitlist_entry(self, waitlist_id: str) -> dict[str, Any] | None:
        url = self._join(self.config.waitlist_service_url, f"/waitlist/{waitlist_id}")
        status_code, payload = self._request_json("GET", url, internal_auth=True)

        if status_code == 404:
            return None
        if status_code == 200 and isinstance(payload, dict):
            return payload
        if status_code >= 500:
            raise TransientProcessingError("Waitlist service unavailable while loading waitlist entry")

        raise PermanentProcessingError(
            f"Waitlist entry lookup failed status={status_code} payload={payload}"
        )

    def _get_waitlist_entry_by_hold(self, hold_id: str) -> dict[str, Any] | None:
        url = self._join(self.config.waitlist_service_url, f"/waitlist/by-hold/{hold_id}")
        status_code, payload = self._request_json("GET", url, internal_auth=True)

        if status_code == 404:
            return None
        if status_code == 200 and isinstance(payload, dict):
            return payload
        if status_code >= 500:
            raise TransientProcessingError("Waitlist service unavailable while loading hold entry")

        raise PermanentProcessingError(
            f"Waitlist hold lookup failed status={status_code} payload={payload}"
        )

    def _mark_waitlist_expired(self, waitlist_id: str, hold_id: str) -> dict[str, Any] | None:
        url = self._join(self.config.waitlist_service_url, f"/waitlist/{waitlist_id}/expire")
        status_code, payload = self._request_json(
            "PUT",
            url,
            internal_auth=True,
            body={"holdID": hold_id},
        )

        if status_code == 200 and isinstance(payload, dict):
            return payload

        if status_code == 409:
            latest = self._get_waitlist_entry(waitlist_id)
            if latest and latest.get("status") == "EXPIRED" and latest.get("holdID") == hold_id:
                return latest
            return None

        if status_code == 404:
            return None

        if status_code >= 500:
            raise TransientProcessingError("Waitlist service unavailable while expiring entry")

        raise PermanentProcessingError(
            f"Waitlist expire failed status={status_code} payload={payload}"
        )

    def _mark_waitlist_offered(self, waitlist_id: str, hold_id: str) -> bool:
        url = self._join(self.config.waitlist_service_url, f"/waitlist/{waitlist_id}/offer")
        status_code, payload = self._request_json(
            "PUT",
            url,
            internal_auth=True,
            body={"holdID": hold_id},
        )

        if status_code == 200 and isinstance(payload, dict):
            offered_hold = payload.get("holdID")
            if not isinstance(offered_hold, str):
                return False
            return offered_hold == hold_id

        if status_code == 409:
            latest = self._get_waitlist_entry(waitlist_id)
            if latest and latest.get("status") == "HOLD_OFFERED" and latest.get("holdID") == hold_id:
                return True
            return False

        if status_code in {404, 400}:
            return False

        if status_code >= 500:
            raise TransientProcessingError("Waitlist service unavailable while offering entry")

        raise PermanentProcessingError(
            f"Waitlist offer failed status={status_code} payload={payload}"
        )

    def _build_hold_idempotency_key(
        self,
        event_id: str,
        seat_category: str,
        seat_id: str,
        user_id: str,
        waitlist_id: str,
    ) -> str:
        material = "|".join([event_id, seat_category, seat_id, user_id, waitlist_id])
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return f"wpo:{digest}"

    def _create_hold(
        self,
        *,
        event_id: str,
        seat_category: str,
        seat_id: str,
        user_id: str,
        waitlist_id: str,
    ) -> dict[str, Any] | None:
        idempotency_key = self._build_hold_idempotency_key(
            event_id,
            seat_category,
            seat_id,
            user_id,
            waitlist_id,
        )
        url = self._join(self.config.inventory_service_url, "/inventory/hold")
        status_code, payload = self._request_json(
            "POST",
            url,
            body={
                "eventID": event_id,
                "userID": user_id,
                "seatCategory": seat_category,
                "qty": 1,
                "fromWaitlist": True,
                "idempotencyKey": idempotency_key,
            },
        )

        if status_code in {200, 201} and isinstance(payload, dict):
            return payload

        if status_code == 409:
            message = str((payload or {}).get("error") or "")
            if "No seat available" in message:
                return None
            if "idempotencyKey" in message and "different user or event" in message:
                raise PermanentProcessingError(message)
            return None

        if status_code == 404:
            return None

        if status_code >= 500:
            raise TransientProcessingError("Inventory service unavailable while creating hold")

        raise PermanentProcessingError(
            f"Inventory hold creation failed status={status_code} payload={payload}"
        )

    def _release_hold_cleanup(self, hold_id: str) -> None:
        url = self._join(self.config.inventory_service_url, f"/inventory/hold/{hold_id}/release")
        try:
            status_code, payload = self._request_json(
                "PUT",
                url,
                body={"reason": "SYSTEM_CLEANUP"},
            )
            if status_code not in {200, 404, 409}:
                logger.warning("Cleanup release returned status=%s payload=%s", status_code, payload)
        except TransientProcessingError as error:
            logger.warning("Cleanup hold release failed transiently: %s", error)
        except Exception as error:  # pragma: no cover - defensive
            logger.warning("Cleanup hold release failed: %s", error)

    def _set_seat_available(self, seat_id: str) -> None:
        url = self._join(self.config.inventory_service_url, f"/inventory/seat/{seat_id}/status")
        status_code, payload = self._request_json(
            "PUT",
            url,
            body={"status": "AVAILABLE"},
        )

        if status_code == 200:
            return

        if status_code in {404, 409}:
            logger.info(
                "Seat status update treated as terminal status=%s payload=%s",
                status_code,
                payload,
            )
            return

        if status_code >= 500:
            raise TransientProcessingError("Inventory service unavailable while setting seat AVAILABLE")

        raise PermanentProcessingError(
            f"Seat status update failed status={status_code} payload={payload}"
        )

    def _get_user_email(self, user_id: str) -> str:
        url = self._join(self.config.user_service_url, f"/user/{user_id}")
        status_code, payload = self._request_json("GET", url, internal_auth=True)

        if status_code == 200 and isinstance(payload, dict):
            email = payload.get("email")
            if isinstance(email, str) and "@" in email:
                return email
            raise PermanentProcessingError("User payload missing valid email")

        if status_code == 404:
            raise PermanentProcessingError("User not found for waitlist promotion")

        if status_code >= 500:
            raise TransientProcessingError("User service unavailable while resolving email")

        raise PermanentProcessingError(
            f"User lookup failed status={status_code} payload={payload}"
        )

    def _publish_notification(self, payload: dict[str, Any]) -> None:
        try:
            self._publisher(
                routing_key="notification.send",
                payload=payload,
                exchange=self.config.topic_exchange,
            )
        except Exception as error:
            raise TransientProcessingError(f"Failed to publish notification event: {error}") from error


def install_signal_handlers(worker: WaitlistPromotionWorker) -> None:
    def _handle_signal(_signal_number: int, _frame: Any) -> None:
        worker.request_shutdown()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


def main() -> None:
    try:
        config = WorkerConfig.from_env()
    except ValueError as error:
        logger.error("Invalid worker configuration: %s", error)
        raise SystemExit(1) from error

    worker = WaitlistPromotionWorker(config)
    install_signal_handlers(worker)

    try:
        worker.run_forever()
    finally:
        worker.close()


if __name__ == "__main__":
    main()
