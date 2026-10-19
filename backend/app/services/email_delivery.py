"""TLS-only SMTP verification email adapter."""
from __future__ import annotations
import asyncio
import smtplib
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit
from app.core.config import settings

class EmailDeliveryNotConfigured(RuntimeError):
    pass

def verification_url(token: str, base_url: str | None = None) -> str:
    base = (base_url if base_url is not None else settings.public_base_url) or ""
    parts = urlsplit(base)
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ValueError("public_https_origin_required")
    path = parts.path.rstrip("/") + "/verify-email"
    return urlunsplit(("https", parts.netloc, path, urlencode({"token": token}), ""))

class SMTPEmailDelivery:
    def __init__(self, configuration: Any = settings) -> None:
        self._settings = configuration

    def _validate_configuration(self) -> None:
        required = (self._settings.smtp_host, self._settings.smtp_username, self._settings.smtp_password, self._settings.smtp_from_email)
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise EmailDeliveryNotConfigured("smtp_configuration_incomplete")
        port = self._settings.smtp_port
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise EmailDeliveryNotConfigured("smtp_port_invalid")
        if self._settings.smtp_starttls is not True:
            raise EmailDeliveryNotConfigured("smtp_tls_required")

    async def send_verification_email(self, *, recipient: str, token: str, expires_at: Any) -> None:
        self._validate_configuration()
        if not isinstance(recipient, str) or len(recipient) > 320 or "@" not in recipient:
            raise ValueError("invalid_recipient")
        link = verification_url(token, self._settings.public_base_url)
        message = EmailMessage()
        message["Subject"] = "Verify your Outreach Marketing Agent account"
        message["From"] = f'{self._settings.smtp_from_name} <{self._settings.smtp_from_email}>'
        message["To"] = recipient
        message.set_content("Verify your email address to activate your account.\n\nOpen this link: " + link + "\n\nThis link expires at " + expires_at.isoformat() + ". If you did not request this, ignore this email.\n")
        await asyncio.to_thread(self._send_message, message)

    def _send_message(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=10) as client:
            client.ehlo()
            client.starttls()
            client.ehlo()
            client.login(self._settings.smtp_username, self._settings.smtp_password)
            client.send_message(message)