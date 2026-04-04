import json
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pika
import requests

from shared.mq import get_connection, publish_json, rabbitmq_configured

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


class PermanentProcessingError(Exception):
    pass


class TransientProcessingError(Exception):
    pass


class DownstreamCallError(Exception):
    def __init__(self, service: str, status_code: int, message: str, transient: bool):
        super().__init__(message)
        self.service = service
        self.status_code = status_code
        self.message = message
        self.transient = transient


def _parse_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer for %s=%s. Using default=%s", name, value, default)
        return default


def _parse_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return float(value)
    except ValueError:
        logger.warning("Invalid float for %s=%s. Using default=%s", name, value, default)
        return default


@dataclass(frozen=True)
class WorkerConfig:
    service_name: str
    topic_exchange: str
    topic_routing_key: str
    topic_queue: str
    retry_queue: str
    fanout_exchange: str
    retry_header_name: str
    retry_delay_ms: int
    max_retry_attempts: int
    reconnect_delay_seconds: int
    event_service_url: str
    inventory_service_url: str
    pricing_service_url: str
    waitlist_service_url: str
    waitlist_auth_header: str
    internal_service_token: str
    http_timeout_seconds: float

    @staticmethod
    def from_env() -> "WorkerConfig":
        service_name = os.getenv("SERVICE_NAME", "pricing-orchestrator")
        return WorkerConfig(
            service_name=service_name,
            topic_exchange=os.getenv("RABBITMQ_EXCHANGE", "ticketblitz"),
            topic_routing_key=os.getenv("PRICING_SOLD_OUT_ROUTING_KEY", "category.sold_out"),
            topic_queue=os.getenv(
                "PRICING_ORCHESTRATOR_QUEUE",
                f"{service_name}.category.sold_out",
            ),
            retry_queue=os.getenv(
                "PRICING_ORCHESTRATOR_RETRY_QUEUE",
                f"{service_name}.category.sold_out.retry",
            ),
            fanout_exchange=os.getenv("RABBITMQ_PRICE_EXCHANGE", "ticketblitz.price"),
            retry_header_name=os.getenv("PRICING_ORCHESTRATOR_RETRY_HEADER", "x-pricing-orchestrator-retry"),
            retry_delay_ms=max(100, _parse_int_env("PRICING_ORCHESTRATOR_RETRY_DELAY_MS", 5000)),
            max_retry_attempts=max(0, _parse_int_env("PRICING_ORCHESTRATOR_MAX_RETRIES", 3)),
            reconnect_delay_seconds=max(1, _parse_int_env("RABBITMQ_RECONNECT_DELAY", 5)),
            event_service_url=os.getenv("EVENT_SERVICE_URL", "http://event-service:5000"),
            inventory_service_url=os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:5000"),
            pricing_service_url=os.getenv("PRICING_SERVICE_URL", "http://pricing-service:5000"),
            waitlist_service_url=os.getenv("WAITLIST_SERVICE_URL", "http://waitlist-service:5000"),
            waitlist_auth_header=os.getenv("WAITLIST_SERVICE_AUTH_HEADER", "X-Internal-Token"),
            internal_service_token=os.getenv("INTERNAL_SERVICE_TOKEN", ""),
            http_timeout_seconds=max(1.0, _parse_float_env("HTTP_TIMEOUT_SECONDS", 12.0)),
        )


