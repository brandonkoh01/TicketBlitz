import json
import logging
import os
import signal
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pika
from python_http_client.exceptions import HTTPError
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from shared.mq import get_connection, rabbitmq_configured

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

TOPIC_NOTIFICATION_TYPES = {
    "BOOKING_CONFIRMED",
    "WAITLIST_JOINED",
    "SEAT_AVAILABLE",
    "HOLD_EXPIRED",
    "CANCELLATION_CONFIRMED",
    "CANCELLATION_DENIED",
    "REFUND_SUCCESSFUL",
    "REFUND_ERROR",
    "TICKET_AVAILABLE_PUBLIC",
    "TICKET_CONFIRMATION",
    "BOOKING_FULFILLMENT_INCIDENT",
}

FANOUT_NOTIFICATION_TYPES = {
    "FLASH_SALE_LAUNCHED",
    "PRICE_ESCALATED",
    "FLASH_SALE_ENDED",
}

ALL_NOTIFICATION_TYPES = TOPIC_NOTIFICATION_TYPES | FANOUT_NOTIFICATION_TYPES

REQUIRED_FIELDS_BY_TYPE = {
    "BOOKING_CONFIRMED": ["email", "eventName", "seatNumber", "ticketID"],
    "WAITLIST_JOINED": ["email", "eventName", "position", "waitlistID"],
    "SEAT_AVAILABLE": ["email", "holdID", "holdExpiry", "paymentURL"],
    "HOLD_EXPIRED": ["email", "holdID"],
    "BOOKING_FULFILLMENT_INCIDENT": [
        "email",
        "holdID",
        "correlationID",
        "errorCode",
        "errorMessage",
        "stage",
    ],
    "CANCELLATION_CONFIRMED": ["email", "bookingID", "eventName"],
    "CANCELLATION_DENIED": ["email", "bookingID", "reason"],
    "REFUND_SUCCESSFUL": ["email", "bookingID", "refundAmount", "eventName"],
    "REFUND_ERROR": ["email", "bookingID", "errorDetail", "nextSteps"],
    "TICKET_AVAILABLE_PUBLIC": ["email", "bookingID", "eventName"],
    "TICKET_CONFIRMATION": ["email", "bookingID", "ticketID", "seatNumber", "eventName"],
    "FLASH_SALE_LAUNCHED": ["eventID", "flashSaleID", "updatedPrices", "waitlistEmails"],
    "PRICE_ESCALATED": [
        "eventID",
        "flashSaleID",
        "soldOutCategory",
        "updatedPrices",
        "waitlistEmails",
    ],
    "FLASH_SALE_ENDED": ["eventID", "flashSaleID", "revertedPrices", "waitlistEmails"],
}

TEMPLATE_ENV_BY_TYPE = {
    "BOOKING_CONFIRMED": "SENDGRID_TEMPLATE_BOOKING_CONFIRMED",
    "WAITLIST_JOINED": "SENDGRID_TEMPLATE_WAITLIST_JOINED",
    "SEAT_AVAILABLE": "SENDGRID_TEMPLATE_SEAT_AVAILABLE",
    "HOLD_EXPIRED": "SENDGRID_TEMPLATE_HOLD_EXPIRED",
    "BOOKING_FULFILLMENT_INCIDENT": "SENDGRID_TEMPLATE_BOOKING_FULFILLMENT_INCIDENT",
    "CANCELLATION_CONFIRMED": "SENDGRID_TEMPLATE_CANCELLATION_CONFIRMED",
    "CANCELLATION_DENIED": "SENDGRID_TEMPLATE_CANCELLATION_DENIED",
    "REFUND_SUCCESSFUL": "SENDGRID_TEMPLATE_REFUND_SUCCESSFUL",
    "REFUND_ERROR": "SENDGRID_TEMPLATE_REFUND_ERROR",
    "TICKET_AVAILABLE_PUBLIC": "SENDGRID_TEMPLATE_TICKET_AVAILABLE_PUBLIC",
    "TICKET_CONFIRMATION": "SENDGRID_TEMPLATE_TICKET_CONFIRMATION",
    "FLASH_SALE_LAUNCHED": "SENDGRID_TEMPLATE_FLASH_SALE_LAUNCHED",
    "PRICE_ESCALATED": "SENDGRID_TEMPLATE_PRICE_ESCALATED",
    "FLASH_SALE_ENDED": "SENDGRID_TEMPLATE_FLASH_SALE_ENDED",
}


class NotificationError(Exception):
    """Base notification processing error."""


