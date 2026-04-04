import json
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pika
import requests

from shared.mq import get_connection, publish_json, rabbitmq_configured

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


class InvalidMessageError(Exception):
    """Message payload is invalid and should not be retried."""


@dataclass(frozen=True)
class ProcessingError(Exception):
    stage: str
    error_code: str
    message: str
    retryable: bool

    def __str__(self) -> str:
        return f"{self.stage}:{self.error_code}:{self.message}"


def parse_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        logger.warning(
            "Invalid integer for %s=%s. Using default=%s", name, value, default)
        return default


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


@dataclass(frozen=True)
class WorkerConfig:
    service_name: str
    exchange: str
    input_routing_key: str
    queue_name: str
    retry_queue_name: str
    notification_routing_key: str
    retry_header_name: str
    retry_delay_ms: int
    max_retry_attempts: int
    reconnect_delay_seconds: int
    inventory_service_url: str
    waitlist_service_url: str
    event_service_url: str
    eticket_generate_url: str
    waitlist_auth_header: str
    internal_service_token: str
    http_timeout_seconds: int
    eticket_timeout_seconds: int
    incident_type: str
    incident_email: str

    @staticmethod
    def from_env() -> "WorkerConfig":
        service_name = os.getenv(
            "SERVICE_NAME", "booking-fulfillment-orchestrator")
        queue_name = os.getenv(
            "BFO_QUEUE_NAME", f"{service_name}.booking.confirmed")
        return WorkerConfig(
            service_name=service_name,
            exchange=os.getenv("RABBITMQ_EXCHANGE", "ticketblitz"),
            input_routing_key=os.getenv(
                "BFO_INPUT_ROUTING_KEY", "booking.confirmed"),
            queue_name=queue_name,
            retry_queue_name=os.getenv(
                "BFO_RETRY_QUEUE_NAME", f"{queue_name}.retry"),
            notification_routing_key=os.getenv(
                "BFO_NOTIFICATION_ROUTING_KEY", "notification.send"),
            retry_header_name=os.getenv("BFO_RETRY_HEADER", "x-bfo-retry"),
            retry_delay_ms=max(100, parse_int_env("BFO_RETRY_DELAY_MS", 5000)),
            max_retry_attempts=max(0, parse_int_env("BFO_MAX_RETRIES", 3)),
            reconnect_delay_seconds=max(
                1, parse_int_env("RABBITMQ_RECONNECT_DELAY", 5)),
            inventory_service_url=os.getenv(
                "INVENTORY_SERVICE_URL", "http://inventory-service:5000"),
            waitlist_service_url=os.getenv(
                "WAITLIST_SERVICE_URL", "http://waitlist-service:5000"),
            event_service_url=os.getenv(
                "EVENT_SERVICE_URL", "http://event-service:5000"),
            eticket_generate_url=os.getenv(
                "ETICKET_GENERATE_URL", "http://kong:8000/eticket/generate"),
            waitlist_auth_header=os.getenv(
                "WAITLIST_SERVICE_AUTH_HEADER", "X-Internal-Token"),
            internal_service_token=os.getenv(
                "INTERNAL_SERVICE_TOKEN", "").strip(),
            http_timeout_seconds=max(1, parse_int_env(
                "BFO_HTTP_TIMEOUT_SECONDS", 10)),
            eticket_timeout_seconds=max(1, parse_int_env(
                "BFO_ETICKET_TIMEOUT_SECONDS", 20)),
            incident_type=os.getenv(
                "BFO_INCIDENT_TYPE", "BOOKING_FULFILLMENT_INCIDENT"),
            incident_email=os.getenv("BOOKING_INCIDENT_EMAIL", "").strip(),
        )


