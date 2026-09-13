"""
Delivery step — emails the finished article over SMTP.

Gmail setup (no OAuth): enable 2-Step Verification, create an App Password at
https://myaccount.google.com/apppasswords, then set:

    SMTP_USER=you@gmail.com
    SMTP_PASS=<16-char app password>
    EMAIL_TO=reviewer@example.com      # optional, defaults to SMTP_USER; comma-separated for several
"""

import os
import smtplib
import ssl
from email.message import EmailMessage


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))


def mask_email(addresses: str) -> str:
    """a.person@gmail.com -> a***@gmail.com (run logs are committed to a public repo)."""
    masked = []
    for addr in addresses.split(","):
        local, _, domain = addr.strip().partition("@")
        masked.append(f"{local[:1]}***@{domain}" if domain else "***")
    return ", ".join(masked)


def send_article_email(subject: str, html_body: str, markdown_text: str, attachment_name: str) -> str:
    """Send HTML article with the Markdown source attached. Returns the recipient string."""
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"].replace(" ", "")  # Gmail shows app passwords with spaces
    to = os.environ.get("EMAIL_TO") or user
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(markdown_text)
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(
        markdown_text.encode("utf-8"),
        maintype="text", subtype="markdown", filename=attachment_name,
    )

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(user, password)
        server.send_message(msg)
    return to
