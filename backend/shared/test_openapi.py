import pathlib
import sys
import unittest

from flask import Flask

# Ensure imports resolve when running this test file directly.
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from shared.openapi import (
    SWAGGER_UI_STATIC_DIR,
    build_openapi_spec,
    register_openapi_routes,
)


class OpenApiHelperTests(unittest.TestCase):
    def test_build_openapi_spec_includes_base_components(self):
        spec = build_openapi_spec(
            service_name="example-service",
            title="Example API",
            description="Example description",
            paths={"/health": {"get": {"responses": {"200": {"description": "ok"}}}}},
        )

        self.assertEqual(spec["openapi"], "3.0.3")
        self.assertIn("HealthResponse", spec["components"]["schemas"])
        self.assertIn("BadRequest", spec["components"]["responses"])

    def test_register_openapi_routes_serves_json_and_docs(self):
        app = Flask(__name__)

        def spec_builder():
            return build_openapi_spec(
                service_name="example-service",
                title="Example API",
                description="Example description",
                paths={"/health": {"get": {"responses": {"200": {"description": "ok"}}}}},
            )

        register_openapi_routes(app, spec_builder)

        client = app.test_client()
        openapi_response = client.get("/openapi.json")
        docs_response = client.get("/docs")

        self.assertEqual(openapi_response.status_code, 200)
        self.assertEqual(docs_response.status_code, 200)
        docs_html = docs_response.get_data(as_text=True)
        self.assertIn("swagger-ui", docs_html)
        self.assertIn("/docs/assets/swagger-ui.css", docs_html)
        self.assertNotIn("unpkg.com", docs_html)

        # Local assets should be served directly by the helper.
        self.assertTrue((SWAGGER_UI_STATIC_DIR / "swagger-ui.css").is_file())
        css_response = client.get("/docs/assets/swagger-ui.css")
        self.assertEqual(css_response.status_code, 200)
        self.assertGreater(len(css_response.get_data()), 0)
        css_response.close()


if __name__ == "__main__":
    unittest.main()
