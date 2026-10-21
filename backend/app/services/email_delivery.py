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


class EmailDeliveryFailed(RuntimeError):
    """Sanitized delivery failure; never expose provider exception details."""
    pass

def verification_url(token: str, base_url: str | None = None) -> str:
    base = (base_url if base_url is not None else settings.public_base_url) or ""
    parts = urlsplit(base)
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ValueError("public_https_origin_required")
    path = parts.path.rstrip("/") + "/api/v1/auth/verify-email"
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
        try:
            await asyncio.to_thread(self._send_message, message)
        except Exception:
            # SMTP/client exceptions may contain server responses or sensitive context.
            # Return a stable error code; never chain or log the original exception here.
            raise EmailDeliveryFailed("smtp_delivery_failed") from None

    async def send_password_reset_email(self, *, recipient: str, token: str, expires_at: Any) -> None:
        self._validate_configuration()
        if not isinstance(recipient, str) or len(recipient) > 320 or "@" not in recipient:
            raise ValueError("invalid_recipient")
        base = (self._settings.public_base_url or "").strip()
        parts = urlsplit(base)
        if (
            parts.scheme.lower() != "https" or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment
        ):
            raise ValueError("public_https_origin_required")
        link = urlunsplit((
            "https", parts.netloc, parts.path.rstrip("/") + "/reset-password",
            urlencode({"token": token}), "",
        ))
        message = EmailMessage()
        message["Subject"] = "Reset your Outreach Marketing Agent password"
        message["From"] = f'{self._settings.smtp_from_name} <{self._settings.smtp_from_email}>'
        message["To"] = recipient
        message.set_content(
            "A password reset was requested for your account.\\n\\n"
            + "Use this link to choose a new password: " + link + "\\n\\n"
            + "This link expires at " + expires_at.isoformat()
            + ". All existing sessions will be signed out. If you did not request this, ignore this email.\\n"
        )
        try:
            await asyncio.to_thread(self._send_message, message)
        except Exception:
            raise EmailDeliveryFailed("smtp_delivery_failed") from None


    async def send_outreach_email(self, *, recipient: str, subject: str, body: str) -> None:
        """Send an explicitly approved outreach email over TLS-only SMTP."""
        self._validate_configuration()
        if not isinstance(recipient, str) or len(recipient) > 320 or "@" not in recipient:
            raise ValueError("invalid_recipient")
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 300:
            raise ValueError("invalid_subject")
        if not isinstance(body, str) or not body.strip() or len(body) > 10000:
            raise ValueError("invalid_body")
        message = EmailMessage()
        message["Subject"] = subject.strip()
        message["From"] = f'{self._settings.smtp_from_name} <{self._settings.smtp_from_email}>'
        message["To"] = recipient
        message.set_content(body)
        try:
            await asyncio.to_thread(self._send_message, message)
        except Exception:
            raise EmailDeliveryFailed("smtp_delivery_failed") from None

    def _send_message(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=10) as client:
            client.ehlo()
            client.starttls()
            client.ehlo()
            client.login(self._settings.smtp_username, self._settings.smtp_password)
            client.send_message(message)