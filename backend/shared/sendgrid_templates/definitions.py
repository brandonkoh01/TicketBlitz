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
    ]
