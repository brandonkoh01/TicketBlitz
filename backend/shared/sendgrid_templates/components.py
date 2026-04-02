"""Global building blocks for SendGrid dynamic template HTML/plain rendering."""

from __future__ import annotations

from typing import Iterable, Tuple


def token(name: str) -> str:
    """Return a SendGrid handlebars token for a dynamic field."""
    return "{{" + name + "}}"


def title_block(*, eyebrow: str, heading: str, subheading: str) -> str:
    return (
        "<p style='margin:0 0 8px;font-size:12px;letter-spacing:1.6px;"
        "text-transform:uppercase;color:#6b7280;font-weight:700;'>"
        + eyebrow
        + "</p>"
        + "<h1 style='margin:0;font-size:26px;line-height:1.2;color:#111827;font-weight:800;'>"
        + heading
        + "</h1>"
        + "<p style='margin:12px 0 0;font-size:15px;line-height:1.6;color:#374151;'>"
        + subheading
        + "</p>"
    )


def summary_table(rows: Iterable[Tuple[str, str]]) -> str:
    row_html = []
    for label, value in rows:
        row_html.append(
            "<tr>"
            "<td style='padding:10px 0;border-bottom:1px solid #e5e7eb;"
            "font-size:13px;line-height:1.4;color:#6b7280;font-weight:600;width:36%;'>"
            + label
            + "</td>"
            "<td style='padding:10px 0;border-bottom:1px solid #e5e7eb;"
            "font-size:14px;line-height:1.4;color:#111827;font-weight:700;'>"
            + value
            + "</td>"
            "</tr>"
        )

    return (
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'"
        " style='border-collapse:collapse;margin-top:18px;'>"
        + "".join(row_html)
        + "</table>"
    )


def cta_button(*, label: str, url_field: str) -> str:
    return (
        "<p style='margin:24px 0 0;'>"
        "<a href='"
        + token(url_field)
        + "'"
        " style='display:inline-block;padding:12px 20px;background:#111827;color:#ffffff;"
        "text-decoration:none;font-size:13px;letter-spacing:0.8px;text-transform:uppercase;"
        "font-weight:700;border-radius:4px;'>"
        + label
        + "</a>"
        "</p>"
    )


def conditional(block: str, *, field: str) -> str:
    return "{{#if " + field + "}}" + block + "{{/if}}"


def body_shell(*, inner_html: str) -> str:
    return (
        "<!doctype html>"
        "<html>"
        "<head>"
        "  <meta charset='utf-8' />"
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />"
        "  <title>TicketBlitz Notification</title>"
        "</head>"
        "<body style='margin:0;padding:0;background:#f3f4f6;font-family:Inter,Helvetica,Arial,sans-serif;'>"
        "  <table role='presentation' width='100%' cellpadding='0' cellspacing='0'"
        "    style='background:#f3f4f6;padding:24px 12px;'>"
        "    <tr>"
        "      <td align='center'>"
        "        <table role='presentation' width='100%' cellpadding='0' cellspacing='0'"
        "          style='max-width:640px;border-collapse:collapse;background:#ffffff;border:1px solid #e5e7eb;'>"
        "          <tr>"
        "            <td style='padding:30px 28px;'>"
        + inner_html
        + (
            "            </td>"
            "          </tr>"
            "          <tr>"
            "            <td style='padding:18px 28px;background:#111827;color:#d1d5db;"
            "font-size:12px;line-height:1.5;'>"
            "              This is an automated message from TicketBlitz."
            "            </td>"
            "          </tr>"
            "        </table>"
            "      </td>"
            "    </tr>"
            "  </table>"
            "</body>"
            "</html>"
        )
    )


def plain_text(*, heading: str, lines: Iterable[str], closing: str = "Thanks,\nTicketBlitz") -> str:
    segments = [heading, "", *lines, "", closing]
    return "\n".join(segments)
