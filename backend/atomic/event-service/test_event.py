import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

EVENT_SERVICE_PATH = Path(__file__).resolve().parent / "event.py"
BACKEND_PATH = EVENT_SERVICE_PATH.parents[2]
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

spec = importlib.util.spec_from_file_location("event_service_module", EVENT_SERVICE_PATH)
event_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(event_module)


class FakeDB:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)

    def table(self, *_args, **_kwargs):
        return self

    def select(self, *_args, **_kwargs):
        return self

    def update(self, *_args, **_kwargs):
        return self

    def insert(self, *_args, **_kwargs):
        return self

    def delete(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def gt(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        data = self.execute_results.pop(0) if self.execute_results else []
        return SimpleNamespace(data=data)


class EventServiceWriteRollbackTests(unittest.TestCase):
    def setUp(self):
        app = event_module.create_app()
        app.testing = True
        self.client = app.test_client()

    def test_update_status_rolls_back_when_publish_fails(self):
        fake_db = FakeDB([[]])

        with patch.object(event_module, "require_db", return_value=None), \
            patch.object(event_module, "parse_uuid", return_value=("event-123", None)), \
            patch.object(
                event_module,
                "fetch_event",
                side_effect=[
                    ({"event_id": "event-123", "status": "ACTIVE"}, None),
                    ({"event_id": "event-123", "status": "COMPLETED"}, None),
                ],
            ), \
            patch.object(event_module, "parse_json_object_body", return_value=({"status": "COMPLETED"}, None)), \
            patch.object(event_module, "get_db", return_value=fake_db), \
            patch.object(
                event_module,
                "publish_with_outbox",
                return_value=(False, {"event_id": "evt", "occurred_at": "now"}, "publish failed", 503),
            ), \
            patch.object(event_module, "rollback_event_status", return_value=True), \
            patch.object(event_module, "delete_integration_event", return_value=True):
            response = self.client.put(
                "/event/a73813ea-2e9e-4ecf-8ce6-2966a2f3218d/status",
                json={"status": "COMPLETED"},
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(body["error"], "Failed to update event status")
        self.assertTrue(body["details"]["rolledBack"])
        self.assertTrue(body["details"]["outboxCleanedUp"])

    def test_update_prices_rolls_back_when_publish_fails(self):
        existing_category = {
            "category_id": "cat-1",
            "event_id": "event-123",
            "current_price": "100.00",
            "deleted_at": None,
        }
        updated_category = {
            "category_id": "cat-1",
            "event_id": "event-123",
            "category_code": "CAT1",
            "name": "VIP",
            "base_price": "100.00",
            "current_price": "80.00",
            "currency": "SGD",
            "total_seats": 100,
            "is_active": True,
            "sort_order": 1,
            "metadata": {},
            "deleted_at": None,
        }
        fake_db = FakeDB([[existing_category], [], [{"change_id": "chg-1"}], [updated_category]])

        payload = {
            "reason": "FLASH_SALE",
            "changed_by": "organiser",
            "context": {"source": "test"},
            "updates": [{"category_id": "cat-1", "new_price": "80.00"}],
        }

        with patch.object(event_module, "require_db", return_value=None), \
            patch.object(event_module, "parse_uuid", return_value=("event-123", None)), \
            patch.object(event_module, "fetch_event", return_value=({"event_id": "event-123", "status": "ACTIVE"}, None)), \
            patch.object(event_module, "parse_json_object_body", return_value=(payload, None)), \
            patch.object(event_module, "normalize_price_updates", return_value=([{"category_id": "cat-1", "new_price": "80.00"}], None)), \
            patch.object(event_module, "get_db", return_value=fake_db), \
            patch.object(
                event_module,
                "publish_with_outbox",
                return_value=(False, {"event_id": "evt", "occurred_at": "now"}, "publish failed", 503),
            ), \
            patch.object(event_module, "rollback_category_prices", return_value=[]), \
            patch.object(event_module, "delete_price_change_records", return_value=[]), \
            patch.object(event_module, "delete_integration_event", return_value=True):
            response = self.client.put(
                "/event/a73813ea-2e9e-4ecf-8ce6-2966a2f3218d/categories/prices",
                json=payload,
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(body["error"], "Failed to update category prices")
        self.assertTrue(body["details"]["rolledBack"])
        self.assertTrue(body["details"]["outboxCleanedUp"])

    def test_update_status_requires_json_content_type(self):
        with patch.object(event_module, "require_db", return_value=None), \
            patch.object(event_module, "parse_uuid", return_value=("event-123", None)), \
            patch.object(event_module, "fetch_event", return_value=({"event_id": "event-123", "status": "ACTIVE"}, None)):
            response = self.client.put(
                "/event/a73813ea-2e9e-4ecf-8ce6-2966a2f3218d/status",
                data="status=COMPLETED",
                content_type="text/plain",
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 415)
        self.assertEqual(body["error"], "Content-Type must be application/json")

    def test_flash_sale_status_does_not_mark_expired_active_sale_as_active(self):
        fake_db = FakeDB(
            [
                [
                    {
                        "event_id": "event-123",
                        "flash_sale_active": True,
                        "active_flash_sale_id": "sale-123",
                    }
                ],
                [],
            ]
        )

        with patch.object(event_module, "require_db", return_value=None), \
            patch.object(event_module, "parse_uuid", return_value=("event-123", None)), \
            patch.object(
                event_module,
                "fetch_event",
                return_value=({"event_id": "event-123", "status": "FLASH_SALE_ACTIVE"}, None),
            ), \
            patch.object(event_module, "get_db", return_value=fake_db):
            response = self.client.get("/event/a73813ea-2e9e-4ecf-8ce6-2966a2f3218d/flash-sale/status")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertFalse(body["flash_sale_active"])
        self.assertIsNone(body["active_flash_sale"])


if __name__ == "__main__":
    unittest.main()
