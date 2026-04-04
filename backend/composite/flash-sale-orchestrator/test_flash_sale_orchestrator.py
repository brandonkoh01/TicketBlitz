import importlib.util
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
