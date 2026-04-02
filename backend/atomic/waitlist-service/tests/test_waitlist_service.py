import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SERVICE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parents[3]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import waitlist as waitlist_service


WAITLIST_ID = "60000000-0000-0000-0000-000000000001"
HOLD_ID = "40000000-0000-0000-0000-000000000002"
EVENT_ID = "10000000-0000-0000-0000-000000000301"
USER_ID = "00000000-0000-0000-0000-000000000001"
CATEGORY_ID = "20000000-0000-0000-0000-000000000101"
AUTH_HEADER_NAME = "X-Internal-Token"
AUTH_TOKEN = "test-internal-token"


def _entry(status="WAITING"):
    return {
        "waitlist_id": WAITLIST_ID,
        "event_id": EVENT_ID,
        "category_id": CATEGORY_ID,
        "user_id": USER_ID,
        "hold_id": HOLD_ID if status != "WAITING" else None,
        "status": status,
        "joined_at": "2026-03-18T07:07:00+00:00",
        "offered_at": "2026-03-18T07:20:00+00:00" if status in {"HOLD_OFFERED", "CONFIRMED", "EXPIRED"} else None,
        "confirmed_at": "2026-03-18T07:24:00+00:00" if status == "CONFIRMED" else None,
        "expired_at": "2026-03-18T07:31:00+00:00" if status == "EXPIRED" else None,
        "priority_score": 10,
        "source": "PUBLIC",
        "metadata": {},
        "created_at": "2026-03-18T07:07:00+00:00",
        "updated_at": "2026-03-18T07:07:00+00:00",
    }


class FakePostgrestAPIError(Exception):
    def __init__(self, payload):
        super().__init__(str(payload))
        self.code = payload.get("code")
        self.message = payload.get("message")
        self.details = payload.get("details")
        self.hint = payload.get("hint")


