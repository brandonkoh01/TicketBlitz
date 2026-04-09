import pathlib
import sys
import unittest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from shared.sendgrid_templates import build_notification_template_definitions


class SendGridTemplateDefinitionTests(unittest.TestCase):
    def test_build_notification_templates_contains_core_notification_types(self):
        definitions = build_notification_template_definitions()

        types = {definition.notification_type for definition in definitions}
        self.assertGreaterEqual(len(definitions), 4)
        self.assertTrue(
            {
                "BOOKING_CONFIRMED",
                "WAITLIST_JOINED",
                "SEAT_AVAILABLE",
                "HOLD_EXPIRED",
                "FLASH_SALE_LAUNCHED",
                "PRICE_ESCALATED",
                "FLASH_SALE_ENDED",
            }.issubset(types)
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

    def test_waitlist_joined_template_includes_status_cta(self):
        definitions = build_notification_template_definitions()
        waitlist_joined = next(
            definition
            for definition in definitions
            if definition.notification_type == "WAITLIST_JOINED"
        )

        self.assertIn("View Waitlist Status", waitlist_joined.html_content)
        self.assertIn("{{waitlistStatusURL}}", waitlist_joined.html_content)
        self.assertIn("{{#if waitlistStatusURL}}", waitlist_joined.html_content)
        self.assertIn("Status URL: {{waitlistStatusURL}}", waitlist_joined.plain_content)

    def test_scenario2_templates_include_expected_tokens(self):
        definitions = build_notification_template_definitions()
        by_type = {definition.notification_type: definition for definition in definitions}

        launched = by_type["FLASH_SALE_LAUNCHED"]
        self.assertIn("{{eventName}}", launched.subject)
        self.assertNotIn("{{eventID}}", launched.subject)
        self.assertIn("{{discountPercentage}}", launched.html_content)
        self.assertIn("{{expiresAtDisplay}}", launched.html_content)
        self.assertIn("{{updatedPrices}}", launched.plain_content)
        self.assertIn("Event: {{eventName}}", launched.plain_content)
        self.assertIn("Ends At: {{expiresAtDisplay}}", launched.plain_content)
        self.assertNotIn("Event ID:", launched.plain_content)

        escalated = by_type["PRICE_ESCALATED"]
        self.assertIn("{{soldOutCategory}}", escalated.html_content)
        self.assertIn("{{updatedPrices}}", escalated.plain_content)
        self.assertIn("{{eventName}}", escalated.subject)
        self.assertNotIn("{{eventID}}", escalated.subject)
        self.assertNotIn("Event ID:", escalated.plain_content)

        ended = by_type["FLASH_SALE_ENDED"]
        self.assertIn("{{eventName}}", ended.subject)
        self.assertNotIn("{{eventID}}", ended.subject)
        self.assertIn("{{revertedPrices}}", ended.plain_content)
        self.assertIn("Event: {{eventName}}", ended.plain_content)
        self.assertNotIn("Event ID:", ended.plain_content)


if __name__ == "__main__":
    unittest.main()
