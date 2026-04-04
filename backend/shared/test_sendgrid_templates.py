import pathlib
import sys
import unittest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from shared.sendgrid_templates import build_notification_template_definitions


class SendGridTemplateDefinitionTests(unittest.TestCase):
    def test_build_notification_templates_returns_four_core_templates(self):
        definitions = build_notification_template_definitions()

        self.assertEqual(len(definitions), 4)
        self.assertEqual(
            {definition.notification_type for definition in definitions},
            {
                "BOOKING_CONFIRMED",
                "WAITLIST_JOINED",
                "SEAT_AVAILABLE",
                "HOLD_EXPIRED",
            },
        )

    def test_each_template_has_env_mapping_and_handlebars_content(self):
        definitions = build_notification_template_definitions()

        for definition in definitions:
            self.assertTrue(definition.env_var.startswith("SENDGRID_TEMPLATE_"))
            self.assertTrue(definition.subject.strip())
            self.assertIn("<!doctype html>", definition.html_content)
            self.assertIn("TicketBlitz", definition.plain_content)

        by_type = {definition.notification_type: definition for definition in definitions}
        self.assertIn("{{eventName}}", by_type["BOOKING_CONFIRMED"].subject)
        self.assertIn("{{eventName}}", by_type["WAITLIST_JOINED"].subject)

    def test_seat_available_template_includes_payment_url_cta(self):
        definitions = build_notification_template_definitions()
        seat_available = next(
            definition
            for definition in definitions
            if definition.notification_type == "SEAT_AVAILABLE"
        )

        self.assertIn("{{paymentURL}}", seat_available.html_content)
        self.assertIn("{{#if paymentURL}}", seat_available.html_content)


if __name__ == "__main__":
    unittest.main()
