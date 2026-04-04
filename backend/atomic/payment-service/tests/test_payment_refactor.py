import payment
import os
import sys
import unittest
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

SERVICE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parents[3]

if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class PaymentRefactorTests(unittest.TestCase):
    def test_payments_create_uses_shared_service(self):
        app = payment.create_app()
        hold_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        expected_payload = {
            "holdID": hold_id,
            "paymentIntentID": "pi_test",
            "clientSecret": "secret_test",
            "amount": "10.00",
            "currency": "SGD",
            "status": "PENDING",
            "holdExpiry": "2026-04-01T00:00:00+00:00",
            "transactionID": str(uuid.uuid4()),
        }

        with patch("payment._process_payment_initiation", return_value=(expected_payload, 201)) as process_mock:
            with app.test_client() as client:
                response = client.post(
                    "/payments/create",
                    json={"holdID": hold_id, "userID": user_id, "amount": 10},
                )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), expected_payload)
        self.assertEqual(process_mock.call_count, 1)

    def test_execute_refund_already_refunded_does_not_republish(self):
        transaction = {
            "transaction_id": str(uuid.uuid4()),
            "hold_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "amount": "100.00",
            "currency": "SGD",
            "status": "REFUND_SUCCEEDED",
            "refund_amount": "90.00",
            "correlation_id": str(uuid.uuid4()),
        }

        policy = {
            "withinPolicy": True,
            "eligibleRefundAmount": "90.00",
            "eventDate": "2026-04-20T00:00:00+00:00",
            "purchaseDate": "2026-04-01T00:00:00+00:00",
            "policyCutoffAt": "2026-04-18T00:00:00+00:00",
            "feePercentage": "10.00",
        }

        with patch("payment._safe_db_select_many", return_value=[]):
            with patch("payment._compute_policy", return_value=policy):
                with patch("payment._publish_refund_event") as publish_mock:
                    result = payment._execute_refund(transaction, None, None)

        self.assertEqual(result["status"], "already_refunded")
        self.assertEqual(result["attempts"], 0)
        publish_mock.assert_not_called()

    def test_webhook_duplicate_received_short_circuits_processing(self):
        app = payment.create_app()
        hold_id = str(uuid.uuid4())
        event = {
            "id": "evt_test_1",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_1",
                    "status": "succeeded",
                    "metadata": {"hold_id": hold_id},
                }
            },
        }

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test"}, clear=False):
            with patch("payment._require_supabase"):
                with patch("payment._require_stripe"):
                    with patch("payment.stripe.Webhook.construct_event", return_value=event):
                        with patch(
                            "payment._record_webhook_event",
                            return_value=(
                                {
                                    "webhook_event_id": "evt_test_1",
                                    "processing_status": "RECEIVED",
                                    "received_at": payment._iso_now(),
                                },
                                True,
                            ),
                        ):
                            with patch("payment._handle_payment_intent_succeeded") as handler_mock:
                                with app.test_client() as client:
                                    response = client.post(
                                        "/payment/webhook",
                                        data=b"{}",
                                        headers={
                                            "Stripe-Signature": "t=1,v1=fakesig"},
                                        content_type="application/json",
                                    )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["idempotent"])
        handler_mock.assert_not_called()

    def test_internal_auth_blocks_mutation_without_token(self):
        app = payment.create_app()
        hold_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        with patch.dict(os.environ, {"PAYMENT_INTERNAL_TOKEN": "internal-secret"}, clear=False):
            with patch("payment._process_payment_initiation") as process_mock:
                with app.test_client() as client:
                    response = client.post(
                        "/payments/create",
                        json={"holdID": hold_id,
                              "userID": user_id, "amount": 10},
                    )

        self.assertEqual(response.status_code, 401)
        process_mock.assert_not_called()

    def test_publish_booking_confirmed_includes_waitlist_id_when_present(self):
        transaction = {
            "hold_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
            "amount": "160.00",
            "currency": "SGD",
            "correlation_id": str(uuid.uuid4()),
        }

        with patch("payment._fetch_user_email", return_value="fan@example.com"):
            with patch("payment._resolve_waitlist_id_for_hold", return_value=str(uuid.uuid4())) as resolve_waitlist:
                with patch("payment.publish_json") as publish_json:
                    payment._publish_booking_confirmed(transaction, "pi_test")

        resolve_waitlist.assert_called_once_with(transaction["hold_id"])
        publish_json.assert_called_once()
        payload = publish_json.call_args.args[1]
        self.assertIn("waitlistID", payload)
        self.assertIsInstance(payload["waitlistID"], str)

    def test_publish_booking_confirmed_sets_waitlist_id_null_when_not_found(self):
        transaction = {
            "hold_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
            "amount": "160.00",
            "currency": "SGD",
            "correlation_id": str(uuid.uuid4()),
        }

        with patch("payment._fetch_user_email", return_value="fan@example.com"):
            with patch("payment._resolve_waitlist_id_for_hold", return_value=None):
                with patch("payment.publish_json") as publish_json:
                    payment._publish_booking_confirmed(transaction, "pi_test")

        publish_json.assert_called_once()
        payload = publish_json.call_args.args[1]
        self.assertIn("waitlistID", payload)
        self.assertIsNone(payload["waitlistID"])


if __name__ == "__main__":
    unittest.main()
