"""Send the report over SMTP (Gmail by default), with the chart inline."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from . import config


class MailError(RuntimeError):
    """Delivery failed; the workflow should fail loudly rather than look fine."""


def missing_settings() -> list[str]:
    """Names of the required secrets that are not set."""
    required = {
        "GMAIL_USER": config.SMTP_USER,
        "GMAIL_APP_PASSWORD": config.SMTP_PASSWORD,
        "MAIL_TO": config.MAIL_TO,
    }
    return [name for name, value in required.items() if not value]


def send(
    subject: str,
    html_body: str,
    *,
    chart_png: bytes | None = None,
    chart_cid: str | None = None,
    attachment_name: str = "ramp-trend.png",
) -> None:
    """Deliver one report. ``chart_cid`` must be the value used in the HTML."""
    missing = missing_settings()
    if missing:
        raise MailError(f"missing required secrets: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(("UW Parking Watch", config.SMTP_USER))
    message["To"] = config.MAIL_TO
    message.set_content(
        "This report is HTML-only. Open it in an HTML-capable mail client, "
        f"or read the source page directly: {config.SOURCE_URL}"
    )
    message.add_alternative(html_body, subtype="html")

    if chart_png and chart_cid:
        # Attach to the HTML part so the cid: reference resolves inline, and keep
        # it downloadable for clients that block inline images.
        html_part = message.get_payload()[-1]
        html_part.add_related(
            chart_png,
            maintype="image",
            subtype="png",
            cid=f"<{chart_cid}>",
            filename=attachment_name,
            disposition="inline",
        )

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context) as smtp:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(
            "SMTP login rejected. For Gmail the password must be a 16-character "
            "App Password (Google Account -> Security -> 2-Step Verification -> "
            f"App passwords), not the account password. Server said: {exc}"
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"could not send mail: {type(exc).__name__}: {exc}") from exc


def new_cid() -> str:
    """A Content-ID without the angle brackets, for use in ``src="cid:..."``."""
    return make_msgid()[1:-1]
