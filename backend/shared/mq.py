import json
import os
from typing import Any, Optional

import pika


def rabbitmq_configured() -> bool:
    return bool(os.getenv("RABBITMQ_URL"))


def get_connection() -> pika.BlockingConnection:
    url = os.getenv("RABBITMQ_URL")
    if not url:
        raise RuntimeError("RABBITMQ_URL must be set before using RabbitMQ")

    params = pika.URLParameters(url)
    params.heartbeat = int(os.getenv("RABBITMQ_HEARTBEAT", "60"))
    params.blocked_connection_timeout = int(os.getenv("RABBITMQ_BLOCKED_TIMEOUT", "30"))
    params.connection_attempts = int(os.getenv("RABBITMQ_CONNECTION_ATTEMPTS", "3"))
    params.retry_delay = float(os.getenv("RABBITMQ_RETRY_DELAY", "5"))

    return pika.BlockingConnection(params)


def publish_json(
    routing_key: str,
    payload: Any,
    exchange: Optional[str] = None,
    mandatory: bool = False,
) -> None:
    exchange_name = exchange or os.getenv("RABBITMQ_EXCHANGE", "ticketblitz")
    exchange_type = os.getenv("RABBITMQ_EXCHANGE_TYPE", "topic")
    exchange_durable = os.getenv("RABBITMQ_EXCHANGE_DURABLE", "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    body = json.dumps(payload, default=str)

    connection = get_connection()
    try:
        channel = connection.channel()
        if exchange_name:
            channel.exchange_declare(
                exchange=exchange_name,
                exchange_type=exchange_type,
                durable=exchange_durable,
            )
        channel.basic_publish(
            exchange=exchange_name,
            routing_key=routing_key,
            body=body,
            mandatory=mandatory,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
    finally:
        connection.close()
