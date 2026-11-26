"""TLS-only SMTP verification email adapter."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import hmac
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
    # Verification links always land on the public frontend. The token is placed
    # in the URL fragment so it is not sent in HTTP requests, access logs, or referrers.
    base = (base_url if base_url is not None else (
        getattr(settings, "frontend_public_url", None)
        or next((item.strip() for item in (getattr(settings, "frontend_origins", "") or "").split(",") if item.strip()), "")
    )) or ""
    parts = urlsplit(base)
    if (
        parts.scheme.lower() != "https" or not parts.hostname
        or parts.username is not None or parts.password is not None
        or parts.path not in ("", "/") or parts.query or parts.fragment
    ):
        raise ValueError("frontend_https_origin_required")
    return urlunsplit(("https", parts.netloc, "/verify-email", "", "")) + "#" + urlencode({"token": token} )

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
        frontend_origin = (
            getattr(self._settings, "frontend_public_url", None)
            or next((item.strip() for item in (getattr(self._settings, "frontend_origins", "") or "").split(",") if item.strip()), "")
        )
        link = verification_url(token, frontend_origin)
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
        # Password-reset links land on the public frontend. Keep the bearer token
        # in the URL fragment so it is never sent in the initial HTTP request,
        # reverse-proxy access logs, or referrer headers.
        base = (
            getattr(self._settings, "frontend_public_url", None)
            or next((item.strip() for item in (getattr(self._settings, "frontend_origins", "") or "").split(",") if item.strip()), "")
        ).strip()
        parts = urlsplit(base)
        if (
            parts.scheme.lower() != "https" or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.path not in ("", "/") or parts.query or parts.fragment
        ):
            raise ValueError("frontend_https_origin_required")
        link = urlunsplit(("https", parts.netloc, "/reset-password", "", "")) + "#" + urlencode({"token": token})
        message = EmailMessage()
        message["Subject"] = "Reset your Outreach Marketing Agent password"
        message["From"] = f'{self._settings.smtp_from_name} <{self._settings.smtp_from_email}>'
        message["To"] = recipient
        message.set_content(
            "A password reset was requested for your account.\n\n"
            + "Use this link to choose a new password: " + link + "\n\n"
            + "This link expires at " + expires_at.isoformat()
            + ". All existing sessions will be signed out. If you did not request this, ignore this email.\n"
        )
        try:
            await asyncio.to_thread(self._send_message, message)
        except Exception:
            raise EmailDeliveryFailed("smtp_delivery_failed") from None


    async def send_workspace_invitation_email(
        self, *, recipient: str, token: str, workspace_name: str, role: str, expires_at: Any,
    ) -> None:
        """Send an expiring workspace invitation to the configured frontend origin."""
        self._validate_configuration()
        if not isinstance(recipient, str) or len(recipient) > 320 or "@" not in recipient:
            raise ValueError("invalid_recipient")
        if not isinstance(workspace_name, str) or not workspace_name.strip() or len(workspace_name) > 200:
            raise ValueError("invalid_workspace_name")
        if role not in {"admin", "member", "viewer"}:
            raise ValueError("invalid_invitation_role")
        # Invitees use the Hostinger frontend route; a URL fragment keeps the
        # bearer token out of HTTP request logs and referrer headers.
        base = (self._settings.frontend_public_url or "").strip() or next(
            (item.strip() for item in (self._settings.frontend_origins or "").split(",") if item.strip()), ""
        )
        parts = urlsplit(base)
        if (parts.scheme.lower() != "https" or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.path not in ("", "/") or parts.query or parts.fragment):
            raise ValueError("frontend_https_origin_required")
        link = urlunsplit((
            "https", parts.netloc, "/invitations/accept", "",
            "",
        )) + "#token=" + token
        message = EmailMessage()
        message["Subject"] = "You're invited to an Outreach Marketing Agent workspace"
        message["From"] = f'{self._settings.smtp_from_name} <{self._settings.smtp_from_email}>'
        message["To"] = recipient
        message.set_content(
            "You have been invited to join the workspace: " + workspace_name.strip() + "\n"
            + "Your proposed role is: " + role + ".\n\n"
            + "Sign in with this email address and accept the invitation here: " + link + "\n\n"
            + "This invitation expires at " + expires_at.isoformat()
            + ". If you were not expecting this invitation, you can ignore this email.\n"
        )
        try:
            await asyncio.to_thread(self._send_message, message)
        except Exception:
            raise EmailDeliveryFailed("smtp_delivery_failed") from None

    async def test_connection(self) -> None:
        """Verify TLS and SMTP authentication without sending any message."""
        self._validate_configuration()
        try:
            await asyncio.to_thread(self._test_connection)
        except Exception:
            # Provider errors may contain host/account details; expose only a stable code.
            raise EmailDeliveryFailed("smtp_connection_test_failed") from None

    def _test_connection(self) -> None:
        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=10) as client:
            client.ehlo()
            client.starttls()
            client.ehlo()
            client.login(self._settings.smtp_username, self._settings.smtp_password)

    async def send_outreach_email(
        self, *, recipient: str, subject: str, body: str,
        delivery_id: str | None = None, workspace_id: str | None = None,
        prospect_id: str | None = None,
    ) -> None:
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
        if delivery_id is not None:
            message["X-OMA-Delivery-ID"] = delivery_id
            sender_domain = str(self._settings.smtp_from_email).rsplit("@", 1)[-1].strip().lower()
            if not sender_domain or len(sender_domain) > 253:
                raise EmailDeliveryNotConfigured("smtp_sender_domain_invalid")
            message["Message-ID"] = "<" + delivery_id + "@" + sender_domain + ">"
            if not workspace_id or not prospect_id:
                raise ValueError("delivery_context_required")
            secret = (settings.outreach_webhook_secret or "").strip()
            base = (self._settings.public_base_url or "").strip()
            parts = urlsplit(base)
            if len(secret.encode("utf-8")) < 32 or parts.scheme.lower() != "https" or not parts.hostname:
                raise EmailDeliveryNotConfigured("email_unsubscribe_endpoint_not_configured")
            payload = (workspace_id + "\n" + prospect_id + "\n" + recipient.strip().casefold()).encode("utf-8")
            encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
            signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
            token = encoded + "." + signature
            unsubscribe_url = urlunsplit((
                "https", parts.netloc, parts.path.rstrip("/") + "/api/v1/webhooks/email/unsubscribe",
                urlencode({"token": token}), "",
            ))
            message["List-Unsubscribe"] = "<" + unsubscribe_url + ">"
            message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
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