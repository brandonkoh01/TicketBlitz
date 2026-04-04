import os
import sys
import unittest
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

BACKEND_DIR = SERVICE_DIR.parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

import app as reservation_app


class FakeOrchestrator:
    def __init__(self):
        self.reserve_response = {"status": "WAITLISTED", "waitlistID": "00000000-0000-0000-0000-000000000100"}
        self.reserve_confirm_response = {"status": "PAYMENT_PENDING", "holdID": "00000000-0000-0000-0000-000000000200"}
        self.waitlist_confirm_response = {"uiStatus": "WAITLIST_OFFERED"}
        self.raise_error = None

    def reserve(self, payload, correlation_id):
        if self.raise_error:
            raise self.raise_error
        return self.reserve_response

    def reserve_confirm(self, payload, correlation_id):
        if self.raise_error:
            raise self.raise_error
        return self.reserve_confirm_response

    def waitlist_confirm(self, hold_id, correlation_id):
        if self.raise_error:
            raise self.raise_error
        return self.waitlist_confirm_response


class ReservationOrchestratorRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = reservation_app.create_app(
            {
                "TESTING": True,
                "USER_SERVICE_URL": "http://user-service:5000",
                "INVENTORY_SERVICE_URL": "http://inventory-service:5000",
                "PAYMENT_SERVICE_URL": "http://payment-service:5000",
                "WAITLIST_SERVICE_URL": "http://waitlist-service:5000",
                "EVENT_SERVICE_URL": "http://event-service:5000",
                "INTERNAL_SERVICE_TOKEN": "test-internal-token",
                "OUTSYSTEMS_BASE_URL": "",
                "OUTSYSTEMS_API_KEY": "",
                "REQUIRE_AUTHENTICATED_USER_HEADER": True,
            }
        )
        self.fake = FakeOrchestrator()
        self.app.config["ORCHESTRATOR"] = self.fake
        self.client = self.app.test_client()
        self.auth_headers = {"X-User-ID": "00000000-0000-0000-0000-000000000001"}

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_openapi_and_docs(self):
        openapi_response = self.client.get("/openapi.json")
        self.assertEqual(openapi_response.status_code, 200)
        self.assertIn("/reserve", openapi_response.get_json()["paths"])

        docs_response = self.client.get("/docs")
        self.assertEqual(docs_response.status_code, 200)

    def test_reserve_route(self):
        response = self.client.post(
            "/reserve",
            json={
                "userID": "00000000-0000-0000-0000-000000000001",
                "eventID": "10000000-0000-0000-0000-000000000301",
                "seatCategory": "CAT1",
                "qty": 1,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "WAITLISTED")
        self.assertTrue(response.headers.get("X-Correlation-ID"))

    def test_reserve_confirm_route(self):
        response = self.client.post(
            "/reserve/confirm",
            json={
                "holdID": "40000000-0000-0000-0000-000000000001",
                "userID": "00000000-0000-0000-0000-000000000001",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "PAYMENT_PENDING")

    def test_waitlist_confirm_route(self):
        response = self.client.get("/waitlist/confirm/40000000-0000-0000-0000-000000000003")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["uiStatus"], "WAITLIST_OFFERED")

    def test_validation_error_mapping(self):
        self.fake.raise_error = reservation_app.ValidationError("bad payload")
        response = self.client.post(
            "/reserve",
            json={
                "userID": "00000000-0000-0000-0000-000000000001",
                "eventID": "10000000-0000-0000-0000-000000000301",
                "seatCategory": "CAT1",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "bad payload")

    def test_auth_header_required(self):
        response = self.client.post(
            "/reserve",
            json={
                "userID": "00000000-0000-0000-0000-000000000001",
                "eventID": "10000000-0000-0000-0000-000000000301",
                "seatCategory": "CAT1",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Authenticated user header is required")

    def test_auth_header_must_match_payload_user(self):
        response = self.client.post(
            "/reserve",
            json={
                "userID": "00000000-0000-0000-0000-000000000001",
                "eventID": "10000000-0000-0000-0000-000000000301",
                "seatCategory": "CAT1",
            },
            headers={"X-User-ID": "00000000-0000-0000-0000-000000000099"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "userID does not match authenticated user")


class FakeDownstreamClient:
    def __init__(self):
        self.user = {"userID": "00000000-0000-0000-0000-000000000001", "email": "fan@example.com"}
        self.event = None
        self.inventory = {"available": 1, "status": "AVAILABLE"}

    def get_user(self, user_id, correlation_id):
        return self.user

    def get_event(self, event_id, correlation_id):
        return self.event

    def get_inventory(self, event_id, seat_category, correlation_id):
        return self.inventory


class ReservationOrchestratorServiceTestCase(unittest.TestCase):
    def test_reserve_raises_not_found_when_event_missing(self):
        config = type("Config", (), {"HTTP_MAX_RETRIES": 0})
        client = FakeDownstreamClient()
        service = reservation_app.ReservationOrchestrator(config, client)

        with self.assertRaises(reservation_app.NotFoundError):
            service.reserve(
                {
                    "userID": "00000000-0000-0000-0000-000000000001",
                    "eventID": "10000000-0000-0000-0000-000000000301",
                    "seatCategory": "CAT1",
                },
                "20000000-0000-0000-0000-000000000001",
            )


if __name__ == "__main__":
    unittest.main()
