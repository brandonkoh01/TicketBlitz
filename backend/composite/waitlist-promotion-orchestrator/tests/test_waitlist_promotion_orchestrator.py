import os
import pathlib
import sys
import unittest
from unittest.mock import patch

# Ensure shared/ can be imported by waitlist_promotion.py during test execution.
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[3]
SERVICE_ROOT = pathlib.Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import waitlist_promotion


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        if text is not None:
            self.text = text
        elif payload is None:
            self.text = ""
        else:
            self.text = "json"

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.closed = False

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        key = (method.upper(), url)
        if key not in self.routes:
            return _FakeResponse(404, {"error": f"No route for {method} {url}"})
        route = self.routes[key]
        if isinstance(route, Exception):
            raise route
        return route

    def close(self):
        self.closed = True


class _FakeChannel:
    def __init__(self):
        self.is_open = True
        self.acked = []
        self.published = []

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_publish(self, **kwargs):
        self.published.append(kwargs)


class _MethodFrame:
    def __init__(self, delivery_tag=1):
        self.delivery_tag = delivery_tag


class WaitlistPromotionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.original_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def _config(self):
        return waitlist_promotion.WorkerConfig(
            service_name="waitlist-promotion-orchestrator",
            topic_exchange="ticketblitz",
            seat_released_routing_key="seat.released",
            seat_released_queue="waitlist-promotion-orchestrator.seat.released",
            seat_released_retry_queue="waitlist-promotion-orchestrator.seat.released.retry",
            retry_header_name="x-waitlist-promotion-retry",
            retry_delay_ms=5000,
            max_retry_attempts=3,
            reconnect_delay_seconds=1,
            inventory_service_url="http://inventory-service:5000",
            waitlist_service_url="http://waitlist-service:5000",
            user_service_url="http://user-service:5000",
            request_connect_timeout_seconds=1.0,
            request_read_timeout_seconds=2.0,
            http_retry_total=0,
            http_retry_backoff_factor=0.0,
            internal_auth_header="X-Internal-Token",
            internal_service_token="ticketblitz-internal-token",
            waitlist_payment_url_template="/waitlist/confirm/{holdID}",
        )

    def test_from_env_applies_defaults_and_validation(self):
        os.environ["SERVICE_NAME"] = ""
        os.environ["INVENTORY_SERVICE_URL"] = "http://inventory-service:5000/"
        os.environ["WAITLIST_SERVICE_URL"] = "http://waitlist-service:5000/"
        os.environ["USER_SERVICE_URL"] = "http://user-service:5000/"
        os.environ["WAITLIST_PROMOTION_RETRY_DELAY_MS"] = "0"

        config = waitlist_promotion.WorkerConfig.from_env()

        self.assertEqual(config.service_name, "waitlist-promotion-orchestrator")
        self.assertEqual(config.inventory_service_url, "http://inventory-service:5000")
        self.assertEqual(config.retry_delay_ms, 100)

    def test_from_env_rejects_invalid_urls(self):
        os.environ["INVENTORY_SERVICE_URL"] = "inventory-service:5000"

        with self.assertRaises(ValueError):
            waitlist_promotion.WorkerConfig.from_env()

    def test_process_payload_promotes_waitlisted_user_and_publishes_notification(self):
        routes = {
            (
                "GET",
                "http://waitlist-service:5000/waitlist/next?eventID=evt-1&seatCategory=CAT1",
            ): _FakeResponse(
                200,
                {
                    "waitlistID": "w-1",
                    "userID": "u-1",
                    "status": "WAITING",
                },
            ),
            ("GET", "http://user-service:5000/user/u-1"): _FakeResponse(
                200,
                {
                    "userID": "u-1",
                    "email": "fan@example.com",
                },
            ),
            ("POST", "http://inventory-service:5000/inventory/hold"): _FakeResponse(
                201,
                {
                    "holdID": "h-1",
                    "holdExpiry": "2026-04-04T10:00:00+00:00",
                },
            ),
            ("PUT", "http://waitlist-service:5000/waitlist/w-1/offer"): _FakeResponse(
                200,
                {
                    "waitlistID": "w-1",
                    "status": "HOLD_OFFERED",
                    "holdID": "h-1",
                },
            ),
        }
        session = _FakeSession(routes)
        published = []

        worker = waitlist_promotion.WaitlistPromotionWorker(
            self._config(),
            session=session,
            publisher=lambda **kwargs: published.append(kwargs),
        )

        worker.process_payload(
            {
                "eventID": "evt-1",
                "seatCategory": "cat1",
                "seatID": "s-1",
                "reason": "MANUAL_RELEASE",
            }
        )

        self.assertEqual(len(published), 1)
        payload = published[0]["payload"]
        self.assertEqual(payload["type"], "SEAT_AVAILABLE")
        self.assertEqual(payload["email"], "fan@example.com")
        self.assertEqual(payload["holdID"], "h-1")
        self.assertEqual(payload["paymentURL"], "/waitlist/confirm/h-1")

        hold_call = next(call for call in session.calls if call["url"].endswith("/inventory/hold"))
        self.assertTrue(hold_call["json"]["fromWaitlist"])
        self.assertIn("idempotencyKey", hold_call["json"])

    def test_process_payload_sets_seat_available_when_no_waitlist_candidate(self):
        routes = {
            (
                "GET",
                "http://waitlist-service:5000/waitlist/next?eventID=evt-1&seatCategory=CAT1",
            ): _FakeResponse(404, {"error": "No waiting users"}),
            ("PUT", "http://inventory-service:5000/inventory/seat/s-1/status"): _FakeResponse(
                200,
                {"seatID": "s-1", "status": "AVAILABLE"},
            ),
        }
        session = _FakeSession(routes)
        published = []

        worker = waitlist_promotion.WaitlistPromotionWorker(
            self._config(),
            session=session,
            publisher=lambda **kwargs: published.append(kwargs),
        )

        worker.process_payload(
            {
                "eventID": "evt-1",
                "seatCategory": "CAT1",
                "seatID": "s-1",
                "reason": "MANUAL_RELEASE",
            }
        )

        self.assertEqual(len(published), 0)
        self.assertTrue(any(call["url"].endswith("/inventory/seat/s-1/status") for call in session.calls))

    def test_process_payload_handles_timeout_branch_and_emits_hold_expired(self):
        routes = {
            ("GET", "http://waitlist-service:5000/waitlist/by-hold/h-old"): _FakeResponse(
                200,
                {"waitlistID": "w-old", "userID": "u-old", "holdID": "h-old", "status": "HOLD_OFFERED"},
            ),
            ("PUT", "http://waitlist-service:5000/waitlist/w-old/expire"): _FakeResponse(
                200,
                {"waitlistID": "w-old", "status": "EXPIRED", "holdID": "h-old"},
            ),
            ("GET", "http://user-service:5000/user/u-old"): _FakeResponse(
                200,
                {"userID": "u-old", "email": "old@example.com"},
            ),
            (
                "GET",
                "http://waitlist-service:5000/waitlist/next?eventID=evt-1&seatCategory=CAT1",
            ): _FakeResponse(404, {"error": "No waiting users"}),
            ("PUT", "http://inventory-service:5000/inventory/seat/s-1/status"): _FakeResponse(
                200,
                {"seatID": "s-1", "status": "AVAILABLE"},
            ),
        }
        session = _FakeSession(routes)
        published = []

        worker = waitlist_promotion.WaitlistPromotionWorker(
            self._config(),
            session=session,
            publisher=lambda **kwargs: published.append(kwargs),
        )

        worker.process_payload(
            {
                "eventID": "evt-1",
                "seatCategory": "CAT1",
                "seatID": "s-1",
                "reason": "PAYMENT_TIMEOUT",
                "expiredHoldID": "h-old",
            }
        )

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["payload"]["type"], "HOLD_EXPIRED")
        self.assertEqual(published[0]["payload"]["email"], "old@example.com")

    def test_process_payload_treats_offer_conflict_with_matching_hold_as_idempotent(self):
        routes = {
            (
                "GET",
                "http://waitlist-service:5000/waitlist/next?eventID=evt-1&seatCategory=CAT1",
            ): _FakeResponse(200, {"waitlistID": "w-1", "userID": "u-1", "status": "WAITING"}),
            ("GET", "http://user-service:5000/user/u-1"): _FakeResponse(200, {"email": "fan@example.com"}),
            ("POST", "http://inventory-service:5000/inventory/hold"): _FakeResponse(
                200,
                {"holdID": "h-1", "holdExpiry": "2026-04-04T10:00:00+00:00"},
            ),
            ("PUT", "http://waitlist-service:5000/waitlist/w-1/offer"): _FakeResponse(
                409,
                {"error": "Cannot transition"},
            ),
            ("GET", "http://waitlist-service:5000/waitlist/w-1"): _FakeResponse(
                200,
                {
                    "waitlistID": "w-1",
                    "status": "HOLD_OFFERED",
                    "holdID": "h-1",
                    "userID": "u-1",
                },
            ),
        }
        session = _FakeSession(routes)
        published = []

        worker = waitlist_promotion.WaitlistPromotionWorker(
            self._config(),
            session=session,
            publisher=lambda **kwargs: published.append(kwargs),
        )

        worker.process_payload(
            {
                "eventID": "evt-1",
                "seatCategory": "CAT1",
                "seatID": "s-1",
                "reason": "MANUAL_RELEASE",
            }
        )

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["payload"]["type"], "SEAT_AVAILABLE")

    def test_handle_delivery_retries_transient_error(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))
        fake_channel = _FakeChannel()
        worker._channel = fake_channel

        with patch.object(worker, "process_payload", side_effect=waitlist_promotion.TransientProcessingError("boom")):
            method = _MethodFrame(delivery_tag=7)
            properties = waitlist_promotion.pika.BasicProperties(headers={})
            worker._handle_delivery(fake_channel, method, properties, b'{"eventID":"evt","seatCategory":"CAT1","seatID":"s","reason":"MANUAL_RELEASE"}')

        self.assertEqual(fake_channel.acked, [7])
        self.assertEqual(len(fake_channel.published), 1)
        self.assertEqual(
            fake_channel.published[0]["routing_key"],
            "waitlist-promotion-orchestrator.seat.released.retry",
        )

    def test_handle_delivery_drops_malformed_json(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))
        fake_channel = _FakeChannel()
        method = _MethodFrame(delivery_tag=9)
        properties = waitlist_promotion.pika.BasicProperties(headers={})

        worker._handle_delivery(fake_channel, method, properties, b"not-json")

        self.assertEqual(fake_channel.acked, [9])
        self.assertEqual(fake_channel.published, [])


if __name__ == "__main__":
    unittest.main()
