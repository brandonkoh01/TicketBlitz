"""Template definitions for notification events sent via SendGrid dynamic templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .components import body_shell, conditional, cta_button, plain_text, summary_table, title_block, token


@dataclass(frozen=True)
class EmailTemplateDefinition:
    notification_type: str
    env_var: str
    template_name: str
    version_name: str
    subject: str
    html_content: str
    plain_content: str


def build_notification_template_definitions() -> List[EmailTemplateDefinition]:
    booking_confirmed_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Ticket Confirmed",
                heading="Your booking is confirmed",
                subheading="Your seat has been secured. Keep this ticket reference for entry.",
            )
            + summary_table(
                [
                    ("Event", token("eventName")),
                    ("Seat", token("seatNumber")),
                    ("Ticket ID", token("ticketID")),
                ]
            )
        )
    )

    waitlist_joined_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Waitlist Joined",
                heading="You are on the waitlist",
                subheading="We will notify you the moment a seat becomes available.",
            )
            + summary_table(
                [
                    ("Event", token("eventName")),
                    ("Queue Position", token("position")),
                    ("Waitlist ID", token("waitlistID")),
                ]
            )
            + conditional(
                cta_button(label="View Waitlist Status", url_field="waitlistStatusURL"),
                field="waitlistStatusURL",
            )
        )
    )

    seat_available_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Seat Available",
                heading="A seat is reserved for you",
                subheading="Your hold will expire soon. Complete payment before the deadline.",
            )
            + summary_table(
                [
                    ("Hold ID", token("holdID")),
                    ("Hold Expires", token("holdExpiry")),
                ]
            )
            + conditional(cta_button(label="Complete Payment", url_field="paymentURL"), field="paymentURL")
        )
    )

    hold_expired_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Hold Expired",
                heading="Your seat hold has expired",
                subheading="The reservation window elapsed before payment was completed.",
            )
            + summary_table(
                [("Hold ID", token("holdID"))]
            )
        )
    )

    cancellation_confirmed_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Cancellation Confirmed",
                heading="Your cancellation request is confirmed",
                subheading="We are now processing your refund.",
            )
            + summary_table(
                [
                    ("Booking ID", token("bookingID")),
                    ("Event", token("eventName")),
                ]
            )
        )
    )

    cancellation_denied_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Cancellation Denied",
                heading="Your cancellation could not be processed",
                subheading="This request is outside the allowed refund policy window.",
            )
            + summary_table(
                [
                    ("Booking ID", token("bookingID")),
                    ("Reason", token("reason")),
                ]
            )
        )
    )

    refund_successful_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Refund Successful",
                heading="Your refund has been issued",
                subheading="The refund should appear based on your bank processing timeline.",
            )
            + summary_table(
                [
                    ("Booking ID", token("bookingID")),
                    ("Refund Amount", token("refundAmount")),
                    ("Event", token("eventName")),
                ]
            )
        )
    )

    refund_error_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Refund Update",
                heading="Your refund needs follow-up",
                subheading="We are unable to complete the refund automatically right now.",
            )
            + summary_table(
                [
                    ("Booking ID", token("bookingID")),
                    ("Issue", token("errorDetail")),
                    ("Next Steps", token("nextSteps")),
                ]
            )
        )
    )

    ticket_available_public_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Ticket Available",
                heading="A ticket is now available",
                subheading="A seat has been returned to inventory.",
            )
            + summary_table(
                [
                    ("Booking ID", token("bookingID")),
                    ("Event", token("eventName")),
                ]
            )
        )
    )

    ticket_confirmation_html = body_shell(
        inner_html=(
            title_block(
                eyebrow="Ticket Confirmed",
                heading="Your reallocated ticket is confirmed",
                subheading="Your new booking is complete.",
            )
            + summary_table(
                [
                    ("Booking ID", token("bookingID")),
                    ("Ticket ID", token("ticketID")),
                    ("Seat", token("seatNumber")),
                    ("Event", token("eventName")),
                ]
            )
        )
    )

    return [
        EmailTemplateDefinition(
            notification_type="BOOKING_CONFIRMED",
            env_var="SENDGRID_TEMPLATE_BOOKING_CONFIRMED",
            template_name="TicketBlitz - Booking Confirmed",
            version_name="booking-confirmed-v1",
            subject="Booking confirmed: {{eventName}}",
            html_content=booking_confirmed_html,
            plain_content=plain_text(
                heading="Booking Confirmed",
                lines=[
                    "Event: {{eventName}}",
                    "Seat: {{seatNumber}}",
                    "Ticket ID: {{ticketID}}",
                ],
            ),
        ),
        EmailTemplateDefinition(
            notification_type="WAITLIST_JOINED",
            env_var="SENDGRID_TEMPLATE_WAITLIST_JOINED",
            template_name="TicketBlitz - Waitlist Joined",
            version_name="waitlist-joined-v1",
            subject="Waitlist joined: {{eventName}}",
            html_content=waitlist_joined_html,
            plain_content=plain_text(
                heading="Waitlist Joined",
                lines=[
                    "Event: {{eventName}}",
                    "Position: {{position}}",
                    "Waitlist ID: {{waitlistID}}",
                    "Status URL: {{waitlistStatusURL}}",
                ],
            ),
        ),
        EmailTemplateDefinition(
            notification_type="SEAT_AVAILABLE",
            env_var="SENDGRID_TEMPLATE_SEAT_AVAILABLE",
            template_name="TicketBlitz - Seat Available",
            version_name="seat-available-v1",
            subject="Seat available now",
            html_content=seat_available_html,
            plain_content=plain_text(
                heading="Seat Available",
                lines=[
                    "Hold ID: {{holdID}}",
                    "Expires: {{holdExpiry}}",
                    "Payment URL: {{paymentURL}}",
                ],
            ),
        ),
        EmailTemplateDefinition(
            notification_type="HOLD_EXPIRED",
            env_var="SENDGRID_TEMPLATE_HOLD_EXPIRED",
            template_name="TicketBlitz - Hold Expired",
            version_name="hold-expired-v1",
            subject="Seat hold expired",
            html_content=hold_expired_html,
            plain_content=plain_text(
                heading="Hold Expired",
                lines=[
                    "Hold ID: {{holdID}}",
                ],
            ),
        ),
        EmailTemplateDefinition(
            notification_type="CANCELLATION_CONFIRMED",
            env_var="SENDGRID_TEMPLATE_CANCELLATION_CONFIRMED",
            template_name="TicketBlitz - Cancellation Confirmed",
            version_name="cancellation-confirmed-v1",
            subject="Cancellation confirmed",
            html_content=cancellation_confirmed_html,
            plain_content=plain_text(
                heading="Cancellation Confirmed",
                lines=[
                    "Booking ID: {{bookingID}}",
                    "Event: {{eventName}}",
                ],
            ),
        ),
        EmailTemplateDefinition(
            notification_type="CANCELLATION_DENIED",
            env_var="SENDGRID_TEMPLATE_CANCELLATION_DENIED",
            template_name="TicketBlitz - Cancellation Denied",
            version_name="cancellation-denied-v1",
            subject="Cancellation request denied",
            html_content=cancellation_denied_html,
            plain_content=plain_text(
                heading="Cancellation Denied",
                lines=[
                    "Booking ID: {{bookingID}}",
                    "Reason: {{reason}}",
                ],
            ),
        ),
        EmailTemplateDefinition(
            notification_type="REFUND_SUCCESSFUL",
            env_var="SENDGRID_TEMPLATE_REFUND_SUCCESSFUL",
            template_name="TicketBlitz - Refund Successful",
            version_name="refund-successful-v1",
            subject="Refund successful",
            html_content=refund_successful_html,
            plain_content=plain_text(
                heading="Refund Successful",
                lines=[
                    "Booking ID: {{bookingID}}",
                    "Refund Amount: {{refundAmount}}",
                    "Event: {{eventName}}",
                ],
            ),
        ),
        EmailTemplateDefinition(
            notification_type="REFUND_ERROR",
            env_var="SENDGRID_TEMPLATE_REFUND_ERROR",
            template_name="TicketBlitz - Refund Error",
            version_name="refund-error-v1",
            subject="Refund processing update",
            html_content=refund_error_html,
            plain_content=plain_text(
                heading="Refund Processing Update",
                lines=[
                    "Booking ID: {{bookingID}}",
                    "Issue: {{errorDetail}}",
                    "Next Steps: {{nextSteps}}",
                ],
            ),
        ),
        EmailTemplateDefinition(
            notification_type="TICKET_AVAILABLE_PUBLIC",
            env_var="SENDGRID_TEMPLATE_TICKET_AVAILABLE_PUBLIC",
            template_name="TicketBlitz - Ticket Available",
            version_name="ticket-available-public-v1",
            subject="Ticket available now",
            html_content=ticket_available_public_html,
            plain_content=plain_text(
                heading="Ticket Available",
                lines=[
                    "Booking ID: {{bookingID}}",
                    "Event: {{eventName}}",
                ],
            ),
        ),
        EmailTemplateDefinition(
            notification_type="TICKET_CONFIRMATION",
            env_var="SENDGRID_TEMPLATE_TICKET_CONFIRMATION",
            template_name="TicketBlitz - Ticket Confirmation",
            version_name="ticket-confirmation-v1",
            subject="Your ticket is confirmed",
            html_content=ticket_confirmation_html,
            plain_content=plain_text(
                heading="Ticket Confirmation",
                lines=[
                    "Booking ID: {{bookingID}}",
                    "Ticket ID: {{ticketID}}",
                    "Seat: {{seatNumber}}",
                    "Event: {{eventName}}",
                ],
            ),
        ),
    ]
