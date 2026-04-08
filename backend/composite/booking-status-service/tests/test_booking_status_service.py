import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import booking_status


VALID_HOLD_ID = "00000000-0000-0000-0000-000000000101"


class MockResponse:
    def __init__(self, status_code, payload=None, text=None):
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


class BookingStatusServiceTestCase(unittest.TestCase):
    def _build_client(self, **overrides):
        config = {
            "TESTING": True,
            "INVENTORY_SERVICE_URL": "http://inventory-service:5000",
            "PAYMENT_SERVICE_URL": "http://payment-service:5000",
            "OUTSYSTEMS_BASE_URL": "http://outsystems.local",
            "INTERNAL_SERVICE_TOKEN": "",
        }
        config.update(overrides)
        app = booking_status.create_app(config)
        return app.test_client()

    def _dispatch(self, url, *_args, **_kwargs):
        if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
            return MockResponse(
                200,
                {
                    "holdID": VALID_HOLD_ID,
                    "holdStatus": "HELD",
                    "seatNumber": "A-10",
                    "amount": 120.0,
                    "currency": "SGD",
                    "holdExpiry": "2026-04-04T10:10:00+00:00",
                    "confirmedAt": None,
                    "expiredAt": None,
                    "releasedAt": None,
                    "fromWaitlist": False,
                },
            )

        if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
            return MockResponse(404, {"error": "No transaction found for hold"})

        if url.endswith(f"/eticket/hold/{VALID_HOLD_ID}"):
            return MockResponse(404, {"error": "Ticket not found"})

        return MockResponse(404, {"error": "not found"})

    def test_health(self):
        client = self._build_client()
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("inventoryConfigured", payload["dependencies"])
        self.assertIn("paymentConfigured", payload["dependencies"])

    def test_openapi_and_docs(self):
        client = self._build_client()

        openapi_response = client.get("/openapi.json")
        self.assertEqual(openapi_response.status_code, 200)
        self.assertIn("/booking-status/{hold_id}", openapi_response.get_json()["paths"])

        docs_response = client.get("/docs")
        self.assertEqual(docs_response.status_code, 200)
        self.assertIn("SwaggerUIBundle", docs_response.get_data(as_text=True))
        hold_param = openapi_response.get_json()["paths"]["/booking-status/{hold_id}"]["get"]["parameters"][0]
        self.assertTrue(hold_param["required"])
        self.assertEqual(hold_param["schema"]["format"], "uuid")

    @patch.object(booking_status.requests, "get")
    def test_invalid_hold_id_returns_400(self, _mock_get):
        client = self._build_client()
        response = client.get("/booking-status/not-a-uuid")
        self.assertEqual(response.status_code, 400)
        self.assertIn("holdID must be a valid UUID", response.get_json()["error"])

    @patch.object(booking_status.requests, "get")
    def test_missing_hold_returns_404(self, mock_get):
        mock_get.return_value = MockResponse(404, {"error": "Hold not found"})
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 404)

    @patch.object(booking_status.requests, "get")
    def test_expired_hold_returns_expired_status(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(
                    200,
                    {
                        "holdID": VALID_HOLD_ID,
                        "holdStatus": "EXPIRED",
                        "seatNumber": "A-10",
                        "amount": 120.0,
                        "currency": "SGD",
                        "holdExpiry": "2026-04-04T10:10:00+00:00",
                        "expiredAt": "2026-04-04T10:15:00+00:00",
                    },
                )
            return MockResponse(500, {"error": "unexpected"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "EXPIRED")

    @patch.object(booking_status.requests, "get")
    def test_released_non_timeout_hold_stays_processing(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(
                    200,
                    {
                        "holdID": VALID_HOLD_ID,
                        "holdStatus": "RELEASED",
                        "releaseReason": "CANCELLATION",
                        "seatNumber": "A-10",
                        "amount": 120.0,
                        "currency": "SGD",
                        "releasedAt": "2026-04-04T10:15:00+00:00",
                    },
                )
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(404, {"error": "No transaction found for hold"})
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "PROCESSING")

    @patch.object(booking_status.requests, "get")
    def test_reconcile_payment_query_is_forwarded_to_payment_service(self, mock_get):
        called_urls = []

        def side_effect(url, *_args, **_kwargs):
            called_urls.append(url)

            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "HELD", "seatNumber": "A-10"})

            if f"/payment/hold/{VALID_HOLD_ID}" in url:
                return MockResponse(404, {"error": "No transaction found for hold"})

            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}?reconcilePayment=true")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(f"/payment/hold/{VALID_HOLD_ID}?reconcile=true" in url for url in called_urls))

    @patch.object(booking_status.requests, "get")
    def test_released_timeout_hold_returns_expired(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(
                    200,
                    {
                        "holdID": VALID_HOLD_ID,
                        "holdStatus": "RELEASED",
                        "releaseReason": "PAYMENT_TIMEOUT",
                        "seatNumber": "A-10",
                        "amount": 120.0,
                        "currency": "SGD",
                        "expiredAt": "2026-04-04T10:15:00+00:00",
                        "releasedAt": "2026-04-04T10:15:00+00:00",
                    },
                )
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "EXPIRED")

    @patch.object(booking_status.requests, "get")
    def test_failed_payment_returns_failed_payment_status(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "HELD", "seatNumber": "A-10"})
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(
                    200,
                    {
                        "holdID": VALID_HOLD_ID,
                        "paymentStatus": "FAILED",
                        "failureReason": "payment_intent.payment_failed",
                    },
                )
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "FAILED_PAYMENT")
        self.assertEqual(payload["paymentStatus"], "FAILED")

    @patch.object(booking_status.requests, "get")
    def test_confirmed_requires_ticket(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "CONFIRMED", "seatNumber": "A-10"})
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(
                    200,
                    {
                        "holdID": VALID_HOLD_ID,
                        "paymentStatus": "SUCCEEDED",
                        "transactionID": "00000000-0000-0000-0000-000000000202",
                    },
                )
            if url.endswith(f"/eticket/hold/{VALID_HOLD_ID}"):
                return MockResponse(
                    200,
                    {
                        "ticketID": "00000000-0000-0000-0000-000000000303",
                        "status": "VALID",
                        "seatNumber": "A-10",
                        "issuedAt": "2026-04-04T10:20:00+00:00",
                    },
                )
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "CONFIRMED")
        self.assertEqual(payload["ticketID"], "00000000-0000-0000-0000-000000000303")

    @patch.object(booking_status.requests, "get")
    def test_processing_when_ticket_not_ready(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "CONFIRMED", "seatNumber": "A-10"})
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "paymentStatus": "SUCCEEDED"})
            if url.endswith(f"/eticket/hold/{VALID_HOLD_ID}"):
                return MockResponse(404, {"error": "Ticket not found"})
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "PROCESSING")
        self.assertEqual(payload["dependencyStatus"]["eticket"], "not_found")

    @patch.object(booking_status.requests, "get")
    def test_inventory_dependency_failure_returns_503(self, mock_get):
        mock_get.return_value = MockResponse(500, {"error": "db down"})
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 503)
        payload = response.get_json()
        self.assertEqual(payload["details"], {"dependency": "inventory-service"})

    @patch.object(booking_status.requests, "get")
    def test_payment_dependency_failure_returns_503(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "HELD", "seatNumber": "A-10"})
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(500, {"error": "payment down"})
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 503)

    @patch.object(booking_status.requests, "get")
    def test_default_processing_when_payment_not_found(self, mock_get):
        mock_get.side_effect = self._dispatch
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "PROCESSING")
        self.assertEqual(payload["dependencyStatus"]["payment"], "not_found")

    @patch.object(booking_status.requests, "get")
    def test_should_forward_internal_auth_header_when_token_is_configured(self, mock_get):
        captured = []

        def side_effect(url, *_args, **kwargs):
            captured.append((url, kwargs.get("headers") or {}))
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "HELD", "seatNumber": "A-10"})
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(404, {"error": "No transaction found for hold"})
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client(INTERNAL_SERVICE_TOKEN="secret-token", INTERNAL_AUTH_HEADER="X-Test-Token")

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(captured), 2)
        self.assertEqual(captured[0][1].get("X-Test-Token"), "secret-token")
        self.assertEqual(captured[1][1].get("X-Test-Token"), "secret-token")

    @patch.object(booking_status.requests, "get")
    def test_should_skip_payment_lookup_when_hold_is_terminal_expired(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "EXPIRED", "expiredAt": "2026-04-04T10:15:00+00:00"})
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                self.fail("Payment endpoint should not be called for terminal expired hold")
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "EXPIRED")
        self.assertEqual(payload["dependencyStatus"]["payment"], "skipped")

    @patch.object(booking_status.requests, "get")
    def test_should_return_processing_when_outsystems_is_disabled(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "CONFIRMED", "seatNumber": "A-10"})
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "paymentStatus": "SUCCEEDED"})
            if url.endswith(f"/eticket/hold/{VALID_HOLD_ID}"):
                self.fail("OutSystems endpoint should not be called when OUTSYSTEMS_BASE_URL is empty")
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client(OUTSYSTEMS_BASE_URL="")

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "PROCESSING")
        self.assertEqual(payload["dependencyStatus"]["eticket"], "disabled")

    @patch.object(booking_status.requests, "get")
    def test_should_return_processing_when_outsystems_is_unavailable(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "CONFIRMED", "seatNumber": "A-10"})
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "paymentStatus": "SUCCEEDED"})
            if url.endswith(f"/eticket/hold/{VALID_HOLD_ID}"):
                return MockResponse(503, {"error": "down"})
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "PROCESSING")
        self.assertEqual(payload["dependencyStatus"]["eticket"], "unavailable")

    @patch.object(booking_status.requests, "get")
    def test_should_allow_confirmed_without_ticket_when_flag_enabled(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "holdStatus": "CONFIRMED", "seatNumber": "A-10"})
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(200, {"holdID": VALID_HOLD_ID, "paymentStatus": "SUCCEEDED"})
            if url.endswith(f"/eticket/hold/{VALID_HOLD_ID}"):
                return MockResponse(404, {"error": "Ticket not found"})
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client(ALLOW_CONFIRMED_WITHOUT_TICKET=True)

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["uiStatus"], "CONFIRMED")
        self.assertEqual(payload["dependencyStatus"]["eticket"], "not_found")

    @patch.object(booking_status.requests, "get")
    def test_should_sanitize_details_when_dependency_request_raises_exception(self, mock_get):
        mock_get.side_effect = booking_status.requests.Timeout("inventory timeout")
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 503)
        payload = response.get_json()
        self.assertEqual(payload["details"], {"dependency": "upstream"})

    @patch.object(booking_status.requests, "get")
    def test_should_use_latest_timestamp_for_updated_at(self, mock_get):
        def side_effect(url, *_args, **_kwargs):
            if url.endswith(f"/inventory/hold/{VALID_HOLD_ID}"):
                return MockResponse(
                    200,
                    {
                        "holdID": VALID_HOLD_ID,
                        "holdStatus": "HELD",
                        "holdExpiry": "2026-04-04T10:00:00+00:00",
                        "releasedAt": "2026-04-04T10:01:00+00:00",
                    },
                )
            if url.endswith(f"/payment/hold/{VALID_HOLD_ID}"):
                return MockResponse(
                    200,
                    {
                        "holdID": VALID_HOLD_ID,
                        "paymentStatus": "FAILED",
                        "createdAt": "2026-04-04T10:02:00+00:00",
                        "updatedAt": "2026-04-04T10:03:00+00:00",
                    },
                )
            return MockResponse(404, {"error": "not found"})

        mock_get.side_effect = side_effect
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["updatedAt"], "2026-04-04T10:03:00+00:00")

    @patch.object(booking_status, "_fetch_inventory_hold")
    def test_should_return_500_when_unexpected_exception_occurs(self, mock_fetch_inventory):
        mock_fetch_inventory.side_effect = RuntimeError("unexpected")
        client = self._build_client()

        response = client.get(f"/booking-status/{VALID_HOLD_ID}")
        self.assertEqual(response.status_code, 500)
        payload = response.get_json()
        self.assertEqual(payload["error"], "Failed to resolve booking status")

    def test_env_float_fallbacks(self):
        self.assertEqual(booking_status._env_float("DOES_NOT_EXIST", 3.0), 3.0)
        with patch.object(booking_status.os, "getenv", return_value="invalid"):
            self.assertEqual(booking_status._env_float("BOOKING_STATUS_TIMEOUT_SECONDS", 3.0), 3.0)
        with patch.object(booking_status.os, "getenv", return_value="0"):
            self.assertEqual(booking_status._env_float("BOOKING_STATUS_TIMEOUT_SECONDS", 3.0), 3.0)


if __name__ == "__main__":
    unittest.main()
