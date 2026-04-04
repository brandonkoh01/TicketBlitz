import os
import pathlib
import sys
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[3]
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

EVENT_ID = "10000000-0000-0000-0000-000000000301"
CATEGORY_CAT1_ID = "20000000-0000-0000-0000-000000000101"
CATEGORY_CAT2_ID = "20000000-0000-0000-0000-000000000102"
CATEGORY_PEN_ID = "20000000-0000-0000-0000-000000000103"

USER_1 = "9aa10000-0000-0000-0000-000000000001"
USER_2 = "9aa10000-0000-0000-0000-000000000002"
USER_3 = "9aa10000-0000-0000-0000-000000000003"
USER_1_EMAIL = "wpo.qa1@ticketblitz.com"
USER_2_EMAIL = "wpo.qa2@ticketblitz.com"
USER_3_EMAIL = "wpo.qa3@ticketblitz.com"

SEAT_CAT1_A = "3aa00000-0000-0000-0000-000000000101"
SEAT_CAT1_B = "3aa00000-0000-0000-0000-000000000102"
SEAT_PEN_A = "3aa00000-0000-0000-0000-000000000103"
SEAT_CAT2_A = "3aa00000-0000-0000-0000-000000000104"

WAITLIST_CAT1_1 = "9bb20000-0000-0000-0000-000000000001"
WAITLIST_CAT1_2 = "9bb20000-0000-0000-0000-000000000002"
WAITLIST_PEN_1 = "9bb20000-0000-0000-0000-000000000003"

HTTP_TIMEOUT = (3.05, 15)
ASYNC_TIMEOUT_SECONDS = 20
POLL_INTERVAL_SECONDS = 1.0


class WaitlistPromotionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_dotenv(PROJECT_ROOT / ".env.local")

        cls.inventory_base_url = os.getenv("INVENTORY_BASE_URL", "http://localhost:5003")
        cls.waitlist_base_url = os.getenv("WAITLIST_BASE_URL", "http://localhost:5005")
        cls.user_base_url = os.getenv("USER_BASE_URL", "http://localhost:5002")

        cls.internal_auth_header = os.getenv("INTERNAL_AUTH_HEADER", "X-Internal-Token")
        cls.internal_service_token = os.getenv("INTERNAL_SERVICE_TOKEN", "ticketblitz-internal-token")
        cls.internal_headers = {cls.internal_auth_header: cls.internal_service_token}

        supabase_url = os.getenv("SUPABASE_URL")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
        if not supabase_url or not supabase_service_key:
            raise unittest.SkipTest("SUPABASE_URL and SUPABASE_SERVICE_KEY are required for integration tests")

        cls.db = create_client(supabase_url, supabase_service_key)
        cls.session = requests.Session()
        cls.session.headers.update({"Accept": "application/json"})

        cls._wait_for_service_health()

    @classmethod
    def tearDownClass(cls):
        cls.session.close()

    def setUp(self):
        self._reset_fixtures()

    @classmethod
    def _wait_for_service_health(cls):
        health_endpoints = [
            f"{cls.inventory_base_url}/health",
            f"{cls.waitlist_base_url}/health",
            f"{cls.user_base_url}/health",
        ]

        deadline = time.time() + 60
        while time.time() < deadline:
            all_up = True
            for endpoint in health_endpoints:
                try:
                    response = cls.session.get(endpoint, timeout=HTTP_TIMEOUT)
                    if response.status_code != 200:
                        all_up = False
                        break
                except requests.RequestException:
                    all_up = False
                    break

            if all_up:
                return
            time.sleep(2)

        raise unittest.SkipTest(
            "Required services are not healthy. Start compose services first: rabbitmq, user-service, waitlist-service, inventory-service, waitlist-promotion-orchestrator"
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _request(self, method: str, url: str, *, expected_status: int | None = None, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = HTTP_TIMEOUT

        response = self.session.request(method, url, **kwargs)
        if expected_status is not None:
            self.assertEqual(
                response.status_code,
                expected_status,
                msg=f"Expected HTTP {expected_status} for {method} {url}, got {response.status_code} body={response.text}",
            )
        return response

    def _wait_until(self, predicate, timeout_seconds=ASYNC_TIMEOUT_SECONDS, poll_interval=POLL_INTERVAL_SECONDS, failure_message="Condition not met"):
        deadline = time.time() + timeout_seconds
        last_value = None
        while time.time() < deadline:
            last_value = predicate()
            if last_value:
                return last_value
            time.sleep(poll_interval)

        self.fail(f"{failure_message}. Last observed value: {last_value}")

    def _fetch_waitlist_entry(self, waitlist_id: str) -> dict | None:
        try:
            response = self.session.get(
                f"{self.waitlist_base_url}/waitlist/{waitlist_id}",
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException:
            return None

        if response.status_code != 200:
            return None

        try:
            return response.json()
        except ValueError:
            return None

    def _wait_for_waitlist_status(self, waitlist_id: str, expected_status: str) -> dict:
        def _check():
            entry = self._fetch_waitlist_entry(waitlist_id)
            if not entry:
                return None
            if entry.get("status") == expected_status:
                return entry
            return None

        return self._wait_until(
            _check,
            failure_message=f"Waitlist {waitlist_id} did not reach status {expected_status}",
        )

    def _fetch_hold(self, hold_id: str) -> dict:
        response = self._request("GET", f"{self.inventory_base_url}/inventory/hold/{hold_id}", expected_status=200)
        return response.json()

    def _fetch_seat_status(self, seat_id: str) -> str:
        result = (
            self.db.table("seats")
            .select("status")
            .eq("seat_id", seat_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        self.assertTrue(rows, msg=f"Seat {seat_id} not found")
        return rows[0]["status"]

    def _notification_event_exists(self, *, event_type: str, hold_id: str, email: str, since_iso: str) -> bool:
        try:
            result = (
                self.db.table("integration_events")
                .select("routing_key,payload,occurred_at")
                .eq("routing_key", "notification.send")
                .gte("occurred_at", since_iso)
                .order("occurred_at", desc=True)
                .limit(100)
                .execute()
            )
        except Exception:
            return False

        for row in result.data or []:
            payload = row.get("payload") or {}
            if payload.get("type") != event_type:
                continue
            if payload.get("holdID") != hold_id:
                continue
            if payload.get("email") != email:
                continue
            return True
        return False

    def _reset_fixtures(self):
        now_iso = self._now_iso()

        self.db.table("waitlist_entries").update(
            {
                "status": "CANCELLED",
                "hold_id": None,
                "offered_at": None,
                "confirmed_at": None,
                "expired_at": None,
                "updated_at": now_iso,
            }
        ).eq("event_id", EVENT_ID).in_("user_id", [USER_1, USER_2, USER_3]).in_(
            "status", ["WAITING", "HOLD_OFFERED"]
        ).execute()

        self.db.table("seat_holds").update(
            {
                "status": "RELEASED",
                "release_reason": "SYSTEM_CLEANUP",
                "released_at": now_iso,
                "updated_at": now_iso,
            }
        ).in_(
            "seat_id", [SEAT_CAT1_A, SEAT_CAT1_B, SEAT_PEN_A, SEAT_CAT2_A]
        ).eq(
            "status", "HELD"
        ).execute()

        self.db.table("users").upsert(
            [
                {
                    "user_id": USER_1,
                    "full_name": "WPO QA User 1",
                    "email": USER_1_EMAIL,
                    "phone": None,
                    "metadata": {"fixture": "wpo_integration"},
                    "deleted_at": None,
                    "updated_at": now_iso,
                },
                {
                    "user_id": USER_2,
                    "full_name": "WPO QA User 2",
                    "email": USER_2_EMAIL,
                    "phone": None,
                    "metadata": {"fixture": "wpo_integration"},
                    "deleted_at": None,
                    "updated_at": now_iso,
                },
                {
                    "user_id": USER_3,
                    "full_name": "WPO QA User 3",
                    "email": USER_3_EMAIL,
                    "phone": None,
                    "metadata": {"fixture": "wpo_integration"},
                    "deleted_at": None,
                    "updated_at": now_iso,
                },
            ],
            on_conflict="user_id",
        ).execute()

        self.db.table("seats").upsert(
            [
                {
                    "seat_id": SEAT_CAT1_A,
                    "event_id": EVENT_ID,
                    "category_id": CATEGORY_CAT1_ID,
                    "seat_number": "WPO-CAT1-A",
                    "status": "PENDING_WAITLIST",
                    "sold_at": None,
                    "metadata": {"fixture": "wpo_integration"},
                    "updated_at": now_iso,
                },
                {
                    "seat_id": SEAT_CAT1_B,
                    "event_id": EVENT_ID,
                    "category_id": CATEGORY_CAT1_ID,
                    "seat_number": "WPO-CAT1-B",
                    "status": "PENDING_WAITLIST",
                    "sold_at": None,
                    "metadata": {"fixture": "wpo_integration"},
                    "updated_at": now_iso,
                },
                {
                    "seat_id": SEAT_PEN_A,
                    "event_id": EVENT_ID,
                    "category_id": CATEGORY_PEN_ID,
                    "seat_number": "WPO-PEN-A",
                    "status": "PENDING_WAITLIST",
                    "sold_at": None,
                    "metadata": {"fixture": "wpo_integration"},
                    "updated_at": now_iso,
                },
                {
                    "seat_id": SEAT_CAT2_A,
                    "event_id": EVENT_ID,
                    "category_id": CATEGORY_CAT2_ID,
                    "seat_number": "WPO-CAT2-A",
                    "status": "PENDING_WAITLIST",
                    "sold_at": None,
                    "metadata": {"fixture": "wpo_integration"},
                    "updated_at": now_iso,
                },
            ],
            on_conflict="seat_id",
        ).execute()

        joined_1 = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        joined_2 = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        joined_3 = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

        self.db.table("waitlist_entries").upsert(
            [
                {
                    "waitlist_id": WAITLIST_CAT1_1,
                    "event_id": EVENT_ID,
                    "category_id": CATEGORY_CAT1_ID,
                    "user_id": USER_1,
                    "hold_id": None,
                    "status": "WAITING",
                    "joined_at": joined_1,
                    "offered_at": None,
                    "confirmed_at": None,
                    "expired_at": None,
                    "priority_score": 10,
                    "source": "WPO_INTEGRATION",
                    "metadata": {"fixture": "wpo_integration", "order": 1},
                    "updated_at": now_iso,
                },
                {
                    "waitlist_id": WAITLIST_CAT1_2,
                    "event_id": EVENT_ID,
                    "category_id": CATEGORY_CAT1_ID,
                    "user_id": USER_2,
                    "hold_id": None,
                    "status": "WAITING",
                    "joined_at": joined_2,
                    "offered_at": None,
                    "confirmed_at": None,
                    "expired_at": None,
                    "priority_score": 9,
                    "source": "WPO_INTEGRATION",
                    "metadata": {"fixture": "wpo_integration", "order": 2},
                    "updated_at": now_iso,
                },
                {
                    "waitlist_id": WAITLIST_PEN_1,
                    "event_id": EVENT_ID,
                    "category_id": CATEGORY_PEN_ID,
                    "user_id": USER_3,
                    "hold_id": None,
                    "status": "WAITING",
                    "joined_at": joined_3,
                    "offered_at": None,
                    "confirmed_at": None,
                    "expired_at": None,
                    "priority_score": 8,
                    "source": "WPO_INTEGRATION",
                    "metadata": {"fixture": "wpo_integration", "order": 1},
                    "updated_at": now_iso,
                },
            ],
            on_conflict="waitlist_id",
        ).execute()

        # Ensure no active CAT2 waitlist rows interfere with no-candidate path tests.
        self.db.table("waitlist_entries").update(
            {
                "status": "CANCELLED",
                "hold_id": None,
                "offered_at": None,
                "confirmed_at": None,
                "expired_at": None,
                "updated_at": now_iso,
            }
        ).eq("event_id", EVENT_ID).eq("category_id", CATEGORY_CAT2_ID).in_(
            "status", ["WAITING", "HOLD_OFFERED"]
        ).execute()

    def _create_hold(self, *, user_id: str, seat_category: str, from_waitlist: bool, idempotency_key: str) -> dict:
        response = self._request(
            "POST",
            f"{self.inventory_base_url}/inventory/hold",
            expected_status=201,
            json={
                "eventID": EVENT_ID,
                "userID": user_id,
                "seatCategory": seat_category,
                "qty": 1,
                "fromWaitlist": from_waitlist,
                "idempotencyKey": idempotency_key,
            },
        )
        return response.json()

    def _release_hold(self, hold_id: str, reason: str) -> dict:
        response = self._request(
            "PUT",
            f"{self.inventory_base_url}/inventory/hold/{hold_id}/release",
            expected_status=200,
            json={"reason": reason},
        )
        return response.json()

    def _force_hold_expired(self, hold_id: str):
        now_iso = self._now_iso()
        hold_row_result = (
            self.db.table("seat_holds")
            .select("created_at")
            .eq("hold_id", hold_id)
            .eq("status", "HELD")
            .limit(1)
            .execute()
        )

        hold_rows = hold_row_result.data or []
        self.assertTrue(hold_rows, msg=f"Active held row not found for hold {hold_id}")

        created_at = hold_rows[0]["created_at"]
        self.db.table("seat_holds").update(
            {
                # Use created_at to satisfy expiry checks while guaranteeing immediate expiration eligibility.
                "hold_expires_at": created_at,
                "updated_at": now_iso,
            }
        ).eq("hold_id", hold_id).eq("status", "HELD").execute()

    def test_should_promote_next_waiting_user_when_pending_waitlist_seat_is_released(self):
        initial_hold = self._create_hold(
            user_id=USER_1,
            seat_category="CAT1",
            from_waitlist=True,
            idempotency_key=f"wpo-it-promote-{uuid.uuid4()}",
        )
        self._release_hold(initial_hold["holdID"], "MANUAL_RELEASE")

        offered_entry = self._wait_for_waitlist_status(WAITLIST_CAT1_1, "HOLD_OFFERED")

        offered_hold_id = offered_entry.get("holdID")
        self.assertTrue(offered_hold_id, msg="Promoted waitlist entry should include holdID")

        offered_hold = self._fetch_hold(offered_hold_id)
        self.assertIn(offered_hold["holdStatus"], {"HELD", "RELEASED"})
        self.assertTrue(offered_hold["fromWaitlist"])
        self.assertEqual(offered_hold["userID"], USER_1)

    def test_should_expire_previous_offer_and_promote_next_waiting_user_on_timeout(self):
        initial_hold = self._create_hold(
            user_id=USER_1,
            seat_category="CAT1",
            from_waitlist=True,
            idempotency_key=f"wpo-it-timeout-seed-{uuid.uuid4()}",
        )

        first_offered_hold = initial_hold["holdID"]

        self._request(
            "PUT",
            f"{self.waitlist_base_url}/waitlist/{WAITLIST_CAT1_1}/offer",
            expected_status=200,
            headers=self.internal_headers,
            json={"holdID": first_offered_hold},
        )

        self._release_hold(first_offered_hold, "PAYMENT_TIMEOUT")

        self._wait_for_waitlist_status(WAITLIST_CAT1_1, "EXPIRED")

        offered_entry_2 = self._wait_for_waitlist_status(WAITLIST_CAT1_2, "HOLD_OFFERED")

        second_offered_hold = offered_entry_2.get("holdID")
        self.assertTrue(second_offered_hold)
        self.assertNotEqual(second_offered_hold, first_offered_hold)

        first_hold = self._fetch_hold(first_offered_hold)
        self.assertIn(first_hold["holdStatus"], {"EXPIRED", "RELEASED"})

        second_hold = self._fetch_hold(second_offered_hold)
        self.assertEqual(second_hold["userID"], USER_2)
        self.assertTrue(second_hold["fromWaitlist"])

    def test_should_set_seat_available_when_released_category_has_no_waiting_candidate(self):
        hold = self._create_hold(
            user_id=USER_3,
            seat_category="CAT2",
            from_waitlist=True,
            idempotency_key=f"wpo-it-no-candidate-{uuid.uuid4()}",
        )

        released = self._release_hold(hold["holdID"], "MANUAL_RELEASE")
        released_seat_id = released["seatID"]

        self._wait_until(
            lambda: released_seat_id if self._fetch_seat_status(released_seat_id) == "AVAILABLE" else None,
            failure_message="Released CAT2 seat was not returned to AVAILABLE",
        )


if __name__ == "__main__":
    unittest.main()
