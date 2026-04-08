import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_PATH = Path(__file__).resolve().parent / "flash_sale_orchestrator.py"
BACKEND_PATH = SERVICE_PATH.parents[2]
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

spec = importlib.util.spec_from_file_location("flash_sale_orchestrator_module", SERVICE_PATH)
orchestrator_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(orchestrator_module)


class FlashSaleOrchestratorTests(unittest.TestCase):
    def setUp(self):
        app = orchestrator_module.create_app()
        app.testing = True
        self.client = app.test_client()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_launch_validation_invalid_event_id(self):
        response = self.client.post(
            "/flash-sale/launch",
            json={
                "eventID": "not-a-uuid",
                "discountPercentage": 50,
                "durationMinutes": 120,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("eventID", response.get_json()["error"])

    def test_launch_flash_sale_publishes_event_name_in_broadcast(self):
        event_id = "10000000-0000-0000-0000-000000000301"
        flash_sale_id = "10000000-0000-0000-0000-000000000401"

        def fake_request_json(method, service_name, base_url, path, **kwargs):
            if method == "GET" and path == f"/event/{event_id}":
                return {"event_id": event_id, "name": "Coldplay Live 2026"}
            if method == "GET" and path == f"/event/{event_id}/categories":
                return {
                    "event_id": event_id,
                    "categories": [
                        {
                            "category_id": "20000000-0000-0000-0000-000000000101",
                            "category_code": "CAT1",
                            "current_price": "100.00",
                            "is_active": True,
                        }
                    ],
                }
            if method == "POST" and path == "/pricing/flash-sale/configure":
                return {
                    "flashSaleID": flash_sale_id,
                    "updatedPrices": [
                        {
                            "categoryID": "20000000-0000-0000-0000-000000000101",
                            "newPrice": "70.00",
                            "category": "CAT1",
                            "currency": "SGD",
                        }
                    ],
                    "expiresAt": "2026-04-08T16:00:00Z",
                }
            if method == "PUT" and path in {
                f"/event/{event_id}/status",
                f"/event/{event_id}/categories/prices",
                f"/inventory/{event_id}/flash-sale",
            }:
                return {"status": "ok"}

            raise AssertionError(f"Unexpected request: {method} {service_name} {path}")

        with patch.object(orchestrator_module, "_request_json", side_effect=fake_request_json), patch.object(
            orchestrator_module,
            "_safe_waitlist_emails",
            return_value=["fan@example.com"],
        ), patch.object(orchestrator_module, "_publish_price_broadcast", return_value=True) as publish_mock:
            response = self.client.post(
                "/flash-sale/launch",
                json={
                    "eventID": event_id,
                    "discountPercentage": "30",
                    "durationMinutes": 30,
                    "escalationPercentage": "20",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["eventName"], "Coldplay Live 2026")
        self.assertEqual(body["discountPercentage"], "30.00%")

        publish_payload = publish_mock.call_args[0][0]
        self.assertEqual(publish_payload["type"], "FLASH_SALE_LAUNCHED")
        self.assertEqual(publish_payload["eventName"], "Coldplay Live 2026")
        self.assertEqual(publish_payload["discountPercentage"], "30.00%")

    def test_status_returns_null_pricing_when_no_active_sale(self):
        event_id = "10000000-0000-0000-0000-000000000301"

        def fake_request_json(method, service_name, base_url, path, **kwargs):
            if method == "GET" and path == f"/event/{event_id}/flash-sale/status":
                return {"event_id": event_id, "flash_sale_active": False}
            if method == "GET" and path == f"/pricing/{event_id}/flash-sale/active":
                raise orchestrator_module.DownstreamError("pricing-service", 404, "No active flash sale")
            raise AssertionError(f"Unexpected request: {method} {service_name} {path}")

        with patch.object(orchestrator_module, "_request_json", side_effect=fake_request_json):
            response = self.client.get(f"/flash-sale/{event_id}/status")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("event", body)
        self.assertIsNone(body.get("pricing"))

    def test_internal_reconcile_requires_internal_token_when_configured(self):
        with patch.dict(
            os.environ,
            {
                "INTERNAL_SERVICE_TOKEN": "secret-token",
                "INTERNAL_AUTH_HEADER": "X-Internal-Token",
            },
        ):
            app = orchestrator_module.create_app()
            app.testing = True
            client = app.test_client()

            response = client.post("/internal/flash-sale/reconcile-expired", json={})

        self.assertEqual(response.status_code, 401)
        self.assertIn("error", response.get_json())

    def test_internal_reconcile_fails_when_internal_token_missing(self):
        with patch.dict(
            os.environ,
            {
                "INTERNAL_SERVICE_TOKEN": "",
                "INTERNAL_AUTH_HEADER": "X-Internal-Token",
            },
            clear=False,
        ):
            app = orchestrator_module.create_app()
            app.testing = True
            client = app.test_client()

            response = client.post("/internal/flash-sale/reconcile-expired", json={})

        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.get_json())

    def test_end_flash_sale_updates_event_and_inventory_before_pricing_end(self):
        event_id = "10000000-0000-0000-0000-000000000301"
        flash_sale_id = "10000000-0000-0000-0000-000000000401"
        category_id = "20000000-0000-0000-0000-000000000011"
        call_order = []

        def fake_request_json(method, service_name, base_url, path, **kwargs):
            call_order.append(f"{method} {service_name} {path}")
            if method == "GET" and path == f"/event/{event_id}":
                return {"event_id": event_id, "name": "Coldplay Live 2026"}
            if method == "GET" and path == f"/pricing/{event_id}/history":
                return {
                    "priceChanges": [
                        {
                            "reason": "FLASH_SALE",
                            "categoryID": category_id,
                            "oldPrice": "100.00",
                        }
                    ]
                }
            if method == "GET" and path == f"/pricing/{event_id}":
                return {
                    "categories": [
                        {
                            "categoryID": category_id,
                            "category": "CAT1",
                            "currentPrice": "80.00",
                            "status": "AVAILABLE",
                            "currency": "SGD",
                        }
                    ]
                }
            if method == "PUT" and path in {
                f"/event/{event_id}/categories/prices",
                f"/event/{event_id}/status",
                f"/inventory/{event_id}/flash-sale",
                f"/pricing/{flash_sale_id}/end",
            }:
                return {"status": "ok"}
            raise AssertionError(f"Unexpected request: {method} {service_name} {path}")

        with patch.object(orchestrator_module, "_request_json", side_effect=fake_request_json), patch.object(
            orchestrator_module,
            "_safe_waitlist_emails",
            return_value=[],
        ), patch.object(orchestrator_module, "_publish_price_broadcast", return_value=True) as publish_mock:
            response = self.client.post(
                "/flash-sale/end",
                json={
                    "eventID": event_id,
                    "flashSaleID": flash_sale_id,
                },
            )

        self.assertEqual(response.status_code, 200)
        pricing_end_index = call_order.index(f"PUT pricing-service /pricing/{flash_sale_id}/end")
        self.assertLess(
            call_order.index(f"PUT event-service /event/{event_id}/status"),
            pricing_end_index,
        )
        self.assertLess(
            call_order.index(f"PUT inventory-service /inventory/{event_id}/flash-sale"),
            pricing_end_index,
        )
        body = response.get_json()
        self.assertEqual(body["eventName"], "Coldplay Live 2026")
        published_payload = publish_mock.call_args[0][0]
        self.assertEqual(published_payload["eventName"], "Coldplay Live 2026")

    def test_end_flash_sale_reverts_to_base_price_for_sold_out_categories(self):
        event_id = "10000000-0000-0000-0000-000000000301"
        flash_sale_id = "10000000-0000-0000-0000-000000000401"
        cat1_id = "20000000-0000-0000-0000-000000000011"
        cat2_id = "20000000-0000-0000-0000-000000000012"
        cat3_id = "20000000-0000-0000-0000-000000000013"
        category_update_payload = {}

        def fake_request_json(method, service_name, base_url, path, **kwargs):
            if method == "GET" and path == f"/event/{event_id}":
                return {"event_id": event_id, "name": "Coldplay Live 2026"}
            if method == "GET" and path == f"/pricing/{event_id}":
                return {
                    "categories": [
                        {
                            "categoryID": cat1_id,
                            "category": "CAT1",
                            "basePrice": "100.00",
                            "currentPrice": "84.00",
                            "status": "SOLD_OUT",
                            "currency": "SGD",
                        },
                        {
                            "categoryID": cat2_id,
                            "category": "CAT2",
                            "basePrice": "150.00",
                            "currentPrice": "105.00",
                            "status": "AVAILABLE",
                            "currency": "SGD",
                        },
                        {
                            "categoryID": cat3_id,
                            "category": "CAT3",
                            "basePrice": "200.00",
                            "currentPrice": "200.00",
                            "status": "AVAILABLE",
                            "currency": "SGD",
                        },
                    ]
                }
            if method == "PUT" and path == f"/event/{event_id}/categories/prices":
                category_update_payload.update(kwargs.get("json_body", {}))
                return {"status": "ok"}
            if method == "PUT" and path in {
                f"/event/{event_id}/status",
                f"/inventory/{event_id}/flash-sale",
                f"/pricing/{flash_sale_id}/end",
            }:
                return {"status": "ok"}
            raise AssertionError(f"Unexpected request: {method} {service_name} {path}")

        with patch.object(orchestrator_module, "_request_json", side_effect=fake_request_json), patch.object(
            orchestrator_module,
            "_safe_waitlist_emails",
            return_value=[],
        ), patch.object(orchestrator_module, "_publish_price_broadcast", return_value=True):
            response = self.client.post(
                "/flash-sale/end",
                json={
                    "eventID": event_id,
                    "flashSaleID": flash_sale_id,
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["eventName"], "Coldplay Live 2026")

        reverted_by_category = {
            row["categoryID"]: row
            for row in body["revertedPrices"]
        }
        self.assertIn(cat1_id, reverted_by_category)
        self.assertEqual(reverted_by_category[cat1_id]["oldPrice"], "84.00")
        self.assertEqual(reverted_by_category[cat1_id]["newPrice"], "100.00")
        self.assertIn(cat2_id, reverted_by_category)
        self.assertEqual(reverted_by_category[cat2_id]["oldPrice"], "105.00")
        self.assertEqual(reverted_by_category[cat2_id]["newPrice"], "150.00")
        self.assertNotIn(cat3_id, reverted_by_category)

        self.assertEqual(category_update_payload["reason"], "REVERT")
        updates_by_category = {
            row["category_id"]: row["new_price"]
            for row in category_update_payload["updates"]
        }
        self.assertEqual(updates_by_category[cat1_id], "100.00")
        self.assertEqual(updates_by_category[cat2_id], "150.00")
        self.assertNotIn(cat3_id, updates_by_category)

    def test_internal_reconcile_success_path_returns_success_payload(self):
        event_id = "10000000-0000-0000-0000-000000000301"
        flash_sale_id = "10000000-0000-0000-0000-000000000401"

        def fake_request_json(method, service_name, base_url, path, **kwargs):
            if method == "GET" and path == "/pricing/flash-sales/expired":
                params = kwargs.get("params", {})
                self.assertEqual(params.get("includeEnded"), "1")
                self.assertEqual(params.get("endedWindowMinutes"), "60")
                return {
                    "flashSales": [
                        {
                            "eventID": event_id,
                            "flashSaleID": flash_sale_id,
                        }
                    ]
                }
            if method == "GET" and path == f"/pricing/{event_id}/history":
                return {"priceChanges": []}
            if method == "GET" and path == f"/event/{event_id}":
                return {"event_id": event_id, "name": "Coldplay Live 2026"}
            if method == "GET" and path == f"/pricing/{event_id}":
                return {"categories": []}
            if method == "PUT" and path in {
                f"/event/{event_id}/status",
                f"/inventory/{event_id}/flash-sale",
                f"/pricing/{flash_sale_id}/end",
            }:
                return {"status": "ok"}
            if method == "PUT" and path == f"/event/{event_id}/categories/prices":
                return {"status": "ok"}
            raise AssertionError(f"Unexpected request: {method} {service_name} {path}")

        with patch.dict(
            os.environ,
            {
                "INTERNAL_SERVICE_TOKEN": "secret-token",
                "INTERNAL_AUTH_HEADER": "X-Internal-Token",
            },
            clear=False,
        ), patch.object(orchestrator_module, "_request_json", side_effect=fake_request_json), patch.object(
            orchestrator_module,
            "_safe_waitlist_emails",
            return_value=[],
        ), patch.object(orchestrator_module, "_publish_price_broadcast", return_value=True):
            app = orchestrator_module.create_app()
            app.testing = True
            client = app.test_client()
            response = client.post(
                "/internal/flash-sale/reconcile-expired",
                json={"eventID": event_id},
                headers={"X-Internal-Token": "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["endedCount"], 1)
        self.assertEqual(body["failedCount"] if "failedCount" in body else 0, 0)

    def test_internal_reconcile_returns_502_when_downstream_step_fails(self):
        event_id = "10000000-0000-0000-0000-000000000301"
        flash_sale_id = "10000000-0000-0000-0000-000000000401"

        def fake_request_json(method, service_name, base_url, path, **kwargs):
            if method == "GET" and path == "/pricing/flash-sales/expired":
                params = kwargs.get("params", {})
                self.assertEqual(params.get("includeEnded"), "1")
                self.assertEqual(params.get("endedWindowMinutes"), "60")
                return {
                    "flashSales": [
                        {
                            "eventID": event_id,
                            "flashSaleID": flash_sale_id,
                        }
                    ]
                }
            if method == "GET" and path == f"/pricing/{event_id}/history":
                return {"priceChanges": []}
            if method == "GET" and path == f"/event/{event_id}":
                return {"event_id": event_id, "name": "Coldplay Live 2026"}
            if method == "GET" and path == f"/pricing/{event_id}":
                return {"categories": []}
            if method == "PUT" and path == f"/event/{event_id}/status":
                raise orchestrator_module.DownstreamError(
                    "event-service",
                    500,
                    "Event update failed",
                )
            if method == "PUT" and path in {
                f"/inventory/{event_id}/flash-sale",
                f"/pricing/{flash_sale_id}/end",
                f"/event/{event_id}/categories/prices",
            }:
                return {"status": "ok"}
            raise AssertionError(f"Unexpected request: {method} {service_name} {path}")

        with patch.dict(
            os.environ,
            {
                "INTERNAL_SERVICE_TOKEN": "secret-token",
                "INTERNAL_AUTH_HEADER": "X-Internal-Token",
            },
            clear=False,
        ), patch.object(orchestrator_module, "_request_json", side_effect=fake_request_json), patch.object(
            orchestrator_module,
            "_safe_waitlist_emails",
            return_value=[],
        ), patch.object(orchestrator_module, "_publish_price_broadcast", return_value=True):
            app = orchestrator_module.create_app()
            app.testing = True
            client = app.test_client()
            response = client.post(
                "/internal/flash-sale/reconcile-expired",
                json={"eventID": event_id},
                headers={"X-Internal-Token": "secret-token"},
            )

        self.assertEqual(response.status_code, 502)
        body = response.get_json()
        self.assertEqual(body["details"]["failedCount"], 1)
        self.assertEqual(body["details"]["endedCount"], 0)


if __name__ == "__main__":
    unittest.main()