class BookingFulfillmentWorker:
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
            except Exception as error:  # pragma: no cover
                logger.warning("Unable to stop consuming cleanly: %s", error)

    def run_forever(self) -> None:
        if not rabbitmq_configured():
            raise RuntimeError(
                "RABBITMQ_URL must be set before starting booking fulfillment worker")

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
            exchange=self.config.exchange,
            exchange_type="topic",
            durable=True,
        )

        self._channel.queue_declare(queue=self.config.queue_name, durable=True)
        self._channel.queue_declare(
            queue=self.config.retry_queue_name,
            durable=True,
            arguments={
                "x-message-ttl": self.config.retry_delay_ms,
                "x-dead-letter-exchange": self.config.exchange,
                "x-dead-letter-routing-key": self.config.input_routing_key,
            },
        )

        self._channel.queue_bind(
            exchange=self.config.exchange,
            queue=self.config.queue_name,
            routing_key=self.config.input_routing_key,
        )

        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(
            queue=self.config.queue_name,
            on_message_callback=self._handle_delivery,
            auto_ack=False,
        )

        logger.info(
            "Listening on queue=%s routing=%s (retry delay=%sms)",
            self.config.queue_name,
            self.config.input_routing_key,
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
                routing_key=self.config.retry_queue_name,
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
            logger.error("Dropping malformed JSON message: %s", body)
            channel.basic_ack(delivery_tag=delivery_tag)
            return

        if not isinstance(payload, dict):
            logger.error("Dropping unsupported payload shape: %s", payload)
            channel.basic_ack(delivery_tag=delivery_tag)
            return

        correlation_id = (
            payload.get("correlationID")
            or payload.get("correlationId")
            or getattr(properties, "correlation_id", None)
            or str(uuid.uuid4())
        )

        try:
            self.process_payload(payload, correlation_id)
            logger.info(
                "Processed booking.confirmed holdID=%s correlationID=%s",
                payload.get("holdID"),
                correlation_id,
            )
            channel.basic_ack(delivery_tag=delivery_tag)
        except InvalidMessageError as error:
            logger.error(
                "Permanent payload error holdID=%s correlationID=%s: %s",
                payload.get("holdID"),
                correlation_id,
                error,
            )
            channel.basic_ack(delivery_tag=delivery_tag)
        except ProcessingError as error:
            if error.retryable and retry_count < self.config.max_retry_attempts:
                next_retry_count = retry_count + 1
                republished = self._enqueue_retry(
                    properties=properties,
                    body=body,
                    retry_count=next_retry_count,
                )
                if republished:
                    logger.warning(
                        "Transient failure stage=%s holdID=%s correlationID=%s retry=%s/%s: %s",
                        error.stage,
                        payload.get("holdID"),
                        correlation_id,
                        next_retry_count,
                        self.config.max_retry_attempts,
                        error,
                    )
                    channel.basic_ack(delivery_tag=delivery_tag)
                    return

            logger.error(
                "Terminal fulfillment failure stage=%s holdID=%s correlationID=%s: %s",
                error.stage,
                payload.get("holdID"),
                correlation_id,
                error,
            )
            self._publish_incident(payload, correlation_id, error)
            channel.basic_ack(delivery_tag=delivery_tag)
        except Exception as error:
            logger.exception(
                "Unexpected failure holdID=%s correlationID=%s: %s",
                payload.get("holdID"),
                correlation_id,
                error,
            )
            self._publish_incident(
                payload,
                correlation_id,
                ProcessingError(
                    stage="worker",
                    error_code="UNEXPECTED_FAILURE",
                    message=str(error),
                    retryable=False,
                ),
            )
            channel.basic_ack(delivery_tag=delivery_tag)

    def process_payload(self, payload: Dict[str, Any], correlation_id: str) -> None:
        message = self._normalize_payload(payload, correlation_id)

        hold = self._confirm_hold(message["holdID"], message["correlationID"])
        ticket = self._generate_eticket(message, hold)

        waitlist_id = message.get(
            "waitlistID") or self._lookup_waitlist_id(message["holdID"])
        if waitlist_id:
            self._confirm_waitlist(waitlist_id, message["holdID"])

        event_name = self._resolve_event_name(message["eventID"])
        self._publish_customer_notification(
            {
                "type": "BOOKING_CONFIRMED",
                "email": message["email"],
                "eventName": event_name,
                "seatNumber": hold["seatNumber"],
                "ticketID": ticket["ticketID"],
                "holdID": message["holdID"],
                "correlationID": message["correlationID"],
            }
        )

    def _normalize_payload(self, payload: Dict[str, Any], correlation_id: str) -> Dict[str, Any]:
        required_fields = ["holdID", "userID", "eventID", "email"]
        for field in required_fields:
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip():
                raise InvalidMessageError(f"Missing required field '{field}'")

        message = {
            "holdID": payload["holdID"].strip(),
            "userID": payload["userID"].strip(),
            "eventID": payload["eventID"].strip(),
            "email": payload["email"].strip(),
            "correlationID": (payload.get("correlationID") or correlation_id).strip(),
            "waitlistID": payload.get("waitlistID") or None,
            "paymentIntentID": payload.get("paymentIntentID") or "",
            "transactionID": payload.get("transactionID") or "",
        }

        if "@" not in message["email"]:
            raise InvalidMessageError(
                "Field 'email' must be a valid email address")

        return message

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        timeout: int,
        stage: str,
        retryable_on_5xx: bool,
        **kwargs,
    ) -> tuple[int, Dict[str, Any], str]:
        try:
            response = requests.request(
                method=method, url=url, timeout=timeout, **kwargs)
        except requests.RequestException as error:
            raise ProcessingError(
                stage=stage,
                error_code="HTTP_REQUEST_FAILED",
                message=str(error),
                retryable=True,
            ) from error

        body_text = response.text or ""
        body_json: Dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body_json = parsed
        except ValueError:
            body_json = {}

        status_code = response.status_code
        if status_code >= 500:
            raise ProcessingError(
                stage=stage,
                error_code=f"HTTP_{status_code}",
                message=body_text or "Upstream server error",
                retryable=retryable_on_5xx,
            )

        return status_code, body_json, body_text

    def _confirm_hold(self, hold_id: str, correlation_id: str) -> Dict[str, Any]:
        url = join_url(self.config.inventory_service_url,
                       f"/inventory/hold/{hold_id}/confirm")
        status, body, raw = self._request_json(
            method="PUT",
            url=url,
            timeout=self.config.http_timeout_seconds,
            stage="inventory_confirm",
            retryable_on_5xx=True,
            json={"correlationID": correlation_id},
        )

        if status == 200:
            seat_id = body.get("seatID")
            seat_number = body.get("seatNumber")
            if not seat_id or not seat_number:
                raise ProcessingError(
                    stage="inventory_confirm",
                    error_code="INVALID_RESPONSE",
                    message="Inventory confirmation response is missing seat details",
                    retryable=False,
                )
            return body

        if status in {404, 409}:
            raise ProcessingError(
                stage="inventory_confirm",
                error_code=f"HTTP_{status}",
                message=raw or "Inventory confirmation rejected",
                retryable=False,
            )

        if status >= 400:
            raise ProcessingError(
                stage="inventory_confirm",
                error_code=f"HTTP_{status}",
                message=raw or "Inventory confirmation failed",
                retryable=False,
            )

        raise ProcessingError(
            stage="inventory_confirm",
            error_code="UNEXPECTED_STATUS",
            message=f"Unexpected status code: {status}",
            retryable=False,
        )

    def _generate_eticket(self, message: Dict[str, Any], hold: Dict[str, Any]) -> Dict[str, Any]:
        request_body = {
            "holdID": message["holdID"],
            "userID": message["userID"],
            "eventID": message["eventID"],
            "seatID": hold["seatID"],
            "seatNumber": hold["seatNumber"],
            "correlationID": message["correlationID"],
            "transactionID": message.get("transactionID") or None,
            "metadata": json.dumps(
                {
                    "paymentIntentID": message.get("paymentIntentID") or None,
                }
            ),
        }

        status, body, raw = self._request_json(
            method="POST",
            url=self.config.eticket_generate_url,
            timeout=self.config.eticket_timeout_seconds,
            stage="eticket_generate",
            retryable_on_5xx=True,
            json=request_body,
        )

        if status in {200, 201} and body.get("ticketID"):
            return body

        if status >= 400:
            retryable = status >= 500
            if status in {400, 404, 409}:
                retryable = False

            raise ProcessingError(
                stage="eticket_generate",
                error_code=f"HTTP_{status}",
                message=raw or "E-ticket generation failed",
                retryable=retryable,
            )

        raise ProcessingError(
            stage="eticket_generate",
            error_code="INVALID_RESPONSE",
            message="E-ticket response missing ticketID",
            retryable=False,
        )

    def _waitlist_headers(self) -> Dict[str, str]:
        if self.config.internal_service_token:
            return {self.config.waitlist_auth_header: self.config.internal_service_token}
        return {}

    def _lookup_waitlist_id(self, hold_id: str) -> Optional[str]:
        url = join_url(self.config.waitlist_service_url,
                       f"/waitlist/by-hold/{hold_id}")
        try:
            response = requests.get(
                url,
                headers=self._waitlist_headers(),
                timeout=self.config.http_timeout_seconds,
            )
        except requests.RequestException as error:
            logger.warning(
                "waitlist lookup failed holdID=%s: %s", hold_id, error)
            return None

        if response.status_code == 200:
            try:
                body = response.json()
            except ValueError:
                return None
            waitlist_id = body.get("waitlistID")
            return str(waitlist_id) if waitlist_id else None

        if response.status_code not in {401, 404}:
            logger.warning(
                "waitlist lookup returned status=%s holdID=%s body=%s",
                response.status_code,
                hold_id,
                response.text,
            )

        return None

    def _confirm_waitlist(self, waitlist_id: str, hold_id: str) -> None:
        url = join_url(self.config.waitlist_service_url,
                       f"/waitlist/{waitlist_id}/confirm")
        try:
            response = requests.put(
                url,
                headers=self._waitlist_headers(),
                json={"status": "CONFIRMED", "holdID": hold_id},
                timeout=self.config.http_timeout_seconds,
            )
        except requests.RequestException as error:
            logger.warning(
                "waitlist confirm request failed waitlistID=%s holdID=%s: %s",
                waitlist_id,
                hold_id,
                error,
            )
            return

        if response.status_code in {200, 404, 409}:
            return

        logger.warning(
            "waitlist confirm returned status=%s waitlistID=%s holdID=%s body=%s",
            response.status_code,
            waitlist_id,
            hold_id,
            response.text,
        )

    def _resolve_event_name(self, event_id: str) -> str:
        url = join_url(self.config.event_service_url, f"/event/{event_id}")
        try:
            response = requests.get(
                url, timeout=self.config.http_timeout_seconds)
            if response.status_code == 200:
                body = response.json()
                name = body.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        except Exception:
            pass

        return "TicketBlitz Event"

    def _publish_customer_notification(self, payload: Dict[str, Any]) -> None:
        try:
            publish_json(
                routing_key=self.config.notification_routing_key,
                payload=payload,
                exchange=self.config.exchange,
            )
        except Exception as error:
            raise ProcessingError(
                stage="notification_publish",
                error_code="PUBLISH_FAILED",
                message=str(error),
                retryable=True,
            ) from error

    def _publish_incident(
        self,
        payload: Dict[str, Any],
        correlation_id: str,
        error: ProcessingError,
    ) -> None:
        recipient = self.config.incident_email
        if not recipient:
            logger.error(
                "BOOKING_INCIDENT_EMAIL is not configured, skipping incident notification holdID=%s correlationID=%s error=%s",
                payload.get("holdID"),
                correlation_id,
                error,
            )
            return

        incident_payload = {
            "type": self.config.incident_type,
            "email": recipient,
            "holdID": payload.get("holdID", ""),
            "correlationID": correlation_id,
            "errorCode": error.error_code,
            "errorMessage": error.message,
            "stage": error.stage,
        }

        try:
            publish_json(
                routing_key=self.config.notification_routing_key,
                payload=incident_payload,
                exchange=self.config.exchange,
            )
        except Exception as publish_error:
            logger.error(
                "Failed to publish incident notification holdID=%s correlationID=%s: %s",
                payload.get("holdID"),
                correlation_id,
                publish_error,
            )


def install_signal_handlers(worker: BookingFulfillmentWorker) -> None:
    def _handle_signal(_signal_number, _frame) -> None:
        worker.request_shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def main() -> None:
    config = WorkerConfig.from_env()
    worker = BookingFulfillmentWorker(config)
    install_signal_handlers(worker)
    worker.run_forever()


if __name__ == "__main__":
    main()
