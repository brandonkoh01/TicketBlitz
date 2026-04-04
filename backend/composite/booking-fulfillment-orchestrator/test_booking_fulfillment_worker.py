import booking_fulfillment_worker as worker_module
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

SERVICE_DIR = pathlib.Path(__file__).resolve().parent
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[3]

if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class _FakeChannel:
    def __init__(self):
        self.acks = []
        self.is_open = True

    def basic_ack(self, delivery_tag):
        self.acks.append(delivery_tag)


class BookingFulfillmentWorkerTests(unittest.TestCase):
    def _config(self):
        return worker_module.WorkerConfig(
            service_name="booking-fulfillment-orchestrator",
            exchange="ticketblitz",
            input_routing_key="booking.confirmed",
            queue_name="booking-fulfillment-orchestrator.booking.confirmed",
            retry_queue_name="booking-fulfillment-orchestrator.booking.confirmed.retry",
            notification_routing_key="notification.send",
            retry_header_name="x-bfo-retry",
            retry_delay_ms=5000,
            max_retry_attempts=2,
            reconnect_delay_seconds=1,
            inventory_service_url="http://inventory-service:5000",
            waitlist_service_url="http://waitlist-service:5000",
            event_service_url="http://event-service:5000",
            eticket_generate_url="http://kong:8000/eticket/generate",
            waitlist_auth_header="X-Internal-Token",
            internal_service_token="token",
            http_timeout_seconds=5,
            eticket_timeout_seconds=5,
            incident_type="BOOKING_FULFILLMENT_INCIDENT",
            incident_email="ops@example.com",
        )

    def test_normalize_payload_requires_fields(self):
        worker = worker_module.BookingFulfillmentWorker(self._config())

        with self.assertRaises(worker_module.InvalidMessageError):
            worker._normalize_payload({"holdID": "h-1"}, "corr-1")

    def test_process_payload_publishes_booking_confirmed_notification(self):
        worker = worker_module.BookingFulfillmentWorker(self._config())

        payload = {
            "holdID": "hold-1",
            "userID": "user-1",
            "eventID": "event-1",
            "email": "fan@example.com",
            "correlationID": "corr-1",
            "waitlistID": "wait-1",
        }

        with patch.object(worker, "_confirm_hold", return_value={"seatID": "seat-1", "seatNumber": "D12"}) as confirm_hold:
            with patch.object(worker, "_generate_eticket", return_value={"ticketID": "TKT-1"}) as generate_ticket:
                with patch.object(worker, "_confirm_waitlist") as confirm_waitlist:
                    with patch.object(worker, "_resolve_event_name", return_value="Coldplay Live"):
                        with patch.object(worker, "_publish_customer_notification") as publish_notification:
                            worker.process_payload(payload, "corr-1")

        confirm_hold.assert_called_once()
        generate_ticket.assert_called_once()
        confirm_waitlist.assert_called_once_with("wait-1", "hold-1")
        publish_notification.assert_called_once()
        sent = publish_notification.call_args.args[0]
        self.assertEqual(sent["type"], "BOOKING_CONFIRMED")
        self.assertEqual(sent["ticketID"], "TKT-1")

    def test_handle_delivery_retries_transient_error(self):
        worker = worker_module.BookingFulfillmentWorker(self._config())
        fake_channel = _FakeChannel()
        method = type("Method", (), {"delivery_tag": 99})()
        properties = worker_module.pika.BasicProperties(
            headers={"x-bfo-retry": 0})

        payload = {
            "holdID": "hold-1",
            "userID": "user-1",
            "eventID": "event-1",
            "email": "fan@example.com",
            "correlationID": "corr-1",
        }

        with patch.object(
            worker,
            "process_payload",
            side_effect=worker_module.ProcessingError(
                stage="eticket_generate",
                error_code="HTTP_503",
                message="temporary",
                retryable=True,
            ),
        ):
            with patch.object(worker, "_enqueue_retry", return_value=True) as enqueue_retry:
                with patch.object(worker, "_publish_incident") as publish_incident:
                    worker._handle_delivery(
                        fake_channel, method, properties, json.dumps(payload).encode("utf-8"))

        enqueue_retry.assert_called_once()
        publish_incident.assert_not_called()
        self.assertEqual(fake_channel.acks, [99])

    def test_handle_delivery_publishes_incident_after_retry_limit(self):
        worker = worker_module.BookingFulfillmentWorker(self._config())
        fake_channel = _FakeChannel()
        method = type("Method", (), {"delivery_tag": 7})()
        properties = worker_module.pika.BasicProperties(
            headers={"x-bfo-retry": 2})

        payload = {
            "holdID": "hold-1",
            "userID": "user-1",
            "eventID": "event-1",
            "email": "fan@example.com",
            "correlationID": "corr-1",
        }

        with patch.object(
            worker,
            "process_payload",
            side_effect=worker_module.ProcessingError(
                stage="eticket_generate",
                error_code="HTTP_503",
                message="temporary",
                retryable=True,
            ),
        ):
            with patch.object(worker, "_enqueue_retry", return_value=False) as enqueue_retry:
                with patch.object(worker, "_publish_incident") as publish_incident:
                    worker._handle_delivery(
                        fake_channel, method, properties, json.dumps(payload).encode("utf-8"))

        enqueue_retry.assert_not_called()
        publish_incident.assert_called_once()
        self.assertEqual(fake_channel.acks, [7])


if __name__ == "__main__":
    unittest.main()
