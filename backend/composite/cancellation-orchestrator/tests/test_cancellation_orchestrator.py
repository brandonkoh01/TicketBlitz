import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parents[3]

if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import cancellation_orchestrator

BOOKING_ID = "00000000-0000-0000-0000-000000000111"
USER_ID = "00000000-0000-0000-0000-000000000001"
EVENT_ID = "00000000-0000-0000-0000-000000000301"
OLD_HOLD_ID = "00000000-0000-0000-0000-000000000211"
OLD_TICKET_ID = "00000000-0000-0000-0000-000000000411"
WAITLIST_ID = "00000000-0000-0000-0000-000000000511"
NEXT_USER_ID = "00000000-0000-0000-0000-000000000002"
NEW_HOLD_ID = "00000000-0000-0000-0000-000000000212"
NEW_TICKET_ID = "00000000-0000-0000-0000-000000000412"


class MockResponse:
    def __init__(self, status_code: int, payload=None, text=None):
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
            raise ValueError("No JSON")
        return self._payload


class CancellationOrchestratorTests(unittest.TestCase):
    def _internal_headers(self):
        return {"X-Internal-Token": "internal-token"}

    def _build_client(self, **overrides):
        config = {
            "TESTING": True,
            "PAYMENT_SERVICE_URL": "http://payment-service:5000",
            "INVENTORY_SERVICE_URL": "http://inventory-service:5000",
            "WAITLIST_SERVICE_URL": "http://waitlist-service:5000",
            "USER_SERVICE_URL": "http://user-service:5000",
            "EVENT_SERVICE_URL": "http://event-service:5000",
            "OUTSYSTEMS_BASE_URL": "http://outsystems.local",
            "INTERNAL_SERVICE_TOKEN": "internal-token",
            "INTERNAL_AUTH_HEADER": "X-Internal-Token",
        }
        config.update(overrides)
        app = cancellation_orchestrator.create_app(config)
        return app.test_client()

    def test_health(self):
        client = self._build_client()
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")

    @patch.object(cancellation_orchestrator.requests, "request")
    @patch.object(cancellation_orchestrator, "publish_json")
    def test_policy_denied(self, publish_mock, request_mock):
        def side_effect(method, url, headers=None, json=None, timeout=None):
            if method == "GET" and url.endswith(f"/payments/verify/{BOOKING_ID}"):
                return MockResponse(
                    200,
                    {
                        "bookingID": BOOKING_ID,
                        "holdID": OLD_HOLD_ID,
                        "userID": USER_ID,
                        "eventID": EVENT_ID,
                        "paymentStatus": "SUCCEEDED",
                        "withinPolicy": False,
                    },
                )
            if method == "GET" and url.endswith(f"/eticket/hold/{OLD_HOLD_ID}"):
                return MockResponse(200, {"ticketID": OLD_TICKET_ID})
            if method == "GET" and "/eticket/validate?" in url:
                return MockResponse(200, {"valid": True, "reason": "OK", "status": "VALID"})
            if method == "GET" and url.endswith(f"/user/{USER_ID}"):
                return MockResponse(200, {"userID": USER_ID, "email": "fan@example.com", "name": "Fan"})
            if method == "GET" and url.endswith(f"/event/{EVENT_ID}"):
                return MockResponse(200, {"event_id": EVENT_ID, "name": "Coldplay Live"})
            return MockResponse(500, {"error": "unexpected"})

        request_mock.side_effect = side_effect
        client = self._build_client()

        response = client.post(
            "/orchestrator/cancellation",
            json={"bookingID": BOOKING_ID, "userID": USER_ID},
        )

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["status"], "DENIED")
        self.assertEqual(publish_mock.call_count, 1)
        self.assertEqual(publish_mock.call_args.kwargs["routing_key"], "notification.send")
        self.assertEqual(publish_mock.call_args.kwargs["payload"]["type"], "CANCELLATION_DENIED")

    @patch.object(cancellation_orchestrator.requests, "request")
    @patch.object(cancellation_orchestrator, "publish_json")
    def test_refund_success_no_waitlist(self, publish_mock, request_mock):
        def side_effect(method, url, headers=None, json=None, timeout=None):
            if method == "GET" and url.endswith(f"/payments/verify/{BOOKING_ID}"):
                return MockResponse(
                    200,
                    {
                        "bookingID": BOOKING_ID,
                        "holdID": OLD_HOLD_ID,
                        "userID": USER_ID,
                        "eventID": EVENT_ID,
                        "paymentStatus": "SUCCEEDED",
                        "withinPolicy": True,
                        "eligibleRefundAmount": "144.00",
                    },
                )
            if method == "GET" and url.endswith(f"/eticket/hold/{OLD_HOLD_ID}"):
                return MockResponse(200, {"ticketID": OLD_TICKET_ID})
            if method == "GET" and "/eticket/validate?" in url:
                return MockResponse(200, {"valid": True, "reason": "OK", "status": "VALID"})
            if method == "GET" and url.endswith(f"/user/{USER_ID}"):
                return MockResponse(200, {"userID": USER_ID, "email": "fan@example.com", "name": "Fan"})
            if method == "GET" and url.endswith(f"/event/{EVENT_ID}"):
                return MockResponse(200, {"event_id": EVENT_ID, "name": "Coldplay Live"})
            if method == "PUT" and url.endswith(f"/payments/status/{BOOKING_ID}"):
                return MockResponse(200, {"updated": True})
            if method == "POST" and url.endswith(f"/payments/refund/{BOOKING_ID}"):
                return MockResponse(200, {"status": "success", "refundAmount": "144.00"})
            if method == "PUT" and url.endswith(f"/etickets/status/{OLD_TICKET_ID}"):
                return MockResponse(200, {"ticketID": OLD_TICKET_ID, "newStatus": "CANCELLED"})
            if method == "PUT" and url.endswith(f"/inventory/hold/{OLD_HOLD_ID}/release"):
                return MockResponse(200, {"holdID": OLD_HOLD_ID, "holdStatus": "RELEASED"})
            if method == "GET" and url.endswith(f"/waitlist/status/{OLD_HOLD_ID}"):
                return MockResponse(200, {"hasWaitlist": False, "entries": []})
            return MockResponse(500, {"error": "unexpected"})

        request_mock.side_effect = side_effect
        client = self._build_client()

        response = client.post(
            "/orchestrator/cancellation",
            json={"bookingID": BOOKING_ID, "userID": USER_ID, "reason": "Fan requested cancellation"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "REFUND_COMPLETED")
        self.assertEqual(publish_mock.call_count, 3)

    @patch.object(cancellation_orchestrator.requests, "request")
    @patch.object(cancellation_orchestrator, "publish_json")
    def test_refund_failure_compensation(self, publish_mock, request_mock):
        def side_effect(method, url, headers=None, json=None, timeout=None):
            if method == "GET" and url.endswith(f"/payments/verify/{BOOKING_ID}"):
                return MockResponse(
                    200,
                    {
                        "bookingID": BOOKING_ID,
                        "holdID": OLD_HOLD_ID,
                        "userID": USER_ID,
                        "eventID": EVENT_ID,
                        "paymentStatus": "SUCCEEDED",
                        "withinPolicy": True,
                    },
                )
            if method == "GET" and url.endswith(f"/eticket/hold/{OLD_HOLD_ID}"):
                return MockResponse(200, {"ticketID": OLD_TICKET_ID})
            if method == "GET" and "/eticket/validate?" in url:
                return MockResponse(200, {"valid": True, "reason": "OK", "status": "VALID"})
            if method == "GET" and url.endswith(f"/user/{USER_ID}"):
                return MockResponse(200, {"userID": USER_ID, "email": "fan@example.com", "name": "Fan"})
            if method == "GET" and url.endswith(f"/event/{EVENT_ID}"):
                return MockResponse(200, {"event_id": EVENT_ID, "name": "Coldplay Live"})
            if method == "PUT" and url.endswith(f"/payments/status/{BOOKING_ID}"):
                return MockResponse(200, {"updated": True})
            if method == "POST" and url.endswith(f"/payments/refund/{BOOKING_ID}"):
                return MockResponse(502, {"error": "Refund failed after maximum retry attempts"})
            if method == "PUT" and url.endswith("/payments/status/fail"):
                return MockResponse(200, {"updated": True})
            if method == "PUT" and url.endswith(f"/etickets/status/{OLD_TICKET_ID}"):
                return MockResponse(200, {"ticketID": OLD_TICKET_ID, "newStatus": "CANCELLATION_IN_PROGRESS"})
            return MockResponse(500, {"error": "unexpected"})

        request_mock.side_effect = side_effect
        client = self._build_client()

        response = client.post(
            "/orchestrator/cancellation",
            json={"bookingID": BOOKING_ID, "userID": USER_ID},
        )

        self.assertEqual(response.status_code, 502)
        payload = response.get_json()
        self.assertEqual(payload["status"], "CANCELLATION_IN_PROGRESS")
        published_types = [call.kwargs["payload"]["type"] for call in publish_mock.call_args_list]
        self.assertIn("REFUND_ERROR", published_types)

    @patch.object(cancellation_orchestrator.requests, "request")
    @patch.object(cancellation_orchestrator, "publish_json")
    def test_reallocation_pending_path(self, publish_mock, request_mock):
        def side_effect(method, url, headers=None, json=None, timeout=None):
            if method == "GET" and url.endswith(f"/payments/verify/{BOOKING_ID}"):
                return MockResponse(
                    200,
                    {
                        "bookingID": BOOKING_ID,
                        "holdID": OLD_HOLD_ID,
                        "userID": USER_ID,
                        "eventID": EVENT_ID,
                        "paymentStatus": "SUCCEEDED",
                        "withinPolicy": True,
                        "eligibleRefundAmount": "144.00",
                    },
                )
            if method == "GET" and url.endswith(f"/eticket/hold/{OLD_HOLD_ID}"):
                return MockResponse(200, {"ticketID": OLD_TICKET_ID})
            if method == "GET" and "/eticket/validate?" in url:
                return MockResponse(200, {"valid": True, "reason": "OK", "status": "VALID"})
            if method == "GET" and url.endswith(f"/user/{USER_ID}"):
                return MockResponse(200, {"userID": USER_ID, "email": "fan@example.com", "name": "Fan"})
            if method == "GET" and url.endswith(f"/user/{NEXT_USER_ID}"):
                return MockResponse(200, {"userID": NEXT_USER_ID, "email": "next@example.com", "name": "Next"})
            if method == "GET" and url.endswith(f"/event/{EVENT_ID}"):
                return MockResponse(200, {"event_id": EVENT_ID, "name": "Coldplay Live"})
            if method == "PUT" and url.endswith(f"/payments/status/{BOOKING_ID}"):
                return MockResponse(200, {"updated": True})
            if method == "POST" and url.endswith(f"/payments/refund/{BOOKING_ID}"):
                return MockResponse(200, {"status": "success", "refundAmount": "144.00"})
            if method == "PUT" and url.endswith(f"/etickets/status/{OLD_TICKET_ID}"):
                return MockResponse(200, {"ticketID": OLD_TICKET_ID, "newStatus": "CANCELLED"})
            if method == "PUT" and url.endswith(f"/inventory/hold/{OLD_HOLD_ID}/release"):
                return MockResponse(200, {"holdID": OLD_HOLD_ID, "holdStatus": "RELEASED"})
            if method == "GET" and url.endswith(f"/waitlist/status/{OLD_HOLD_ID}"):
                return MockResponse(
                    200,
                    {
                        "hasWaitlist": True,
                        "seatCategory": "CAT1",
                        "nextUser": {
                            "waitlistID": WAITLIST_ID,
                            "userID": NEXT_USER_ID,
                            "seatCategory": "CAT1",
                        },
                        "entries": [],
                    },
                )
            if method == "POST" and url.endswith("/inventory/hold"):
                return MockResponse(
                    201,
                    {
                        "holdID": NEW_HOLD_ID,
                        "holdExpiry": "2026-04-08T10:00:00+00:00",
                        "amount": "160.00",
                        "currency": "SGD",
                    },
                )
            if method == "PUT" and url.endswith(f"/waitlist/{WAITLIST_ID}/offer"):
                return MockResponse(200, {"waitlistID": WAITLIST_ID, "status": "HOLD_OFFERED", "holdID": NEW_HOLD_ID})
            if method == "POST" and url.endswith("/payments/create"):
                return MockResponse(
                    201,
                    {
                        "paymentIntentID": "pi_new",
                        "clientSecret": "secret_new",
                        "amount": "160.00",
                        "currency": "SGD",
                    },
                )
            return MockResponse(500, {"error": "unexpected"})

        request_mock.side_effect = side_effect
        client = self._build_client()

        response = client.post(
            "/orchestrator/cancellation",
            json={"bookingID": BOOKING_ID, "userID": USER_ID},
        )

        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertEqual(payload["status"], "REALLOCATION_PENDING")
        self.assertEqual(payload["waitlistID"], WAITLIST_ID)
        published_types = [call.kwargs["payload"]["type"] for call in publish_mock.call_args_list]
        self.assertIn("SEAT_AVAILABLE", published_types)

    @patch.object(cancellation_orchestrator.requests, "request")
    @patch.object(cancellation_orchestrator, "publish_json")
    def test_confirm_reallocation(self, publish_mock, request_mock):
        def side_effect(method, url, headers=None, json=None, timeout=None):
            if method == "GET" and url.endswith(f"/waitlist/{WAITLIST_ID}"):
                return MockResponse(
                    200,
                    {
                        "waitlistID": WAITLIST_ID,
                        "userID": NEXT_USER_ID,
                        "holdID": NEW_HOLD_ID,
                        "status": "HOLD_OFFERED",
                    },
                )
            if method == "GET" and url.endswith(f"/payment/hold/{NEW_HOLD_ID}"):
                return MockResponse(200, {"paymentStatus": "SUCCEEDED", "transactionID": BOOKING_ID})
            if method == "PUT" and url.endswith(f"/inventory/hold/{NEW_HOLD_ID}/confirm"):
                return MockResponse(200, {"holdID": NEW_HOLD_ID, "holdStatus": "CONFIRMED"})
            if method == "PUT" and url.endswith(f"/waitlist/{WAITLIST_ID}/confirm"):
                return MockResponse(200, {"waitlistID": WAITLIST_ID, "status": "CONFIRMED", "holdID": NEW_HOLD_ID})
            if method == "GET" and url.endswith(f"/payments/verify/{BOOKING_ID}"):
                return MockResponse(200, {"holdID": OLD_HOLD_ID, "eventID": EVENT_ID, "userID": USER_ID, "withinPolicy": True})
            if method == "GET" and url.endswith(f"/eticket/hold/{OLD_HOLD_ID}"):
                return MockResponse(200, {"ticketID": OLD_TICKET_ID})
            if method == "GET" and url.endswith(f"/inventory/hold/{NEW_HOLD_ID}"):
                return MockResponse(200, {"holdID": NEW_HOLD_ID, "seatID": "00000000-0000-0000-0000-000000000888", "seatNumber": "D12"})
            if method == "POST" and url.endswith("/etickets/update"):
                return MockResponse(200, {"operation": "TRANSFER_AND_REISSUE", "newTicketID": NEW_TICKET_ID})
            if method == "GET" and url.endswith(f"/user/{NEXT_USER_ID}"):
                return MockResponse(200, {"userID": NEXT_USER_ID, "email": "next@example.com"})
            if method == "GET" and url.endswith(f"/event/{EVENT_ID}"):
                return MockResponse(200, {"event_id": EVENT_ID, "name": "Coldplay Live"})
            return MockResponse(500, {"error": "unexpected"})

        request_mock.side_effect = side_effect
        client = self._build_client()

        response = client.post(
            "/orchestrator/cancellation/reallocation/confirm",
            json={
                "bookingID": BOOKING_ID,
                "newHoldID": NEW_HOLD_ID,
                "waitlistID": WAITLIST_ID,
                "newUserID": NEXT_USER_ID,
            },
            headers=self._internal_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "REALLOCATION_CONFIRMED")
        self.assertEqual(payload["ticketID"], NEW_TICKET_ID)
        self.assertEqual(publish_mock.call_count, 1)
        self.assertEqual(publish_mock.call_args.kwargs["payload"]["type"], "TICKET_CONFIRMATION")

    def test_confirm_reallocation_requires_internal_auth(self):
        client = self._build_client()

        response = client.post(
            "/orchestrator/cancellation/reallocation/confirm",
            json={
                "bookingID": BOOKING_ID,
                "newHoldID": NEW_HOLD_ID,
                "waitlistID": WAITLIST_ID,
            },
        )

        self.assertEqual(response.status_code, 401)
        payload = response.get_json()
        self.assertEqual(payload["error"], "Unauthorized")

    @patch.object(cancellation_orchestrator.requests, "request")
    @patch.object(cancellation_orchestrator, "publish_json")
    def test_confirm_reallocation_rejects_mismatched_new_user(self, publish_mock, request_mock):
        def side_effect(method, url, headers=None, json=None, timeout=None):
            if method == "GET" and url.endswith(f"/waitlist/{WAITLIST_ID}"):
                return MockResponse(
                    200,
                    {
                        "waitlistID": WAITLIST_ID,
                        "userID": NEXT_USER_ID,
                        "holdID": NEW_HOLD_ID,
                        "status": "HOLD_OFFERED",
                    },
                )
            return MockResponse(500, {"error": "unexpected"})

        request_mock.side_effect = side_effect
        client = self._build_client()

        response = client.post(
            "/orchestrator/cancellation/reallocation/confirm",
            json={
                "bookingID": BOOKING_ID,
                "newHoldID": NEW_HOLD_ID,
                "waitlistID": WAITLIST_ID,
                "newUserID": USER_ID,
            },
            headers=self._internal_headers(),
        )

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertIn("newUserID does not match", payload["error"])
        self.assertEqual(publish_mock.call_count, 0)

    @patch.object(cancellation_orchestrator.requests, "request")
    @patch.object(cancellation_orchestrator, "publish_json")
    def test_confirm_reallocation_transfer_failure_requires_reconciliation(self, publish_mock, request_mock):
        def side_effect(method, url, headers=None, json=None, timeout=None):
            if method == "GET" and url.endswith(f"/waitlist/{WAITLIST_ID}"):
                return MockResponse(
                    200,
                    {
                        "waitlistID": WAITLIST_ID,
                        "userID": NEXT_USER_ID,
                        "holdID": NEW_HOLD_ID,
                        "status": "HOLD_OFFERED",
                    },
                )
            if method == "GET" and url.endswith(f"/payment/hold/{NEW_HOLD_ID}"):
                return MockResponse(200, {"paymentStatus": "SUCCEEDED", "transactionID": BOOKING_ID})
            if method == "PUT" and url.endswith(f"/inventory/hold/{NEW_HOLD_ID}/confirm"):
                return MockResponse(200, {"holdID": NEW_HOLD_ID, "holdStatus": "CONFIRMED"})
            if method == "GET" and url.endswith(f"/payments/verify/{BOOKING_ID}"):
                return MockResponse(200, {"holdID": OLD_HOLD_ID, "eventID": EVENT_ID, "userID": USER_ID, "withinPolicy": True})
            if method == "GET" and url.endswith(f"/eticket/hold/{OLD_HOLD_ID}"):
                return MockResponse(200, {"ticketID": OLD_TICKET_ID})
            if method == "GET" and url.endswith(f"/inventory/hold/{NEW_HOLD_ID}"):
                return MockResponse(200, {"holdID": NEW_HOLD_ID, "seatID": "00000000-0000-0000-0000-000000000888", "seatNumber": "D12"})
            if method == "POST" and url.endswith("/etickets/update"):
                return MockResponse(502, {"error": "outsystems unavailable"})
            return MockResponse(500, {"error": "unexpected"})

        request_mock.side_effect = side_effect
        client = self._build_client()

        response = client.post(
            "/orchestrator/cancellation/reallocation/confirm",
            json={
                "bookingID": BOOKING_ID,
                "newHoldID": NEW_HOLD_ID,
                "waitlistID": WAITLIST_ID,
                "newUserID": NEXT_USER_ID,
            },
            headers=self._internal_headers(),
        )

        self.assertEqual(response.status_code, 502)
        payload = response.get_json()
        self.assertEqual(payload["status"], "REALLOCATION_RECONCILIATION_REQUIRED")
        self.assertEqual(publish_mock.call_count, 0)


if __name__ == "__main__":
    unittest.main()