class PermanentNotificationError(NotificationError):
    """Non-retryable processing error."""


class TransientNotificationError(NotificationError):
    """Retryable processing error."""


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


def is_production_env() -> bool:
    for name in ("APP_ENV", "ENVIRONMENT", "FLASK_ENV"):
        value = os.getenv(name)
        if value and value.lower() in {"prod", "production"}:
            return True
    return False


@dataclass(frozen=True)
class WorkerConfig:
    service_name: str
    topic_exchange: str
    topic_routing_key: str
    topic_queue: str
    topic_retry_queue: str
    fanout_exchange: str
    fanout_queue: str
    fanout_retry_queue: str
    retry_header_name: str
    retry_delay_ms: int
    max_retry_attempts: int
    reconnect_delay_seconds: int
    sendgrid_api_key: str
    sendgrid_from_email: str
    sendgrid_from_name: str
    is_production: bool

    @staticmethod
    def from_env() -> "WorkerConfig":
        service_name = os.getenv("SERVICE_NAME", "notification-service")
        return WorkerConfig(
            service_name=service_name,
            topic_exchange=os.getenv("RABBITMQ_EXCHANGE", "ticketblitz"),
            topic_routing_key=os.getenv(
                "NOTIFICATION_TOPIC_ROUTING_KEY", "notification.send"),
            topic_queue=os.getenv(
                "NOTIFICATION_TOPIC_QUEUE", f"{service_name}.notification.send"
            ),
            topic_retry_queue=os.getenv(
                "NOTIFICATION_TOPIC_RETRY_QUEUE",
                f"{service_name}.notification.send.retry",
            ),
            fanout_exchange=os.getenv(
                "RABBITMQ_PRICE_EXCHANGE", "ticketblitz.price"),
            fanout_queue=os.getenv(
                "NOTIFICATION_FANOUT_QUEUE", f"{service_name}.price.broadcast"
            ),
            fanout_retry_queue=os.getenv(
                "NOTIFICATION_FANOUT_RETRY_QUEUE",
                f"{service_name}.price.broadcast.retry",
            ),
            retry_header_name=os.getenv(
                "NOTIFICATION_RETRY_HEADER", "x-notification-retry"),
            retry_delay_ms=max(100, parse_int_env(
                "NOTIFICATION_RETRY_DELAY_MS", 5000)),
            max_retry_attempts=max(0, parse_int_env(
                "NOTIFICATION_MAX_RETRIES", 3)),
            reconnect_delay_seconds=max(
                1, parse_int_env("RABBITMQ_RECONNECT_DELAY", 5)),
            sendgrid_api_key=os.getenv("SENDGRID_API_KEY", ""),
            sendgrid_from_email=os.getenv("SENDGRID_FROM_EMAIL", ""),
            sendgrid_from_name=os.getenv("SENDGRID_FROM_NAME", "TicketBlitz"),
            is_production=is_production_env(),
        )