class PricingOrchestratorWorker:
    def __init__(self, config: WorkerConfig):
        self.config = config
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        self._shutdown_requested = False

    def request_shutdown(self) -> None:
        self._shutdown_requested = True
        logger.info("Shutdown requested for %s", self.config.service_name)

        if self._connection and self._connection.is_open:
            self._connection.add_callback_threadsafe(self._stop_consuming)

    def _stop_consuming(self) -> None:
        if self._channel and self._channel.is_open:
            try:
                self._channel.stop_consuming()
            except Exception as error:
                logger.warning("Failed to stop consuming cleanly: %s", error)

    def run_forever(self) -> None:
        if not rabbitmq_configured():
            raise RuntimeError("RABBITMQ_URL must be set before starting pricing orchestrator")

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
                time.sleep(self.config.reconnect_delay_seconds)

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
        self._channel.exchange_declare(
            exchange=self.config.fanout_exchange,
            exchange_type="fanout",
            durable=True,
        )

        self._channel.queue_declare(queue=self.config.topic_queue, durable=True)
        self._channel.queue_declare(
            queue=self.config.retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": self.config.retry_delay_ms,
                "x-dead-letter-exchange": self.config.topic_exchange,
                "x-dead-letter-routing-key": self.config.topic_routing_key,
            },
        )

        self._channel.queue_bind(
            exchange=self.config.topic_exchange,
            queue=self.config.topic_queue,
            routing_key=self.config.topic_routing_key,
        )

        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(
            queue=self.config.topic_queue,
            on_message_callback=self._handle_delivery,
            auto_ack=False,
        )

        logger.info(
            "Listening on queue=%s routing_key=%s",
            self.config.topic_queue,
            self.config.topic_routing_key,
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

    def _extract_retry_count(self, properties: pika.BasicProperties) -> int:
        if not properties or not properties.headers:
            return 0

        value = properties.headers.get(self.config.retry_header_name, 0)
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
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
                routing_key=self.config.retry_queue,
                body=body,
                properties=next_properties,
                mandatory=False,
            )
            return True
        except Exception as error:
            logger.warning("Unable to enqueue retry message: %s", error)
            return False

    def _handle_delivery(self, channel, method, properties, body: bytes) -> None:
        delivery_tag = method.delivery_tag
        retry_count = self._extract_retry_count(properties)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Dropping malformed JSON message: %s", body)
            channel.basic_ack(delivery_tag=delivery_tag)
            return

        if not isinstance(payload, dict):
            logger.error("Dropping unsupported payload shape: %s", payload)
            channel.basic_ack(delivery_tag=delivery_tag)
            return

        correlation_id = payload.get("correlationID") or getattr(properties, "correlation_id", None)

        try:
            self.process_payload(payload, correlation_id)
            channel.basic_ack(delivery_tag=delivery_tag)
            logger.info("Processed sold-out event correlationID=%s", correlation_id)
        except PermanentProcessingError as error:
            logger.warning(
                "Permanent failure correlationID=%s: %s",
                correlation_id,
                error,
            )
            channel.basic_ack(delivery_tag=delivery_tag)
        except TransientProcessingError as error:
            if retry_count < self.config.max_retry_attempts:
                next_retry_count = retry_count + 1
                enqueued = self._enqueue_retry(properties, body, next_retry_count)
                if enqueued:
                    logger.warning(
                        "Transient failure correlationID=%s retry=%s/%s: %s",
                        correlation_id,
                        next_retry_count,
                        self.config.max_retry_attempts,
                        error,
                    )
                    channel.basic_ack(delivery_tag=delivery_tag)
                else:
                    logger.error("Retry scheduling failed correlationID=%s: %s", correlation_id, error)
                    # Preserve at-least-once semantics when we cannot enqueue retry.
                    channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
                return

            logger.error("Retry limit reached correlationID=%s: %s", correlation_id, error)
            channel.basic_ack(delivery_tag=delivery_tag)
        except Exception as error:
            logger.exception("Unexpected error processing message correlationID=%s: %s", correlation_id, error)
            channel.basic_ack(delivery_tag=delivery_tag)

    def validate_payload(self, payload: Dict[str, Any]) -> Dict[str, str]:
        required_fields = ["eventID", "category", "flashSaleID", "soldAt"]
        missing = [field for field in required_fields if not payload.get(field)]
        if missing:
            raise PermanentProcessingError(f"Missing required field(s): {', '.join(missing)}")

        event_id = str(payload["eventID"])
        sold_out_category = str(payload["category"]).strip().upper()
        flash_sale_id = str(payload["flashSaleID"])
        sold_at = str(payload["soldAt"])

        return {
            "eventID": event_id,
            "soldOutCategory": sold_out_category,
            "flashSaleID": flash_sale_id,
            "soldAt": sold_at,
        }

    def _request_json(
        self,
        method: str,
        service_name: str,
        base_url: str,
        path: str,
        *,
        expected_statuses: List[int],
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{base_url.rstrip('/')}{path}"
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                headers=headers,
                json=json_body,
                timeout=self.config.http_timeout_seconds,
            )
        except requests.Timeout as error:
            raise DownstreamCallError(service_name, 504, f"{service_name} request timed out", True) from error
        except requests.RequestException as error:
            raise DownstreamCallError(service_name, 503, f"{service_name} unavailable", True) from error

        try:
            body = response.json() if response.text else {}
        except ValueError:
            body = {}

        if response.status_code not in expected_statuses:
            message = body.get("error") if isinstance(body, dict) else None
            transient = response.status_code >= 500
            raise DownstreamCallError(
                service_name,
                response.status_code,
                message or f"{service_name} request failed",
                transient,
            )

        if isinstance(body, dict):
            return body

        return {"data": body}

    def _history_has_matching_escalation(
        self,
        event_id: str,
        flash_sale_id: str,
        sold_out_category: str,
        sold_at: str,
    ) -> bool:
        history = self._request_json(
            "GET",
            "pricing-service",
            self.config.pricing_service_url,
            f"/pricing/{event_id}/history",
            expected_statuses=[200],
            params={"flashSaleID": flash_sale_id, "limit": "100"},
        )

        rows = history.get("priceChanges", [])
        if not isinstance(rows, list):
            return False

        sold_out_normalized = sold_out_category.strip().upper()
        for row in rows:
            if not isinstance(row, dict):
                continue

            if str(row.get("reason", "")).upper() != "ESCALATION":
                continue

            context = row.get("context") if isinstance(row.get("context"), dict) else {}
            context_sold_out = str(context.get("soldOutCategory", "")).upper()
            context_sold_at = str(context.get("soldAt", ""))

            if context_sold_out == sold_out_normalized and context_sold_at == sold_at:
                return True

        return False

    def _load_waitlist_emails(self, event_id: str) -> List[str]:
        if not self.config.internal_service_token:
            logger.warning("INTERNAL_SERVICE_TOKEN is not set. waitlist emails will be skipped")
            return []

        headers = {self.config.waitlist_auth_header: self.config.internal_service_token}
        body = self._request_json(
            "GET",
            "waitlist-service",
            self.config.waitlist_service_url,
            "/waitlist",
            expected_statuses=[200],
            headers=headers,
            params={
                "eventID": event_id,
                "status": "WAITING",
                "includeEmail": "true",
                "limit": "200",
            },
        )

        rows = body.get("entries", [])
        if not isinstance(rows, list):
            return []

        dedupe: Dict[str, bool] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            email = row.get("email")
            if isinstance(email, str) and "@" in email:
                dedupe[email] = True

        return list(dedupe.keys())

    def _is_category_available(self, event_id: str, category_code: str) -> bool:
        inventory = self._request_json(
            "GET",
            "inventory-service",
            self.config.inventory_service_url,
            f"/inventory/{event_id}/{category_code}",
            expected_statuses=[200],
        )
        available = inventory.get("available")
        if isinstance(available, int):
            return available > 0
        return str(inventory.get("status", "")).upper() == "AVAILABLE"

    def _publish_escalation(self, payload: Dict[str, Any]) -> None:
        try:
            publish_json(
                routing_key="",
                payload=payload,
                exchange=self.config.fanout_exchange,
                exchange_type="fanout",
            )
        except Exception as error:
            raise TransientProcessingError(f"Failed to publish fanout escalation event: {error}") from error

    def process_payload(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        validated = self.validate_payload(payload)

        event_id = validated["eventID"]
        sold_out_category = validated["soldOutCategory"]
        sold_at = validated["soldAt"]
        flash_sale_id_from_event = validated["flashSaleID"]

        effective_correlation_id = correlation_id or str(uuid.uuid4())

        try:
            active_sale = self._request_json(
                "GET",
                "pricing-service",
                self.config.pricing_service_url,
                f"/pricing/{event_id}/flash-sale/active",
                expected_statuses=[200],
            )
        except DownstreamCallError as error:
            if error.status_code == 404:
                raise PermanentProcessingError("No active flash sale for sold-out event") from error
            if error.transient:
                raise TransientProcessingError(error.message) from error
            raise PermanentProcessingError(error.message) from error

        active_flash_sale_id = str(active_sale.get("flashSaleID"))
        if active_flash_sale_id != flash_sale_id_from_event:
            raise PermanentProcessingError(
                "Sold-out event flashSaleID does not match active flash sale"
            )

        try:
            already_processed = self._history_has_matching_escalation(
                event_id,
                active_flash_sale_id,
                sold_out_category,
                sold_at,
            )
        except DownstreamCallError as error:
            if error.transient:
                raise TransientProcessingError(error.message) from error
            raise PermanentProcessingError(error.message) from error

        if already_processed:
            logger.info(
                "Skipping duplicate sold-out escalation event eventID=%s flashSaleID=%s soldOutCategory=%s",
                event_id,
                active_flash_sale_id,
                sold_out_category,
            )
            return

        try:
            categories_body = self._request_json(
                "GET",
                "event-service",
                self.config.event_service_url,
                f"/event/{event_id}/categories",
                expected_statuses=[200],
            )
        except DownstreamCallError as error:
            if error.transient:
                raise TransientProcessingError(error.message) from error
            raise PermanentProcessingError(error.message) from error

        categories = categories_body.get("categories", [])
        if not isinstance(categories, list):
            raise PermanentProcessingError("Event categories response has invalid shape")

        remaining_categories = []
        for row in categories:
            if not isinstance(row, dict):
                continue
            code = str(row.get("category_code", "")).upper()
            if code == sold_out_category:
                continue
            if not row.get("is_active", True):
                continue

            try:
                is_available = self._is_category_available(event_id, code)
            except DownstreamCallError as error:
                if error.transient:
                    raise TransientProcessingError(error.message) from error
                raise PermanentProcessingError(error.message) from error
            if not is_available:
                continue

            remaining_categories.append(
                {
                    "categoryID": row.get("category_id"),
                    "category": row.get("category_code"),
                    "currentPrice": row.get("current_price"),
                }
            )

        if not remaining_categories:
            logger.info(
                "No available categories remain for escalation eventID=%s flashSaleID=%s soldOutCategory=%s",
                event_id,
                active_flash_sale_id,
                sold_out_category,
            )
            return

        try:
            escalation_result = self._request_json(
                "POST",
                "pricing-service",
                self.config.pricing_service_url,
                "/pricing/escalate",
                expected_statuses=[200],
                json_body={
                    "eventID": event_id,
                    "flashSaleID": active_flash_sale_id,
                    "soldOutCategory": sold_out_category,
                    "remainingCategories": remaining_categories,
                    "soldAt": sold_at,
                },
            )
        except DownstreamCallError as error:
            if error.transient:
                raise TransientProcessingError(error.message) from error
            raise PermanentProcessingError(error.message) from error

        updated_prices = escalation_result.get("updatedPrices", [])
        if not isinstance(updated_prices, list):
            raise PermanentProcessingError("Escalation response has invalid updatedPrices shape")

        event_updates = [
            {
                "category_id": row.get("categoryID"),
                "new_price": row.get("newPrice"),
            }
            for row in updated_prices
            if isinstance(row, dict) and row.get("categoryID") and row.get("newPrice") is not None
        ]

        if event_updates:
            try:
                self._request_json(
                    "PUT",
                    "event-service",
                    self.config.event_service_url,
                    f"/event/{event_id}/categories/prices",
                    expected_statuses=[200],
                    json_body={
                        "reason": "ESCALATION",
                        "flashSaleID": active_flash_sale_id,
                        "changed_by": self.config.service_name,
                        "context": {
                            "soldOutCategory": sold_out_category,
                            "soldAt": sold_at,
                            "correlationID": effective_correlation_id,
                            "source": self.config.service_name,
                        },
                        "updates": event_updates,
                    },
                )
            except DownstreamCallError as error:
                if error.transient:
                    raise TransientProcessingError(error.message) from error
                raise PermanentProcessingError(error.message) from error

        try:
            waitlist_emails = self._load_waitlist_emails(event_id)
        except DownstreamCallError as error:
            if error.transient:
                raise TransientProcessingError(error.message) from error
            raise PermanentProcessingError(error.message) from error

        self._publish_escalation(
            {
                "type": "PRICE_ESCALATED",
                "eventID": event_id,
                "flashSaleID": active_flash_sale_id,
                "soldOutCategory": sold_out_category,
                "updatedPrices": updated_prices,
                "waitlistEmails": waitlist_emails,
                "correlationID": effective_correlation_id,
            }
        )


def install_signal_handlers(worker: PricingOrchestratorWorker) -> None:
    def _handle_signal(_signal_number, _frame) -> None:
        worker.request_shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def main() -> None:
    config = WorkerConfig.from_env()
    worker = PricingOrchestratorWorker(config)
    install_signal_handlers(worker)
    worker.run_forever()


if __name__ == "__main__":
    main()
