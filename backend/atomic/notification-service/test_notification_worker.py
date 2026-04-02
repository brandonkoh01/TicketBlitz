import os
import pathlib
import sys
import unittest

# Ensure shared/ can be imported by notification.py during test execution.
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import notification

SENDGRID_LIVE_TEST_FLAG = "RUN_SENDGRID_INTEGRATION_TESTS"
SENDGRID_LIVE_REQUIRED_ENV = (
    "SENDGRID_API_KEY",
    "SENDGRID_FROM_EMAIL",
    "SENDGRID_TEMPLATE_BOOKING_CONFIRMED",
    "SENDGRID_TEST_TO_EMAIL",
)


class _FakeResponse:
    def __init__(self, status_code, body=""):
        self.status_code = status_code
        self.body = body


class _FakeSendGridClient:
    def __init__(self, response):
        self.response = response
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        return self.response


class _FakeChannel:
    def __init__(self):
        self.is_open = True
        self.published = []

    def basic_publish(self, **kwargs):
        self.published.append(kwargs)


class NotificationWorkerTests(unittest.TestCase):
    def setUp(self):
        self.original_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def _config(self, is_production=False, api_key=""):
        return notification.WorkerConfig(
            service_name="notification-service",
            topic_exchange="ticketblitz",
            topic_routing_key="notification.send",
            topic_queue="notification-service.notification.send",
            topic_retry_queue="notification-service.notification.send.retry",
            fanout_exchange="ticketblitz.price",
            fanout_queue="notification-service.price.broadcast",
            fanout_retry_queue="notification-service.price.broadcast.retry",
            retry_header_name="x-notification-retry",
            retry_delay_ms=5000,
            max_retry_attempts=3,
            reconnect_delay_seconds=1,
            sendgrid_api_key=api_key,
            sendgrid_from_email="noreply@ticketblitz.com",
            sendgrid_from_name="TicketBlitz",
            is_production=is_production,
        )

    def _require_sendgrid_live_test_enabled(self):
        if os.getenv(SENDGRID_LIVE_TEST_FLAG) != "1":
            self.skipTest(
                "Live SendGrid test disabled. Set RUN_SENDGRID_INTEGRATION_TESTS=1 to enable."
            )

    def _require_sendgrid_live_env(self):
        missing = [name for name in SENDGRID_LIVE_REQUIRED_ENV if not os.getenv(name)]
        if missing:
            self.skipTest(
                "Live SendGrid test skipped. Missing env vars: " + ", ".join(sorted(missing))
            )

        template_id = os.getenv("SENDGRID_TEMPLATE_BOOKING_CONFIRMED", "").strip()
        if template_id in {"", "d-..."}:
            self.skipTest(
                "Live SendGrid test skipped. SENDGRID_TEMPLATE_BOOKING_CONFIRMED must be a real template id."
            )

    def _live_sendgrid_config(self):
        return notification.WorkerConfig(
            service_name="notification-service",
            topic_exchange="ticketblitz",
            topic_routing_key="notification.send",
            topic_queue="notification-service.notification.send",
            topic_retry_queue="notification-service.notification.send.retry",
            fanout_exchange="ticketblitz.price",
            fanout_queue="notification-service.price.broadcast",
            fanout_retry_queue="notification-service.price.broadcast.retry",
            retry_header_name="x-notification-retry",
            retry_delay_ms=5000,
            max_retry_attempts=0,
            reconnect_delay_seconds=1,
            sendgrid_api_key=os.getenv("SENDGRID_API_KEY", ""),
            sendgrid_from_email=os.getenv("SENDGRID_FROM_EMAIL", ""),
            sendgrid_from_name=os.getenv("SENDGRID_FROM_NAME", "TicketBlitz"),
            # Production mode ensures 401/403 fail the test instead of non-prod fallback.
            is_production=True,
        )

    def test_enqueue_retry_routes_topic_messages_to_retry_queue(self):
        worker = notification.NotificationWorker(self._config())
        fake_channel = _FakeChannel()
        worker._channel = fake_channel

        method = type(
            "Method",
            (),
            {"exchange": "ticketblitz", "routing_key": "notification.send"},
        )()
        properties = notification.pika.BasicProperties(headers={})

        enqueued = worker._enqueue_retry(method, properties, b"{}", retry_count=2)

        self.assertTrue(enqueued)
        self.assertEqual(len(fake_channel.published), 1)
        published = fake_channel.published[0]
        self.assertEqual(published["exchange"], "")
        self.assertEqual(
            published["routing_key"],
            "notification-service.notification.send.retry",
        )
        self.assertEqual(
            published["properties"].headers["x-notification-retry"],
            2,
        )

    def test_enqueue_retry_routes_fanout_messages_to_retry_queue(self):
        worker = notification.NotificationWorker(self._config())
        fake_channel = _FakeChannel()
        worker._channel = fake_channel

        method = type(
            "Method",
            (),
            {"exchange": "ticketblitz.price", "routing_key": ""},
        )()
        properties = notification.pika.BasicProperties(headers={})

        enqueued = worker._enqueue_retry(method, properties, b"{}", retry_count=1)

        self.assertTrue(enqueued)
        self.assertEqual(len(fake_channel.published), 1)
        published = fake_channel.published[0]
        self.assertEqual(published["exchange"], "")
        self.assertEqual(
            published["routing_key"],
            "notification-service.price.broadcast.retry",
        )

    def test_validate_payload_missing_field_raises_permanent_error(self):
        worker = notification.NotificationWorker(self._config())

        with self.assertRaises(notification.PermanentNotificationError):
            worker.validate_payload(
                "SEAT_AVAILABLE",
                {
                    "type": "SEAT_AVAILABLE",
                    "email": "fan@example.com",
                    "holdID": "H-002",
                    "paymentURL": "/waitlist/confirm/H-002",
                },
            )

    def test_process_payload_non_production_missing_sendgrid_config_falls_back(self):
        worker = notification.NotificationWorker(self._config(is_production=False, api_key=""))

        # Should not raise; logs warning and drops to non-production fallback behavior.
        worker.process_payload(
            {
                "type": "BOOKING_CONFIRMED",
                "email": "fan@example.com",
                "eventName": "Coldplay Live",
                "seatNumber": "D12",
                "ticketID": "TKT-9988",
            }
        )

    def test_send_email_sendgrid_status_classification(self):
        os.environ["SENDGRID_TEMPLATE_BOOKING_CONFIRMED"] = "d-template-id"

        worker = notification.NotificationWorker(self._config(is_production=False, api_key="test-key"))

        worker._sendgrid_client = _FakeSendGridClient(_FakeResponse(403, "forbidden"))
        worker.send_email(
            "BOOKING_CONFIRMED",
            ["fan@example.com"],
            {"eventName": "Coldplay Live"},
        )

        worker._sendgrid_client = _FakeSendGridClient(_FakeResponse(500, "server error"))
        with self.assertRaises(notification.TransientNotificationError):
            worker.send_email(
                "BOOKING_CONFIRMED",
                ["fan@example.com"],
                {"eventName": "Coldplay Live"},
            )

        worker._sendgrid_client = _FakeSendGridClient(_FakeResponse(400, "bad request"))
        with self.assertRaises(notification.PermanentNotificationError):
            worker.send_email(
                "BOOKING_CONFIRMED",
                ["fan@example.com"],
                {"eventName": "Coldplay Live"},
            )

    def test_process_payload_allows_empty_waitlist_email_list(self):
        worker = notification.NotificationWorker(self._config(is_production=False, api_key=""))

        # Fanout notifications can legitimately have no recipients.
        worker.process_payload(
            {
                "type": "FLASH_SALE_LAUNCHED",
                "eventID": "evt-1",
                "flashSaleID": "fs-1",
                "updatedPrices": [{"category": "CAT1", "newPrice": 150.0}],
                "waitlistEmails": [],
            }
        )

    def test_sendgrid_live_booking_confirmed_email_delivery(self):
        self._require_sendgrid_live_test_enabled()
        self._require_sendgrid_live_env()

        worker = notification.NotificationWorker(self._live_sendgrid_config())
        worker.process_payload(
            {
                "type": "BOOKING_CONFIRMED",
                "email": os.environ["SENDGRID_TEST_TO_EMAIL"],
                "eventName": "TicketBlitz SendGrid Smoke Test",
                "seatNumber": "SG-A1",
                "ticketID": "SG-TEST-001",
            }
        )


if __name__ == "__main__":
    unittest.main()