class NotificationWorker:
    def __init__(self, config: WorkerConfig):
        self.config = config
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        self._shutdown_requested = False
        self._sendgrid_client = (
            SendGridAPIClient(self.config.sendgrid_api_key)
            if self.config.sendgrid_api_key
            else None
        )

    def request_shutdown(self) -> None:
        self._shutdown_requested = True
        logger.info("Shutdown requested for %s", self.config.service_name)

        if self._connection and self._connection.is_open:
            self._connection.add_callback_threadsafe(self._stop_consuming)

    def _stop_consuming(self) -> None:
        if self._channel and self._channel.is_open:
            try:
                self._channel.stop_consuming()
            except Exception as error:  # pragma: no cover - defensive shutdown path
                logger.warning("Unable to stop consuming cleanly: %s", error)

    def run_forever(self) -> None:
        if not rabbitmq_configured():
            raise RuntimeError(
                "RABBITMQ_URL must be set before starting notification worker")

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

        self._channel.queue_declare(
            queue=self.config.topic_queue, durable=True)
        self._channel.queue_declare(
            queue=self.config.fanout_queue, durable=True)
        self._channel.queue_declare(
            queue=self.config.topic_retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": self.config.retry_delay_ms,
                "x-dead-letter-exchange": self.config.topic_exchange,
                "x-dead-letter-routing-key": self.config.topic_routing_key,
            },
        )
        self._channel.queue_declare(
            queue=self.config.fanout_retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": self.config.retry_delay_ms,
                "x-dead-letter-exchange": self.config.fanout_exchange,
            },
        )

        self._channel.queue_bind(
            exchange=self.config.topic_exchange,
            queue=self.config.topic_queue,
            routing_key=self.config.topic_routing_key,
        )
        self._channel.queue_bind(
            exchange=self.config.fanout_exchange,
            queue=self.config.fanout_queue,
        )

        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(
            queue=self.config.topic_queue,
            on_message_callback=self._handle_delivery,
            auto_ack=False,
        )
        self._channel.basic_consume(
            queue=self.config.fanout_queue,
            on_message_callback=self._handle_delivery,
            auto_ack=False,
        )

        logger.info(
            "Listening on topic queue=%s and fanout queue=%s (retry delay=%sms)",
            self.config.topic_queue,
            self.config.fanout_queue,
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

        event_type = str(payload.get("type", "UNKNOWN"))
        correlation_id = payload.get("correlationID") or getattr(
            properties, "correlation_id", None)

        try:
            self.process_payload(payload)
            logger.info(
                "Processed type=%s correlationID=%s",
                event_type,
                correlation_id,
            )
            channel.basic_ack(delivery_tag=delivery_tag)
        except PermanentNotificationError as error:
            logger.error(
                "Permanent failure for type=%s correlationID=%s: %s",
                event_type,
                correlation_id,
                error,
            )
            channel.basic_ack(delivery_tag=delivery_tag)
        except TransientNotificationError as error:
            if retry_count < self.config.max_retry_attempts:
                next_retry_count = retry_count + 1
                republished = self._enqueue_retry(
                    method=method,
                    properties=properties,
                    body=body,
                    retry_count=next_retry_count,
                )
                if republished:
                    logger.warning(
                        "Transient failure for type=%s correlationID=%s retry=%s/%s (delay=%sms): %s",
                        event_type,
                        correlation_id,
                        next_retry_count,
                        self.config.max_retry_attempts,
                        self.config.retry_delay_ms,
                        error,
                    )
                    channel.basic_ack(delivery_tag=delivery_tag)
                    return

                logger.warning(
                    "Retry scheduling failed for type=%s correlationID=%s. Dropping to avoid hot loop: %s",
                    event_type,
                    correlation_id,
                    error,
                )
                channel.basic_ack(delivery_tag=delivery_tag)
                return

            logger.error(
                "Retry limit reached for type=%s correlationID=%s. Dropping message: %s",
                event_type,
                correlation_id,
                error,
            )
            channel.basic_ack(delivery_tag=delivery_tag)
        except Exception as error:
            logger.exception(
                "Unexpected failure for type=%s correlationID=%s: %s",
                event_type,
                correlation_id,
                error,
            )
            channel.basic_ack(delivery_tag=delivery_tag)

    def _extract_retry_count(self, properties: pika.BasicProperties) -> int:
        if not properties or not properties.headers:
            return 0

        raw_value = properties.headers.get(self.config.retry_header_name, 0)
        if isinstance(raw_value, int):
            return max(0, raw_value)

        if isinstance(raw_value, str) and raw_value.isdigit():
            return int(raw_value)

        return 0

    def _retry_queue_for_delivery(self, method) -> Optional[str]:
        if (
            method.exchange == self.config.topic_exchange
            and method.routing_key == self.config.topic_routing_key
        ):
            return self.config.topic_retry_queue

        if method.exchange == self.config.fanout_exchange:
            return self.config.fanout_retry_queue

        return None

    def _enqueue_retry(
        self,
        method,
        properties: pika.BasicProperties,
        body: bytes,
        retry_count: int,
    ) -> bool:
        if not self._channel or not self._channel.is_open:
            return False

        retry_queue = self._retry_queue_for_delivery(method)
        if not retry_queue:
            logger.warning(
                "No retry queue mapping for exchange=%s routing_key=%s",
                method.exchange,
                method.routing_key,
            )
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
                routing_key=retry_queue,
                body=body,
                properties=next_properties,
                mandatory=False,
            )
            return True
        except Exception as error:
            logger.warning("Unable to republish retry message: %s", error)
            return False

    def process_payload(self, payload: Dict[str, Any]) -> None:
        event_type = payload.get("type")
        if not isinstance(event_type, str):
            raise PermanentNotificationError(
                "Payload must include string field 'type'")

        if event_type not in ALL_NOTIFICATION_TYPES:
            raise PermanentNotificationError(
                f"Unsupported notification type: {event_type}")

        self.validate_payload(event_type, payload)

        recipients = self.get_recipients(event_type, payload)
        template_data = self.build_template_data(event_type, payload)
        self.send_email(event_type, recipients, template_data)

    def validate_payload(self, event_type: str, payload: Dict[str, Any]) -> None:
        for field in REQUIRED_FIELDS_BY_TYPE[event_type]:
            if field not in payload or payload[field] in (None, ""):
                raise PermanentNotificationError(
                    f"Payload type {event_type} missing required field '{field}'"
                )

            if field != "waitlistEmails" and payload[field] == []:
                raise PermanentNotificationError(
                    f"Payload type {event_type} missing required field '{field}'"
                )

        if event_type in TOPIC_NOTIFICATION_TYPES:
            email = payload.get("email")
            if not isinstance(email, str) or "@" not in email:
                raise PermanentNotificationError(
                    f"Payload type {event_type} contains invalid email"
                )
            return

        waitlist_emails = payload.get("waitlistEmails")
        if not isinstance(waitlist_emails, list):
            raise PermanentNotificationError(
                f"Payload type {event_type} requires list field 'waitlistEmails'"
            )

        if not all(isinstance(email, str) and "@" in email for email in waitlist_emails):
            raise PermanentNotificationError(
                f"Payload type {event_type} has invalid email(s) in waitlistEmails"
            )

    def get_recipients(self, event_type: str, payload: Dict[str, Any]) -> List[str]:
        if event_type in TOPIC_NOTIFICATION_TYPES:
            return [payload["email"]]
        return payload["waitlistEmails"]

    def build_template_data(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload)
        data.pop("waitlistEmails", None)
        data["notificationType"] = event_type
        return data

    def send_email(self, event_type: str, recipients: List[str], template_data: Dict[str, Any]) -> None:
        if not recipients:
            logger.info(
                "No recipients for type=%s. Skipping email dispatch.", event_type)
            return

        template_env = TEMPLATE_ENV_BY_TYPE.get(event_type)
        if not template_env:
            raise PermanentNotificationError(
                f"No template mapping found for type {event_type}")

        template_id = os.getenv(template_env, "")
        if not template_id:
            self._handle_missing_config(
                f"{template_env} not configured for type {event_type}",
            )
            return

        if not self._sendgrid_client:
            self._handle_missing_config("SENDGRID_API_KEY not configured")
            return

        if not self.config.sendgrid_from_email:
            self._handle_missing_config("SENDGRID_FROM_EMAIL not configured")
            return

        message = Mail(
            from_email=(self.config.sendgrid_from_email,
                        self.config.sendgrid_from_name),
            to_emails=recipients,
            is_multiple=len(recipients) > 1,
        )
        message.template_id = template_id
        message.dynamic_template_data = template_data

        try:
            response = self._sendgrid_client.send(message)
        except HTTPError as error:
            status_code = int(getattr(error, "status_code", 0) or 0)
            detail = getattr(error, "body", None) or str(error)

            if status_code in {401, 403}:
                if not self.config.is_production:
                    logger.warning(
                        "Non-production fallback for invalid SendGrid credentials. status=%s type=%s",
                        status_code,
                        event_type,
                    )
                    return

                raise PermanentNotificationError(
                    f"SendGrid authentication failed with status {status_code}: {detail}"
                ) from error

            if 400 <= status_code < 500 and status_code != 429:
                raise PermanentNotificationError(
                    f"SendGrid rejected request with status {status_code}: {detail}"
                ) from error

            raise TransientNotificationError(
                f"SendGrid temporary failure with status {status_code}: {detail}"
            ) from error
        except Exception as error:
            raise TransientNotificationError(
                f"SendGrid transport error: {error}") from error

        status_code = int(response.status_code)
        if status_code == 202:
            return

        if status_code in {401, 403} and not self.config.is_production:
            logger.warning(
                "Non-production fallback for invalid SendGrid credentials. status=%s type=%s",
                status_code,
                event_type,
            )
            return

        if 400 <= status_code < 500 and status_code != 429:
            raise PermanentNotificationError(
                f"SendGrid rejected request with status {status_code}: {response.body}"
            )

        raise TransientNotificationError(
            f"SendGrid temporary failure with status {status_code}: {response.body}"
        )

    def _handle_missing_config(self, detail: str) -> None:
        if self.config.is_production:
            raise PermanentNotificationError(detail)

        logger.warning("Non-production log-only fallback: %s", detail)


def install_signal_handlers(worker: NotificationWorker) -> None:
    def _handle_signal(_signal_number, _frame) -> None:
        worker.request_shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def main() -> None:
    config = WorkerConfig.from_env()
    worker = NotificationWorker(config)
    install_signal_handlers(worker)
    worker.run_forever()


if __name__ == "__main__":
    main()
