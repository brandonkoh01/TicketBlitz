import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_PATH = Path(__file__).resolve().parent / "pricing.py"
BACKEND_PATH = SERVICE_PATH.parents[2]
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

spec = importlib.util.spec_from_file_location("pricing_service_module", SERVICE_PATH)
pricing_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(pricing_module)


class PricingServiceTests(unittest.TestCase):
    def setUp(self):
        app = pricing_module.create_app()
        app.testing = True
        self.client = app.test_client()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_get_active_flash_sale_invalid_uuid(self):
        with patch.object(pricing_module, "db_configured", return_value=True):
            response = self.client.get("/pricing/not-a-uuid/flash-sale/active")

        self.assertEqual(response.status_code, 400)
        self.assertIn("eventID", response.get_json()["error"])

    def test_get_expired_active_flash_sales_invalid_event_uuid(self):
        with patch.object(pricing_module, "db_configured", return_value=True):
            response = self.client.get("/pricing/flash-sales/expired?eventID=bad-uuid")

        self.assertEqual(response.status_code, 400)
        self.assertIn("eventID", response.get_json()["error"])

    def test_get_expired_active_flash_sales_success(self):
        with patch.object(pricing_module, "db_configured", return_value=True), patch.object(
            pricing_module,
            "_find_expired_active_flash_sales",
            return_value=[
                {
                    "flash_sale_id": "00000000-0000-0000-0000-000000000099",
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "status": "ACTIVE",
                    "starts_at": "2026-04-04T12:00:00+00:00",
                    "ends_at": "2026-04-04T12:01:00+00:00",
                    "ended_at": None,
                }
            ],
        ):
            response = self.client.get("/pricing/flash-sales/expired?limit=5")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["flashSales"][0]["flashSaleID"], "00000000-0000-0000-0000-000000000099")

    def test_get_expired_active_flash_sales_include_ended_forwards_window(self):
        with patch.object(pricing_module, "db_configured", return_value=True), patch.object(
            pricing_module,
            "_find_expired_active_flash_sales",
            return_value=[],
        ) as selector:
            response = self.client.get(
                "/pricing/flash-sales/expired?includeEnded=1&endedWindowMinutes=45&limit=7"
            )

        self.assertEqual(response.status_code, 200)
        selector.assert_called_once_with(
            event_id=None,
            limit=7,
            include_ended=True,
            ended_since_minutes=45,
        )

    def test_get_expired_active_flash_sales_rejects_invalid_ended_window_minutes(self):
        with patch.object(pricing_module, "db_configured", return_value=True):
            response = self.client.get(
                "/pricing/flash-sales/expired?includeEnded=1&endedWindowMinutes=bad"
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("endedWindowMinutes", response.get_json()["error"])

    def test_escalate_requires_sold_out_category(self):
        with patch.object(pricing_module, "db_configured", return_value=True):
            response = self.client.post(
                "/pricing/escalate",
                json={
                    "eventID": "00000000-0000-0000-0000-000000000001",
                    "flashSaleID": "00000000-0000-0000-0000-000000000099",
                    "remainingCategories": [],
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("soldOutCategory", response.get_json()["error"])

    def test_escalate_requires_remaining_categories(self):
        with patch.object(pricing_module, "db_configured", return_value=True):
            response = self.client.post(
                "/pricing/escalate",
                json={
                    "eventID": "00000000-0000-0000-0000-000000000001",
                    "flashSaleID": "00000000-0000-0000-0000-000000000099",
                    "soldOutCategory": "CAT1",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("remainingCategories", response.get_json()["error"])

    def test_escalate_uses_only_remaining_categories(self):
        event_id = "00000000-0000-0000-0000-000000000001"
        flash_sale_id = "00000000-0000-0000-0000-000000000099"
        cat1_id = "00000000-0000-0000-0000-000000000010"
        cat2_id = "00000000-0000-0000-0000-000000000011"

        categories = [
            {
                "category_id": cat1_id,
                "category_code": "CAT1",
                "current_price": "200.00",
                "currency": "SGD",
                "is_active": True,
            },
            {
                "category_id": cat2_id,
                "category_code": "CAT2",
                "current_price": "100.00",
                "currency": "SGD",
                "is_active": True,
            },
        ]

        with patch.object(pricing_module, "db_configured", return_value=True), patch.object(
            pricing_module,
            "_find_active_flash_sale",
            return_value={"flash_sale_id": flash_sale_id, "escalation_percentage": "20"},
        ), patch.object(pricing_module, "_fetch_categories_for_event", return_value=categories):
            response = self.client.post(
                "/pricing/escalate",
                json={
                    "eventID": event_id,
                    "flashSaleID": flash_sale_id,
                    "soldOutCategory": "CAT1",
                    "remainingCategories": [{"categoryID": cat2_id}],
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["updatedPrices"][0]["categoryID"], cat2_id)

    def test_configure_flash_sale_success(self):
        event_id = "00000000-0000-0000-0000-000000000001"
        flash_sale_id = "00000000-0000-0000-0000-000000000099"

        categories = [
            {
                "category_id": "00000000-0000-0000-0000-000000000010",
                "category_code": "CAT1",
                "base_price": "250.00",
                "current_price": "200.00",
                "currency": "SGD",
            }
        ]

        with patch.object(pricing_module, "db_configured", return_value=True), \
            patch.object(pricing_module, "_fetch_event", return_value={"event_id": event_id, "status": "ACTIVE"}), \
            patch.object(pricing_module, "_fetch_categories_for_event", return_value=categories), \
            patch.object(
                pricing_module,
                "_insert_flash_sale",
                return_value={"flash_sale_id": flash_sale_id, "ends_at": "2026-04-04T12:00:00+00:00"},
            ):
            response = self.client.post(
                "/pricing/flash-sale/configure",
                json={
                    "eventID": event_id,
                    "discountPercentage": 50,
                    "durationMinutes": 120,
                    "escalationPercentage": 20,
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["flashSaleID"], flash_sale_id)
        self.assertEqual(len(body["updatedPrices"]), 1)
        self.assertEqual(body["updatedPrices"][0]["oldPrice"], "250.00")
        self.assertEqual(body["updatedPrices"][0]["newPrice"], "125.00")

    def test_configure_flash_sale_uses_base_price_not_current_price(self):
        event_id = "00000000-0000-0000-0000-000000000001"
        flash_sale_id = "00000000-0000-0000-0000-000000000099"

        categories = [
            {
                "category_id": "00000000-0000-0000-0000-000000000010",
                "category_code": "CAT1",
                "base_price": "288.00",
                "current_price": "15.73",
                "currency": "SGD",
            }
        ]

        with patch.object(pricing_module, "db_configured", return_value=True), \
            patch.object(pricing_module, "_fetch_event", return_value={"event_id": event_id, "status": "ACTIVE"}), \
            patch.object(pricing_module, "_fetch_categories_for_event", return_value=categories), \
            patch.object(
                pricing_module,
                "_insert_flash_sale",
                return_value={"flash_sale_id": flash_sale_id, "ends_at": "2026-04-04T12:00:00+00:00"},
            ):
            response = self.client.post(
                "/pricing/flash-sale/configure",
                json={
                    "eventID": event_id,
                    "discountPercentage": 30,
                    "durationMinutes": 120,
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["updatedPrices"][0]["oldPrice"], "288.00")
        self.assertEqual(body["updatedPrices"][0]["newPrice"], "201.60")

    def test_configure_flash_sale_conflict_maps_to_409(self):
        event_id = "00000000-0000-0000-0000-000000000001"

        with patch.object(pricing_module, "db_configured", return_value=True), \
            patch.object(pricing_module, "_fetch_event", return_value={"event_id": event_id, "status": "ACTIVE"}), \
            patch.object(
                pricing_module,
                "_fetch_categories_for_event",
                return_value=[
                    {
                        "category_id": "00000000-0000-0000-0000-000000000010",
                        "category_code": "CAT1",
                        "base_price": "200.00",
                        "current_price": "200.00",
                        "currency": "SGD",
                    }
                ],
            ), \
            patch.object(
                pricing_module,
                "_insert_flash_sale",
                side_effect=RuntimeError("violates unique constraint flash_sales_active_event_uk"),
            ):
            response = self.client.post(
                "/pricing/flash-sale/configure",
                json={
                    "eventID": event_id,
                    "discountPercentage": 50,
                    "durationMinutes": 120,
                },
            )

        self.assertEqual(response.status_code, 409)

    def test_get_effective_pricing_marks_missing_seat_rows_as_sold_out(self):
        event_id = "00000000-0000-0000-0000-000000000001"
        cat1_id = "00000000-0000-0000-0000-000000000010"
        cat2_id = "00000000-0000-0000-0000-000000000011"

        categories = [
            {
                "category_id": cat1_id,
                "category_code": "CAT1",
                "name": "Category 1",
                "base_price": "100.00",
                "current_price": "100.00",
                "currency": "SGD",
                "is_active": True,
            },
            {
                "category_id": cat2_id,
                "category_code": "CAT2",
                "name": "Category 2",
                "base_price": "120.00",
                "current_price": "120.00",
                "currency": "SGD",
                "is_active": True,
            },
        ]

        with patch.object(pricing_module, "db_configured", return_value=True), \
            patch.object(pricing_module, "_fetch_event", return_value={"event_id": event_id, "status": "ACTIVE"}), \
            patch.object(pricing_module, "_fetch_categories_for_event", return_value=categories), \
            patch.object(pricing_module, "_find_active_flash_sale", return_value=None), \
            patch.object(pricing_module, "_available_counts_by_category", return_value={cat2_id: 2}):
            response = self.client.get(f"/pricing/{event_id}")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        returned_categories = {entry["category"]: entry for entry in body["categories"]}
        self.assertEqual(returned_categories["CAT1"]["status"], "SOLD_OUT")
        self.assertEqual(returned_categories["CAT2"]["status"], "AVAILABLE")


if __name__ == "__main__":
    unittest.main()
