import notification
import os
import pathlib
import sys
import unittest
from python_http_client.exceptions import HTTPError

# Ensure shared/ can be imported by notification.py during test execution.
SERVICE_DIR = pathlib.Path(__file__).resolve().parent
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


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


class _FakeRaisingSendGridClient:
    def __init__(self, error):
        self.error = error
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        raise self.error


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
        missing = [
            name for name in SENDGRID_LIVE_REQUIRED_ENV if not os.getenv(name)]
        if missing:
            self.skipTest(
                "Live SendGrid test skipped. Missing env vars: " +
                ", ".join(sorted(missing))
            )

        template_id = os.getenv(
            "SENDGRID_TEMPLATE_BOOKING_CONFIRMED", "").strip()
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

        enqueued = worker._enqueue_retry(
            method, properties, b"{}", retry_count=2)

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

        enqueued = worker._enqueue_retry(
            method, properties, b"{}", retry_count=1)

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

    def test_validate_payload_requires_event_name_for_flash_sale_notifications(self):
        worker = notification.NotificationWorker(self._config())

        with self.assertRaises(notification.PermanentNotificationError):
            worker.validate_payload(
                "FLASH_SALE_LAUNCHED",
                {
                    "type": "FLASH_SALE_LAUNCHED",
                    "eventID": "evt-1",
                    "flashSaleID": "fs-1",
                    "updatedPrices": [{"category": "CAT1", "newPrice": 123.0}],
                    "waitlistEmails": ["fan@example.com"],
                },
            )

    def test_validate_payload_requires_discount_for_flash_sale_launch(self):
        worker = notification.NotificationWorker(self._config())

        with self.assertRaises(notification.PermanentNotificationError):
            worker.validate_payload(
                "FLASH_SALE_LAUNCHED",
                {
                    "type": "FLASH_SALE_LAUNCHED",
                    "eventID": "evt-1",
                    "eventName": "Coldplay Live 2026",
                    "flashSaleID": "fs-1",
                    "updatedPrices": [{"category": "CAT1", "newPrice": 123.0}],
                    "waitlistEmails": ["fan@example.com"],
                },
            )

    def test_validate_payload_ticket_available_public_accepts_waitlist_emails(self):
        worker = notification.NotificationWorker(self._config())

        worker.validate_payload(
            "TICKET_AVAILABLE_PUBLIC",
            {
                "type": "TICKET_AVAILABLE_PUBLIC",
                "bookingID": "BK-777",
                "eventName": "Coldplay Live",
                "waitlistEmails": ["fan1@example.com", "fan2@example.com"],
            },
        )

    def test_get_recipients_ticket_available_public_prefers_waitlist_email_list(self):
        worker = notification.NotificationWorker(self._config())

        recipients = worker.get_recipients(
            "TICKET_AVAILABLE_PUBLIC",
            {
                "type": "TICKET_AVAILABLE_PUBLIC",
                "email": "fallback@example.com",
                "waitlistEmails": [
                    "fan1@example.com",
                    "fan1@example.com",
                    "fan2@example.com",
                ],
            },
        )

        self.assertEqual(recipients, ["fan1@example.com", "fan2@example.com"])

    def test_process_payload_non_production_missing_sendgrid_config_falls_back(self):
        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key=""))

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

        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key="test-key"))

        worker._sendgrid_client = _FakeSendGridClient(
            _FakeResponse(403, "forbidden"))
        with self.assertRaises(notification.PermanentNotificationError):
            worker.send_email(
                "BOOKING_CONFIRMED",
                ["fan@example.com"],
                {"eventName": "Coldplay Live"},
            )

        worker._sendgrid_client = _FakeSendGridClient(
            _FakeResponse(500, "server error"))
        with self.assertRaises(notification.TransientNotificationError):
            worker.send_email(
                "BOOKING_CONFIRMED",
                ["fan@example.com"],
                {"eventName": "Coldplay Live"},
            )

        worker._sendgrid_client = _FakeSendGridClient(
            _FakeResponse(400, "bad request"))
        with self.assertRaises(notification.PermanentNotificationError):
            worker.send_email(
                "BOOKING_CONFIRMED",
                ["fan@example.com"],
                {"eventName": "Coldplay Live"},
            )

    def test_send_email_non_production_sendgrid_http_401_falls_back_when_opted_in(self):
        os.environ["SENDGRID_TEMPLATE_BOOKING_CONFIRMED"] = "d-template-id"
        os.environ[notification.SENDGRID_AUTH_FALLBACK_ENV] = "1"

        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key="test-key"))
        worker._sendgrid_client = _FakeRaisingSendGridClient(
            HTTPError(401, "Unauthorized", b"unauthorized", {})
        )

        worker.send_email(
            "BOOKING_CONFIRMED",
            ["fan@example.com"],
            {"eventName": "Coldplay Live"},
        )

    def test_send_email_non_production_sendgrid_http_401_raises_without_opt_in(self):
        os.environ["SENDGRID_TEMPLATE_BOOKING_CONFIRMED"] = "d-template-id"

        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key="test-key"))
        worker._sendgrid_client = _FakeRaisingSendGridClient(
            HTTPError(401, "Unauthorized", b"unauthorized", {})
        )

        with self.assertRaises(notification.PermanentNotificationError):
            worker.send_email(
                "BOOKING_CONFIRMED",
                ["fan@example.com"],
                {"eventName": "Coldplay Live"},
            )

    def test_send_email_non_production_quota_exceeded_is_transient(self):
        os.environ["SENDGRID_TEMPLATE_BOOKING_CONFIRMED"] = "d-template-id"

        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key="test-key"))
        worker._sendgrid_client = _FakeRaisingSendGridClient(
            HTTPError(
                401,
                "Unauthorized",
                b'{"errors":[{"message":"Maximum credits exceeded"}]}',
                {},
            )
        )

        with self.assertRaises(notification.TransientNotificationError):
            worker.send_email(
                "BOOKING_CONFIRMED",
                ["fan@example.com"],
                {"eventName": "Coldplay Live"},
            )

    def test_send_email_production_sendgrid_http_401_raises_permanent(self):
        os.environ["SENDGRID_TEMPLATE_BOOKING_CONFIRMED"] = "d-template-id"

        worker = notification.NotificationWorker(
            self._config(is_production=True, api_key="test-key"))
        worker._sendgrid_client = _FakeRaisingSendGridClient(
            HTTPError(401, "Unauthorized", b"unauthorized", {})
        )

        with self.assertRaises(notification.PermanentNotificationError):
            worker.send_email(
                "BOOKING_CONFIRMED",
                ["fan@example.com"],
                {"eventName": "Coldplay Live"},
            )

    def test_send_email_ticket_available_public_sends_bulk(self):
        os.environ["SENDGRID_TEMPLATE_TICKET_AVAILABLE_PUBLIC"] = "d-template-id"

        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key="test-key")
        )
        fake_client = _FakeSendGridClient(_FakeResponse(202, "accepted"))
        worker._sendgrid_client = fake_client

        worker.send_email(
            "TICKET_AVAILABLE_PUBLIC",
            ["fan1@example.com", "fan2@example.com", "fan3@example.com"],
            {"eventName": "Lawrence Wong Live", "bookingID": "BK-777"},
        )

        self.assertEqual(len(fake_client.sent), 1)

    def test_process_payload_allows_empty_waitlist_email_list(self):
        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key=""))

        # Fanout notifications can legitimately have no recipients.
        worker.process_payload(
            {
                "type": "FLASH_SALE_LAUNCHED",
                "eventID": "evt-1",
                "eventName": "Coldplay Live 2026",
                "flashSaleID": "fs-1",
                "discountPercentage": "30.00%",
                "updatedPrices": [{"category": "CAT1", "newPrice": 150.0}],
                "waitlistEmails": [],
            }
        )

    def test_process_payload_sends_flash_sale_email_when_template_is_configured(self):
        os.environ["SENDGRID_TEMPLATE_FLASH_SALE_LAUNCHED"] = "d-template-id"

        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key="test-key"))
        worker._sendgrid_client = _FakeSendGridClient(_FakeResponse(202, "accepted"))

        worker.process_payload(
            {
                "type": "FLASH_SALE_LAUNCHED",
                "eventID": "10000000-0000-0000-0000-000000000501",
                "eventName": "Coldplay Live 2026",
                "flashSaleID": "b28df509-0fc2-4909-bf90-e14f0cfbd1de",
                "updatedPrices": [{"category": "CAT1", "newPrice": 131.6}],
                "waitlistEmails": ["fan@example.com"],
                "expiresAt": "2026-04-08T05:56:55Z",
                "discountPercentage": "30.00",
            }
        )

        self.assertEqual(len(worker._sendgrid_client.sent), 1)

    def test_build_template_data_formats_flash_sale_launch_fields_for_display(self):
        worker = notification.NotificationWorker(self._config(is_production=False, api_key=""))

        template_data = worker.build_template_data(
            "FLASH_SALE_LAUNCHED",
            {
                "type": "FLASH_SALE_LAUNCHED",
                "eventID": "10000000-0000-0000-0000-000000000501",
                "eventName": "Coldplay Live 2026",
                "flashSaleID": "b28df509-0fc2-4909-bf90-e14f0cfbd1de",
                "discountPercentage": "30.00",
                "updatedPrices": [{"category": "CAT1", "newPrice": 131.6}],
                "waitlistEmails": ["fan@example.com"],
                "expiresAt": "2026-04-08T05:56:55Z",
            },
        )

        self.assertEqual(template_data["discountPercentage"], "30.00%")
        self.assertEqual(template_data["expiresAtDisplay"], "08/04/26 01:56 PM SGT")

    def test_validate_payload_rejects_invalid_fanout_waitlist_email(self):
        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key=""))

        with self.assertRaises(notification.PermanentNotificationError):
            worker.validate_payload(
                "PRICE_ESCALATED",
                {
                    "type": "PRICE_ESCALATED",
                    "eventID": "10000000-0000-0000-0000-000000000501",
                    "eventName": "Coldplay Live 2026",
                    "flashSaleID": "b28df509-0fc2-4909-bf90-e14f0cfbd1de",
                    "soldOutCategory": "CAT1",
                    "updatedPrices": [{"category": "CAT2", "newPrice": 96.6}],
                    "waitlistEmails": ["invalid-email"],
                },
            )

    def test_send_email_missing_scenario2_template_raises_in_production(self):
        worker = notification.NotificationWorker(
            self._config(is_production=True, api_key="test-key"))
        worker._sendgrid_client = _FakeSendGridClient(_FakeResponse(202, "accepted"))

        with self.assertRaises(notification.PermanentNotificationError):
            worker.send_email(
                "FLASH_SALE_ENDED",
                ["fan@example.com"],
                {
                    "eventID": "10000000-0000-0000-0000-000000000501",
                    "eventName": "Coldplay Live 2026",
                    "flashSaleID": "b28df509-0fc2-4909-bf90-e14f0cfbd1de",
                    "revertedPrices": [{"category": "CAT1", "newPrice": 188.0}],
                },
            )

    def test_validate_payload_requires_incident_fields(self):
        worker = notification.NotificationWorker(
            self._config(is_production=False, api_key=""))

        with self.assertRaises(notification.PermanentNotificationError):
            worker.validate_payload(
                "BOOKING_FULFILLMENT_INCIDENT",
                {
                    "type": "BOOKING_FULFILLMENT_INCIDENT",
                    "email": "ops@example.com",
                    "holdID": "hold-1",
                    "correlationID": "corr-1",
                    "errorCode": "HTTP_500",
                    # missing errorMessage and stage
                },
            )

    def test_process_payload_accepts_scenario3_type(self):
        worker = notification.NotificationWorker(self._config(is_production=False, api_key=""))

        worker.process_payload(
            {
                "type": "CANCELLATION_CONFIRMED",
                "email": "fan@example.com",
                "bookingID": "BK-500",
                "eventName": "Coldplay Live",
            }
        )

    def test_process_payload_rejects_scenario3_without_event_name(self):
        worker = notification.NotificationWorker(self._config(is_production=False, api_key=""))

        with self.assertRaises(notification.PermanentNotificationError):
            worker.process_payload(
                {
                    "type": "TICKET_CONFIRMATION",
                    "email": "fan@example.com",
                    "bookingID": "BK-501",
                    "ticketID": "TKT-501",
                    "seatNumber": "A1",
                }
            )

    def test_build_template_data_waitlist_joined_derives_status_url(self):
        worker = notification.NotificationWorker(self._config(is_production=False, api_key=""))
        os.environ["WAITLIST_STATUS_URL_TEMPLATE"] = "https://ticketblitz.app/waitlist/{waitlistID}"

        template_data = worker.build_template_data(
            "WAITLIST_JOINED",
            {
                "type": "WAITLIST_JOINED",
                "email": "fan@example.com",
                "eventName": "Coldplay Live",
                "position": 3,
                "waitlistID": "a6f0574e-7c9f-4b12-8e56-fa95b8fbfa4a",
            },
        )

        self.assertEqual(
            template_data["waitlistStatusURL"],
            "https://ticketblitz.app/waitlist/a6f0574e-7c9f-4b12-8e56-fa95b8fbfa4a",
        )

    def test_build_template_data_waitlist_joined_keeps_explicit_status_url(self):
        worker = notification.NotificationWorker(self._config(is_production=False, api_key=""))

        template_data = worker.build_template_data(
            "WAITLIST_JOINED",
            {
                "type": "WAITLIST_JOINED",
                "email": "fan@example.com",
                "eventName": "Coldplay Live",
                "position": 2,
                "waitlistID": "waitlist-123",
                "waitlistStatusURL": "https://example.com/custom/waitlist-123",
            },
        )

        self.assertEqual(
            template_data["waitlistStatusURL"],
            "https://example.com/custom/waitlist-123",
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