class WaitlistServiceTestCase(unittest.TestCase):
    def _build_client(self, repo):
        app = waitlist_service.create_app(
            {
                "TESTING": True,
                "WAITLIST_REPOSITORY": repo,
                "INTERNAL_AUTH_HEADER": AUTH_HEADER_NAME,
                "INTERNAL_SERVICE_TOKEN": AUTH_TOKEN,
                "REQUIRE_INTERNAL_AUTH": True,
            }
        )
        return app.test_client()

    def _auth_headers(self):
        return {AUTH_HEADER_NAME: AUTH_TOKEN}

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_health_endpoint_is_public(self, _mock_db_configured):
        client = self._build_client(Mock())

        response = client.get("/health")
        self.assertEqual(response.status_code, 200)

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_openapi_endpoint_is_public(self, _mock_db_configured):
        client = self._build_client(Mock())

        response = client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["openapi"], "3.0.3")
        self.assertEqual(payload["info"]["title"], "TicketBlitz Waitlist Service API")
        self.assertIn("/waitlist/join", payload["paths"])
        self.assertEqual(
            payload["components"]["securitySchemes"]["InternalToken"]["name"],
            AUTH_HEADER_NAME,
        )

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_swagger_docs_endpoint_is_public(self, _mock_db_configured):
        client = self._build_client(Mock())

        response = client.get("/docs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        self.assertIn("SwaggerUIBundle", response.get_data(as_text=True))
        self.assertIn("/openapi.json", response.get_data(as_text=True))

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_mutating_routes_require_auth(self, _mock_db_configured):
        client = self._build_client(Mock())

        response = client.post(
            "/waitlist/join",
            json={"userID": USER_ID, "eventID": EVENT_ID, "seatCategory": "CAT1"},
        )
        self.assertEqual(response.status_code, 401)

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_sensitive_read_routes_require_auth(self, _mock_db_configured):
        client = self._build_client(Mock())

        response = client.get("/waitlist")
        self.assertEqual(response.status_code, 401)

        response = client.get(f"/waitlist/next?eventID={EVENT_ID}&seatCategory=CAT1")
        self.assertEqual(response.status_code, 401)

        response = client.get(f"/waitlist/by-hold/{HOLD_ID}")
        self.assertEqual(response.status_code, 401)

        response = client.get(f"/waitlist/status/{HOLD_ID}")
        self.assertEqual(response.status_code, 401)

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_join_waitlist_returns_expected_contract(self, _mock_db_configured):
        repo = Mock()
        repo.resolve_category.return_value = {
            "category_id": CATEGORY_ID,
            "event_id": EVENT_ID,
            "category_code": "CAT1",
            "name": "Category 1",
        }
        repo.join_waitlist.return_value = _entry(status="WAITING")
        repo.get_positions.return_value = {WAITLIST_ID: 3}
        repo.get_category_map.return_value = {
            CATEGORY_ID: {
                "category_id": CATEGORY_ID,
                "event_id": EVENT_ID,
                "category_code": "CAT1",
                "name": "Category 1",
            }
        }

        client = self._build_client(repo)
        response = client.post(
            "/waitlist/join",
            headers=self._auth_headers(),
            json={"userID": USER_ID, "eventID": EVENT_ID, "seatCategory": "CAT1", "qty": 1},
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["waitlistID"], WAITLIST_ID)
        self.assertEqual(payload["position"], 3)
        self.assertEqual(payload["status"], "WAITING")

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_join_waitlist_maps_unique_violation_to_409(self, _mock_db_configured):
        repo = Mock()
        repo.resolve_category.return_value = {
            "category_id": CATEGORY_ID,
            "event_id": EVENT_ID,
            "category_code": "CAT1",
            "name": "Category 1",
        }
        repo.join_waitlist.side_effect = FakePostgrestAPIError(
            {
                "code": "23505",
                "message": "duplicate key value violates unique constraint",
                "details": "Key (event_id, category_id, user_id) already exists.",
            }
        )

        client = self._build_client(repo)
        with patch.object(waitlist_service, "APIError", FakePostgrestAPIError):
            response = client.post(
                "/waitlist/join",
                headers=self._auth_headers(),
                json={"userID": USER_ID, "eventID": EVENT_ID, "seatCategory": "CAT1", "qty": 1},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("already on the waitlist", response.get_json()["error"])

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_list_waitlist_rejects_seat_category_without_event(self, _mock_db_configured):
        client = self._build_client(Mock())

        response = client.get("/waitlist?seatCategory=CAT1", headers=self._auth_headers())
        self.assertEqual(response.status_code, 400)
        self.assertIn("eventID is required", response.get_json()["error"])

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_get_waitlist_by_id_returns_position(self, _mock_db_configured):
        repo = Mock()
        repo.get_entry.return_value = _entry(status="WAITING")
        repo.get_positions.return_value = {WAITLIST_ID: 1}
        repo.get_category_map.return_value = {
            CATEGORY_ID: {
                "category_id": CATEGORY_ID,
                "event_id": EVENT_ID,
                "category_code": "CAT1",
                "name": "Category 1",
            }
        }

        client = self._build_client(repo)
        response = client.get(f"/waitlist/{WAITLIST_ID}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["waitlistID"], WAITLIST_ID)
        self.assertEqual(payload["position"], 1)
        self.assertNotIn("email", payload)
        repo.get_user_email_map.assert_not_called()

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_get_waitlist_by_id_include_email_requires_auth(self, _mock_db_configured):
        repo = Mock()
        repo.get_entry.return_value = _entry(status="WAITING")
        repo.get_positions.return_value = {WAITLIST_ID: 1}
        repo.get_category_map.return_value = {
            CATEGORY_ID: {
                "category_id": CATEGORY_ID,
                "event_id": EVENT_ID,
                "category_code": "CAT1",
                "name": "Category 1",
            }
        }

        client = self._build_client(repo)
        response = client.get(f"/waitlist/{WAITLIST_ID}?includeEmail=true")
        self.assertEqual(response.status_code, 401)

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_get_next_waitlist_requires_params(self, _mock_db_configured):
        client = self._build_client(Mock())

        response = client.get("/waitlist/next", headers=self._auth_headers())
        self.assertEqual(response.status_code, 400)
        self.assertIn("eventID is required", response.get_json()["error"])

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_get_next_waitlist_returns_not_found_when_empty(self, _mock_db_configured):
        repo = Mock()
        repo.resolve_category.return_value = {
            "category_id": CATEGORY_ID,
            "event_id": EVENT_ID,
            "category_code": "CAT1",
            "name": "Category 1",
        }
        repo.get_next_waiting.return_value = None

        client = self._build_client(repo)
        response = client.get(
            f"/waitlist/next?eventID={EVENT_ID}&seatCategory=CAT1",
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 404)

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_offer_waitlist_rejects_invalid_transition(self, _mock_db_configured):
        repo = Mock()
        repo.get_entry.return_value = _entry(status="CONFIRMED")

        client = self._build_client(repo)
        response = client.put(
            f"/waitlist/{WAITLIST_ID}/offer",
            headers=self._auth_headers(),
            json={"holdID": HOLD_ID},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("Cannot transition", response.get_json()["error"])

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_offer_waitlist_succeeds(self, _mock_db_configured):
        repo = Mock()
        repo.get_entry.return_value = _entry(status="WAITING")
        repo.update_entry_if_status.return_value = _entry(status="HOLD_OFFERED")
        repo.get_positions.return_value = {}
        repo.get_category_map.return_value = {
            CATEGORY_ID: {
                "category_id": CATEGORY_ID,
                "event_id": EVENT_ID,
                "category_code": "CAT1",
                "name": "Category 1",
            }
        }

        client = self._build_client(repo)
        response = client.put(
            f"/waitlist/{WAITLIST_ID}/offer",
            headers=self._auth_headers(),
            json={"holdID": HOLD_ID},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "HOLD_OFFERED")

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_confirm_waitlist_succeeds(self, _mock_db_configured):
        repo = Mock()
        repo.get_entry.return_value = _entry(status="HOLD_OFFERED")
        repo.update_entry_if_status.return_value = _entry(status="CONFIRMED")
        repo.get_positions.return_value = {}
        repo.get_category_map.return_value = {
            CATEGORY_ID: {
                "category_id": CATEGORY_ID,
                "event_id": EVENT_ID,
                "category_code": "CAT1",
                "name": "Category 1",
            }
        }

        client = self._build_client(repo)
        response = client.put(
            f"/waitlist/{WAITLIST_ID}/confirm",
            headers=self._auth_headers(),
            json={"holdID": HOLD_ID},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "CONFIRMED")

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_expire_waitlist_succeeds(self, _mock_db_configured):
        repo = Mock()
        repo.get_entry.return_value = _entry(status="HOLD_OFFERED")
        repo.update_entry_if_status.return_value = _entry(status="EXPIRED")
        repo.get_positions.return_value = {}
        repo.get_category_map.return_value = {
            CATEGORY_ID: {
                "category_id": CATEGORY_ID,
                "event_id": EVENT_ID,
                "category_code": "CAT1",
                "name": "Category 1",
            }
        }

        client = self._build_client(repo)
        response = client.put(
            f"/waitlist/{WAITLIST_ID}/expire",
            headers=self._auth_headers(),
            json={"holdID": HOLD_ID},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "EXPIRED")

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_confirm_waitlist_rejects_hold_mismatch(self, _mock_db_configured):
        repo = Mock()
        repo.get_entry.return_value = _entry(status="HOLD_OFFERED")

        client = self._build_client(repo)
        response = client.put(
            f"/waitlist/{WAITLIST_ID}/confirm",
            headers=self._auth_headers(),
            json={"holdID": "50000000-0000-0000-0000-000000000003"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("holdID does not match", response.get_json()["error"])

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_offer_waitlist_detects_concurrent_update_conflict(self, _mock_db_configured):
        repo = Mock()
        repo.get_entry.side_effect = [
            _entry(status="WAITING"),
            _entry(status="CONFIRMED"),
        ]
        repo.update_entry_if_status.return_value = None

        client = self._build_client(repo)
        response = client.put(
            f"/waitlist/{WAITLIST_ID}/offer",
            headers=self._auth_headers(),
            json={"holdID": HOLD_ID},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("concurrent update", response.get_json()["error"])

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_waitlist_status_by_hold_returns_next_user(self, _mock_db_configured):
        repo = Mock()
        repo.get_hold_context.return_value = {
            "hold_id": HOLD_ID,
            "event_id": EVENT_ID,
            "category_id": CATEGORY_ID,
        }
        repo.get_waiting_for_context.return_value = [_entry(status="WAITING")]
        repo.get_positions.return_value = {WAITLIST_ID: 1}
        repo.get_category_map.return_value = {
            CATEGORY_ID: {
                "category_id": CATEGORY_ID,
                "event_id": EVENT_ID,
                "category_code": "CAT1",
                "name": "Category 1",
            }
        }

        client = self._build_client(repo)
        response = client.get(f"/waitlist/status/{HOLD_ID}", headers=self._auth_headers())

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["hasWaitlist"])
        self.assertEqual(payload["nextUser"]["waitlistID"], WAITLIST_ID)
        self.assertNotIn("email", payload["nextUser"])

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_dequeue_waitlist_user_requires_hold_query(self, _mock_db_configured):
        client = self._build_client(Mock())

        response = client.delete(
            f"/waitlist/users/{USER_ID}",
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("holdID", response.get_json()["error"])

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_dequeue_waitlist_user_does_not_cancel_hold_offered(self, _mock_db_configured):
        repo = Mock()
        repo.get_hold_context.return_value = {
            "hold_id": HOLD_ID,
            "event_id": EVENT_ID,
            "category_id": CATEGORY_ID,
        }
        offered_entry = _entry(status="HOLD_OFFERED")
        offered_entry["hold_id"] = HOLD_ID
        repo.get_active_entry_for_user.side_effect = (
            lambda **kwargs: None if kwargs.get("active_statuses") == ["WAITING"] else offered_entry
        )
        repo.update_entry.return_value = None

        client = self._build_client(repo)
        response = client.delete(
            f"/waitlist/users/{USER_ID}?holdID={HOLD_ID}",
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("Active waitlist entry not found", response.get_json()["error"])

    @patch.object(waitlist_service, "db_configured", return_value=True)
    def test_dequeue_waitlist_user_marks_cancelled(self, _mock_db_configured):
        repo = Mock()
        repo.get_hold_context.return_value = {
            "hold_id": HOLD_ID,
            "event_id": EVENT_ID,
            "category_id": CATEGORY_ID,
        }
        repo.get_active_entry_for_user.return_value = _entry(status="WAITING")
        repo.update_entry.return_value = _entry(status="CANCELLED")
        repo.get_positions.return_value = {}
        repo.get_category_map.return_value = {
            CATEGORY_ID: {
                "category_id": CATEGORY_ID,
                "event_id": EVENT_ID,
                "category_code": "CAT1",
                "name": "Category 1",
            }
        }

        client = self._build_client(repo)
        response = client.delete(
            f"/waitlist/users/{USER_ID}?holdID={HOLD_ID}",
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
