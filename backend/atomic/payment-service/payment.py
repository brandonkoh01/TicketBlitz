import logging
import os

import stripe
from flask import Flask, jsonify, request
from flask_cors import CORS

from shared.db import db_configured
from shared.mq import rabbitmq_configured

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

    @app.get("/health")
    def health():
        return (
            jsonify(
                {
                    "status": "ok",
                    "service": os.getenv("SERVICE_NAME", "payment-service"),
                    "supabaseConfigured": db_configured(),
                    "rabbitmqConfigured": rabbitmq_configured(),
                    "stripeConfigured": bool(os.getenv("STRIPE_SECRET_KEY")),
                }
            ),
            200,
        )

    @app.post("/payment/webhook")
    def payment_webhook():
        payload = request.get_data(as_text=True)
        signature = request.headers.get("Stripe-Signature")
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

        event_type = "unverified"

        if webhook_secret and signature:
            try:
                event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
                event_type = event.get("type", "unknown")
            except ValueError:
                return jsonify({"error": "Invalid payload"}), 400
            except stripe.error.SignatureVerificationError:
                return jsonify({"error": "Invalid signature"}), 400

        return jsonify({"status": "accepted", "eventType": event_type}), 200

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Unhandled error: %s", error)
        return jsonify({"error": "Internal server error"}), 500

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
