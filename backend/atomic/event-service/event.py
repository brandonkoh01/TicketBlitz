import logging
import os

from flask import Flask, jsonify
from flask_cors import CORS

from shared.db import db_configured, get_db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    @app.get("/health")
    def health():
        return (
            jsonify(
                {
                    "status": "ok",
                    "service": os.getenv("SERVICE_NAME", "event-service"),
                    "supabaseConfigured": db_configured(),
                }
            ),
            200,
        )

    @app.get("/events")
    def list_events():
        events = []

        if db_configured():
            try:
                result = (
                    get_db()
                    .table("events")
                    .select("event_id,event_code,name,venue,event_date,status")
                    .limit(50)
                    .execute()
                )
                events = result.data or []
            except Exception as error:
                logger.warning("Failed to load events from Supabase: %s", error)

        return jsonify({"events": events}), 200

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
