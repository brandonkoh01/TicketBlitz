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

EVENT_ID = "10000000-0000-0000-0000-000000000301"
SEAT_ID = "30000000-0000-0000-0000-000000000042"
WAITLIST_ID = "9bb20000-0000-0000-0000-000000000001"
USER_ID = "9aa10000-0000-0000-0000-000000000001"
HOLD_ID = "4c100000-0000-0000-0000-000000000001"
OLD_WAITLIST_ID = "9bb20000-0000-0000-0000-000000000002"
OLD_USER_ID = "9aa10000-0000-0000-0000-000000000002"
OLD_HOLD_ID = "4c100000-0000-0000-0000-000000000002"
OTHER_HOLD_ID = "4c100000-0000-0000-0000-000000000099"


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
        self.nacked = []
        self.published = []
        self.publish_error = None

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag, requeue=False):
        self.nacked.append({"delivery_tag": delivery_tag, "requeue": requeue})

    def basic_publish(self, **kwargs):
        if self.publish_error is not None:
            raise self.publish_error
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

    def _config_with(self, **overrides):
        values = self._config().__dict__.copy()
        values.update(overrides)
        return waitlist_promotion.WorkerConfig(**values)

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

    def test_from_env_rejects_blank_internal_auth_header_when_token_is_set(self):
        os.environ["INTERNAL_SERVICE_TOKEN"] = "token"
        os.environ["INTERNAL_AUTH_HEADER"] = "   "

        with self.assertRaises(ValueError):
            waitlist_promotion.WorkerConfig.from_env()

    def test_build_payment_url_appends_hold_id_without_placeholder(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(
            self._config_with(waitlist_payment_url_template="/waitlist/confirm"),
            session=_FakeSession({}),
        )

        self.assertEqual(worker._build_payment_url(HOLD_ID), f"/waitlist/confirm/{HOLD_ID}")

    def test_internal_auth_headers_returns_empty_map_when_token_is_not_set(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(
            self._config_with(internal_service_token=""),
            session=_FakeSession({}),
        )

        self.assertEqual(worker._internal_auth_headers(), {})

    def test_process_payload_promotes_waitlisted_user_and_publishes_notification(self):
        routes = {
            (
                "GET",
                f"http://waitlist-service:5000/waitlist/next?eventID={EVENT_ID}&seatCategory=CAT1",
            ): _FakeResponse(
                200,
                {
                    "waitlistID": WAITLIST_ID,
                    "userID": USER_ID,
                    "status": "WAITING",
                },
            ),
            ("GET", f"http://user-service:5000/user/{USER_ID}"): _FakeResponse(
                200,
                {
                    "userID": USER_ID,
                    "email": "fan@example.com",
                },
            ),
            ("POST", "http://inventory-service:5000/inventory/hold"): _FakeResponse(
                201,
                {
                    "holdID": HOLD_ID,
                    "holdExpiry": "2026-04-04T10:00:00+00:00",
                },
            ),
            ("PUT", f"http://waitlist-service:5000/waitlist/{WAITLIST_ID}/offer"): _FakeResponse(
                200,
                {
                    "waitlistID": WAITLIST_ID,
                    "status": "HOLD_OFFERED",
                    "holdID": HOLD_ID,
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
                "eventID": EVENT_ID,
                "seatCategory": "cat1",
                "seatID": SEAT_ID,
                "reason": "MANUAL_RELEASE",
            }
        )

        self.assertEqual(len(published), 1)
        payload = published[0]["payload"]
        self.assertEqual(payload["type"], "SEAT_AVAILABLE")
        self.assertEqual(payload["email"], "fan@example.com")
        self.assertEqual(payload["holdID"], HOLD_ID)
        self.assertEqual(payload["paymentURL"], f"/waitlist/confirm/{HOLD_ID}")

        hold_call = next(call for call in session.calls if call["url"].endswith("/inventory/hold"))
        self.assertTrue(hold_call["json"]["fromWaitlist"])
        self.assertIn("idempotencyKey", hold_call["json"])

    def test_process_payload_sets_seat_available_when_no_waitlist_candidate(self):
        routes = {
            (
                "GET",
                f"http://waitlist-service:5000/waitlist/next?eventID={EVENT_ID}&seatCategory=CAT1",
            ): _FakeResponse(404, {"error": "No waiting users"}),
            ("PUT", f"http://inventory-service:5000/inventory/seat/{SEAT_ID}/status"): _FakeResponse(
                200,
                {"seatID": SEAT_ID, "status": "AVAILABLE"},
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
                "eventID": EVENT_ID,
                "seatCategory": "CAT1",
                "seatID": SEAT_ID,
                "reason": "MANUAL_RELEASE",
            }
        )

        self.assertEqual(len(published), 0)
        self.assertTrue(any(call["url"].endswith(f"/inventory/seat/{SEAT_ID}/status") for call in session.calls))

    def test_process_payload_handles_timeout_branch_and_emits_hold_expired(self):
        routes = {
            ("GET", f"http://waitlist-service:5000/waitlist/by-hold/{OLD_HOLD_ID}"): _FakeResponse(
                200,
                {
                    "waitlistID": OLD_WAITLIST_ID,
                    "userID": OLD_USER_ID,
                    "holdID": OLD_HOLD_ID,
                    "status": "HOLD_OFFERED",
                },
            ),
            ("PUT", f"http://waitlist-service:5000/waitlist/{OLD_WAITLIST_ID}/expire"): _FakeResponse(
                200,
                {"waitlistID": OLD_WAITLIST_ID, "status": "EXPIRED", "holdID": OLD_HOLD_ID},
            ),
            ("GET", f"http://user-service:5000/user/{OLD_USER_ID}"): _FakeResponse(
                200,
                {"userID": OLD_USER_ID, "email": "old@example.com"},
            ),
            (
                "GET",
                f"http://waitlist-service:5000/waitlist/next?eventID={EVENT_ID}&seatCategory=CAT1",
            ): _FakeResponse(404, {"error": "No waiting users"}),
            ("PUT", f"http://inventory-service:5000/inventory/seat/{SEAT_ID}/status"): _FakeResponse(
                200,
                {"seatID": SEAT_ID, "status": "AVAILABLE"},
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
                "eventID": EVENT_ID,
                "seatCategory": "CAT1",
                "seatID": SEAT_ID,
                "reason": "PAYMENT_TIMEOUT",
                "expiredHoldID": OLD_HOLD_ID,
            }
        )

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["payload"]["type"], "HOLD_EXPIRED")
        self.assertEqual(published[0]["payload"]["email"], "old@example.com")

    def test_process_payload_treats_offer_conflict_with_matching_hold_as_idempotent(self):
        routes = {
            (
                "GET",
                f"http://waitlist-service:5000/waitlist/next?eventID={EVENT_ID}&seatCategory=CAT1",
            ): _FakeResponse(200, {"waitlistID": WAITLIST_ID, "userID": USER_ID, "status": "WAITING"}),
            ("GET", f"http://user-service:5000/user/{USER_ID}"): _FakeResponse(200, {"email": "fan@example.com"}),
            ("POST", "http://inventory-service:5000/inventory/hold"): _FakeResponse(
                200,
                {"holdID": HOLD_ID, "holdExpiry": "2026-04-04T10:00:00+00:00"},
            ),
            ("PUT", f"http://waitlist-service:5000/waitlist/{WAITLIST_ID}/offer"): _FakeResponse(
                409,
                {"error": "Cannot transition"},
            ),
            ("GET", f"http://waitlist-service:5000/waitlist/{WAITLIST_ID}"): _FakeResponse(
                200,
                {
                    "waitlistID": WAITLIST_ID,
                    "status": "HOLD_OFFERED",
                    "holdID": HOLD_ID,
                    "userID": USER_ID,
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
                "eventID": EVENT_ID,
                "seatCategory": "CAT1",
                "seatID": SEAT_ID,
                "reason": "MANUAL_RELEASE",
            }
        )

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["payload"]["type"], "SEAT_AVAILABLE")

    def test_process_payload_releases_hold_when_offer_returns_missing_hold_id(self):
        routes = {
            (
                "GET",
                f"http://waitlist-service:5000/waitlist/next?eventID={EVENT_ID}&seatCategory=CAT1",
            ): _FakeResponse(200, {"waitlistID": WAITLIST_ID, "userID": USER_ID, "status": "WAITING"}),
            ("GET", f"http://user-service:5000/user/{USER_ID}"): _FakeResponse(200, {"email": "fan@example.com"}),
            ("POST", "http://inventory-service:5000/inventory/hold"): _FakeResponse(
                200,
                {"holdID": HOLD_ID, "holdExpiry": "2026-04-04T10:00:00+00:00"},
            ),
            ("PUT", f"http://waitlist-service:5000/waitlist/{WAITLIST_ID}/offer"): _FakeResponse(
                200,
                {"waitlistID": WAITLIST_ID, "status": "HOLD_OFFERED"},
            ),
            ("PUT", f"http://inventory-service:5000/inventory/hold/{HOLD_ID}/release"): _FakeResponse(
                200,
                {"released": True},
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
                "eventID": EVENT_ID,
                "seatCategory": "CAT1",
                "seatID": SEAT_ID,
                "reason": "MANUAL_RELEASE",
            }
        )

        self.assertEqual(len(published), 0)
        self.assertTrue(any(call["url"].endswith(f"/inventory/hold/{HOLD_ID}/release") for call in session.calls))

    def test_process_payload_rejects_non_uuid_payload_fields(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))

        with self.assertRaises(waitlist_promotion.PermanentProcessingError):
            worker.process_payload(
                {
                    "eventID": "not-a-uuid",
                    "seatCategory": "CAT1",
                    "seatID": SEAT_ID,
                    "reason": "MANUAL_RELEASE",
                }
            )

    def test_process_payload_rejects_non_uuid_expired_hold_id_for_timeout(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))

        with self.assertRaises(waitlist_promotion.PermanentProcessingError):
            worker.process_payload(
                {
                    "eventID": EVENT_ID,
                    "seatCategory": "CAT1",
                    "seatID": SEAT_ID,
                    "reason": "PAYMENT_TIMEOUT",
                    "expiredHoldID": "bad-hold-id",
                }
            )

    def test_process_payload_does_not_publish_when_create_hold_reports_no_seat_available(self):
        routes = {
            (
                "GET",
                f"http://waitlist-service:5000/waitlist/next?eventID={EVENT_ID}&seatCategory=CAT1",
            ): _FakeResponse(200, {"waitlistID": WAITLIST_ID, "userID": USER_ID, "status": "WAITING"}),
            ("GET", f"http://user-service:5000/user/{USER_ID}"): _FakeResponse(200, {"email": "fan@example.com"}),
            ("POST", "http://inventory-service:5000/inventory/hold"): _FakeResponse(
                409,
                {"error": "No seat available for hold"},
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
                "eventID": EVENT_ID,
                "seatCategory": "CAT1",
                "seatID": SEAT_ID,
                "reason": "MANUAL_RELEASE",
            }
        )

        self.assertEqual(published, [])
        self.assertFalse(any(call["url"].endswith("/offer") for call in session.calls))

    def test_mark_waitlist_expired_treats_conflict_with_matching_hold_as_idempotent(self):
        routes = {
            ("PUT", f"http://waitlist-service:5000/waitlist/{WAITLIST_ID}/expire"): _FakeResponse(
                409,
                {"error": "Cannot transition"},
            ),
            ("GET", f"http://waitlist-service:5000/waitlist/{WAITLIST_ID}"): _FakeResponse(
                200,
                {"waitlistID": WAITLIST_ID, "status": "EXPIRED", "holdID": HOLD_ID},
            ),
        }
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession(routes))

        expired_entry = worker._mark_waitlist_expired(WAITLIST_ID, HOLD_ID)

        self.assertIsNotNone(expired_entry)
        self.assertEqual(expired_entry["status"], "EXPIRED")
        self.assertEqual(expired_entry["holdID"], HOLD_ID)

    def test_mark_waitlist_offered_returns_false_when_hold_id_mismatches(self):
        routes = {
            ("PUT", f"http://waitlist-service:5000/waitlist/{WAITLIST_ID}/offer"): _FakeResponse(
                200,
                {"waitlistID": WAITLIST_ID, "status": "HOLD_OFFERED", "holdID": OTHER_HOLD_ID},
            )
        }
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession(routes))

        self.assertFalse(worker._mark_waitlist_offered(WAITLIST_ID, HOLD_ID))

    def test_create_hold_raises_for_idempotency_conflict_with_different_user_or_event(self):
        routes = {
            ("POST", "http://inventory-service:5000/inventory/hold"): _FakeResponse(
                409,
                {"error": "idempotencyKey was already used for a different user or event"},
            )
        }
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession(routes))

        with self.assertRaises(waitlist_promotion.PermanentProcessingError):
            worker._create_hold(
                event_id=EVENT_ID,
                seat_category="CAT1",
                seat_id=SEAT_ID,
                user_id=USER_ID,
                waitlist_id=WAITLIST_ID,
            )

    def test_set_seat_available_treats_conflict_as_terminal(self):
        routes = {
            ("PUT", f"http://inventory-service:5000/inventory/seat/{SEAT_ID}/status"): _FakeResponse(
                409,
                {"error": "Seat cannot transition"},
            )
        }
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession(routes))

        worker._set_seat_available(SEAT_ID)

    def test_set_seat_available_raises_permanent_error_for_bad_request(self):
        routes = {
            ("PUT", f"http://inventory-service:5000/inventory/seat/{SEAT_ID}/status"): _FakeResponse(
                400,
                {"error": "Invalid seat status"},
            )
        }
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession(routes))

        with self.assertRaises(waitlist_promotion.PermanentProcessingError):
            worker._set_seat_available(SEAT_ID)

    def test_get_user_email_raises_when_payload_email_is_invalid(self):
        routes = {
            ("GET", f"http://user-service:5000/user/{USER_ID}"): _FakeResponse(
                200,
                {"userID": USER_ID, "email": "invalid-email"},
            )
        }
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession(routes))

        with self.assertRaises(waitlist_promotion.PermanentProcessingError):
            worker._get_user_email(USER_ID)

    def test_get_next_waitlist_entry_sends_internal_auth_header(self):
        routes = {
            (
                "GET",
                f"http://waitlist-service:5000/waitlist/next?eventID={EVENT_ID}&seatCategory=CAT1",
            ): _FakeResponse(404, {"error": "No waiting users"})
        }
        session = _FakeSession(routes)
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=session)

        self.assertIsNone(worker._get_next_waitlist_entry(EVENT_ID, "CAT1"))
        self.assertEqual(session.calls[0]["headers"]["X-Internal-Token"], "ticketblitz-internal-token")

    def test_handle_delivery_retries_transient_error(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))
        fake_channel = _FakeChannel()
        worker._channel = fake_channel

        with patch.object(worker, "process_payload", side_effect=waitlist_promotion.TransientProcessingError("boom")):
            method = _MethodFrame(delivery_tag=7)
            properties = waitlist_promotion.pika.BasicProperties(headers={})
            worker._handle_delivery(
                fake_channel,
                method,
                properties,
                (
                    f'{{"eventID":"{EVENT_ID}","seatCategory":"CAT1",'
                    f'"seatID":"{SEAT_ID}","reason":"MANUAL_RELEASE"}}'
                ).encode("utf-8"),
            )

        self.assertEqual(fake_channel.acked, [7])
        self.assertEqual(fake_channel.nacked, [])
        self.assertEqual(len(fake_channel.published), 1)
        self.assertEqual(
            fake_channel.published[0]["routing_key"],
            "waitlist-promotion-orchestrator.seat.released.retry",
        )

    def test_handle_delivery_requeues_when_retry_enqueue_fails(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))
        fake_channel = _FakeChannel()
        fake_channel.publish_error = RuntimeError("publish failed")
        worker._channel = fake_channel

        with patch.object(worker, "process_payload", side_effect=waitlist_promotion.TransientProcessingError("boom")):
            method = _MethodFrame(delivery_tag=11)
            properties = waitlist_promotion.pika.BasicProperties(headers={})
            worker._handle_delivery(
                fake_channel,
                method,
                properties,
                (
                    f'{{"eventID":"{EVENT_ID}","seatCategory":"CAT1",'
                    f'"seatID":"{SEAT_ID}","reason":"MANUAL_RELEASE"}}'
                ).encode("utf-8"),
            )

        self.assertEqual(fake_channel.acked, [])
        self.assertEqual(fake_channel.nacked, [{"delivery_tag": 11, "requeue": True}])

    def test_handle_delivery_drops_malformed_json(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))
        fake_channel = _FakeChannel()
        method = _MethodFrame(delivery_tag=9)
        properties = waitlist_promotion.pika.BasicProperties(headers={})

        worker._handle_delivery(fake_channel, method, properties, b"not-json")

        self.assertEqual(fake_channel.acked, [9])
        self.assertEqual(fake_channel.published, [])

    def test_handle_delivery_acks_non_object_json_payload(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))
        fake_channel = _FakeChannel()
        method = _MethodFrame(delivery_tag=19)
        properties = waitlist_promotion.pika.BasicProperties(headers={})

        worker._handle_delivery(fake_channel, method, properties, b"[]")

        self.assertEqual(fake_channel.acked, [19])
        self.assertEqual(fake_channel.nacked, [])

    def test_handle_delivery_acks_permanent_processing_error(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))
        fake_channel = _FakeChannel()

        with patch.object(worker, "process_payload", side_effect=waitlist_promotion.PermanentProcessingError("bad")):
            method = _MethodFrame(delivery_tag=21)
            properties = waitlist_promotion.pika.BasicProperties(headers={})
            worker._handle_delivery(
                fake_channel,
                method,
                properties,
                (
                    f'{{"eventID":"{EVENT_ID}","seatCategory":"CAT1",'
                    f'"seatID":"{SEAT_ID}","reason":"MANUAL_RELEASE"}}'
                ).encode("utf-8"),
            )

        self.assertEqual(fake_channel.acked, [21])
        self.assertEqual(fake_channel.nacked, [])

    def test_handle_delivery_drops_after_retry_limit_is_reached(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))
        fake_channel = _FakeChannel()

        with patch.object(worker, "process_payload", side_effect=waitlist_promotion.TransientProcessingError("boom")):
            method = _MethodFrame(delivery_tag=23)
            properties = waitlist_promotion.pika.BasicProperties(
                headers={"x-waitlist-promotion-retry": 3}
            )
            worker._handle_delivery(
                fake_channel,
                method,
                properties,
                (
                    f'{{"eventID":"{EVENT_ID}","seatCategory":"CAT1",'
                    f'"seatID":"{SEAT_ID}","reason":"MANUAL_RELEASE"}}'
                ).encode("utf-8"),
            )

        self.assertEqual(fake_channel.acked, [23])
        self.assertEqual(fake_channel.published, [])
        self.assertEqual(fake_channel.nacked, [])

    def test_handle_delivery_acks_on_unexpected_exception(self):
        worker = waitlist_promotion.WaitlistPromotionWorker(self._config(), session=_FakeSession({}))
        fake_channel = _FakeChannel()

        with patch.object(worker, "process_payload", side_effect=RuntimeError("unexpected")):
            method = _MethodFrame(delivery_tag=25)
            properties = waitlist_promotion.pika.BasicProperties(headers={})
            worker._handle_delivery(
                fake_channel,
                method,
                properties,
                (
                    f'{{"eventID":"{EVENT_ID}","seatCategory":"CAT1",'
                    f'"seatID":"{SEAT_ID}","reason":"MANUAL_RELEASE"}}'
                ).encode("utf-8"),
            )

        self.assertEqual(fake_channel.acked, [25])
        self.assertEqual(fake_channel.nacked, [])


if __name__ == "__main__":
    unittest.main()
