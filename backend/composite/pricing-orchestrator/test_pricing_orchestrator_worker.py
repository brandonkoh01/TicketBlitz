import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

MODULE_PATH = pathlib.Path(__file__).resolve().parent / "pricing_orchestrator.py"
spec = importlib.util.spec_from_file_location("pricing_orchestrator_module", MODULE_PATH)
pricing_orchestrator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(pricing_orchestrator)


class PricingOrchestratorWorkerTests(unittest.TestCase):
    def _config(self):
        return pricing_orchestrator.WorkerConfig(
            service_name="pricing-orchestrator",
            topic_exchange="ticketblitz",
            topic_routing_key="category.sold_out",
            topic_queue="pricing-orchestrator.category.sold_out",
            retry_queue="pricing-orchestrator.category.sold_out.retry",
            fanout_exchange="ticketblitz.price",
            retry_header_name="x-pricing-orchestrator-retry",
            retry_delay_ms=5000,
            max_retry_attempts=3,
            reconnect_delay_seconds=1,
            event_service_url="http://event-service:5000",
            inventory_service_url="http://inventory-service:5000",
            pricing_service_url="http://pricing-service:5000",
            waitlist_service_url="http://waitlist-service:5000",
            waitlist_auth_header="X-Internal-Token",
            internal_service_token="ticketblitz-internal-token",
            http_timeout_seconds=10,
        )

    def test_validate_payload_missing_field(self):
        worker = pricing_orchestrator.PricingOrchestratorWorker(self._config())

        with self.assertRaises(pricing_orchestrator.PermanentProcessingError):
            worker.validate_payload(
                {
                    "eventID": "evt-1",
                    "flashSaleID": "fs-1",
                    "soldAt": "2026-04-04T12:00:00Z",
                }
            )

    def test_process_payload_happy_path_publishes_escalation(self):
        worker = pricing_orchestrator.PricingOrchestratorWorker(self._config())

        payload = {
            "eventID": "evt-1",
            "category": "CAT1",
            "flashSaleID": "fs-1",
            "soldAt": "2026-04-04T12:00:00Z",
        }

        def fake_request_json(method, service_name, base_url, path, **kwargs):
            if method == "GET" and path == "/pricing/evt-1/flash-sale/active":
                return {"flashSaleID": "fs-1"}

            if method == "GET" and path == "/pricing/evt-1/history":
                return {"priceChanges": []}

            if method == "GET" and path == "/event/evt-1/categories":
                return {
                    "categories": [
                        {
                            "category_id": "cat-2",
                            "category_code": "CAT2",
                            "current_price": "100.00",
                            "is_active": True,
                        }
                    ]
                }

            if method == "GET" and path == "/inventory/evt-1/CAT2":
                return {"available": 2, "status": "AVAILABLE"}

            if method == "POST" and path == "/pricing/escalate":
                return {
                    "updatedPrices": [
                        {
                            "categoryID": "cat-2",
                            "category": "CAT2",
                            "oldPrice": "100.00",
                            "newPrice": "120.00",
                            "currency": "SGD",
                        }
                    ]
                }

            if method == "PUT" and path == "/event/evt-1/categories/prices":
                return {"ok": True}

            if method == "GET" and path == "/waitlist":
                return {"entries": [{"email": "fan@example.com"}]}

            raise AssertionError(f"Unexpected request: {method} {path}")

        with patch.object(worker, "_request_json", side_effect=fake_request_json), \
            patch.object(worker, "_publish_escalation") as publish_mock:
            worker.process_payload(payload, correlation_id="corr-1")

        publish_mock.assert_called_once()
        published_payload = publish_mock.call_args[0][0]
        self.assertEqual(published_payload["type"], "PRICE_ESCALATED")
        self.assertEqual(published_payload["eventID"], "evt-1")
        self.assertEqual(published_payload["soldOutCategory"], "CAT1")
        self.assertEqual(published_payload["waitlistEmails"], ["fan@example.com"])

    def test_handle_delivery_nacks_when_retry_enqueue_fails(self):
        worker = pricing_orchestrator.PricingOrchestratorWorker(self._config())

        channel = Mock()
        method = Mock(delivery_tag=42)
        properties = Mock(headers={})
        body = b'{"eventID":"evt-1","category":"CAT1","flashSaleID":"fs-1","soldAt":"2026-04-04T12:00:00Z"}'

        with patch.object(
            worker,
            "process_payload",
            side_effect=pricing_orchestrator.TransientProcessingError("network down"),
        ), patch.object(worker, "_enqueue_retry", return_value=False):
            worker._handle_delivery(channel, method, properties, body)

        channel.basic_ack.assert_not_called()
        channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=True)


if __name__ == "__main__":
    unittest.main()
