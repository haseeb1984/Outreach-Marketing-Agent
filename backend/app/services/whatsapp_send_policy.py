"""Fail-closed WhatsApp send eligibility checks.

This module does not send messages. A future provider sender must call this policy
immediately before dispatch and must keep outbound WhatsApp disabled until that
sender is integrated, reviewed, and verified against Meta sandbox/live requirements.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID


CUSTOMER_SERVICE_WINDOW_SECONDS = 24 * 60 * 60


class WhatsAppSendPolicy:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def evaluate(
        self,
        *,
        workspace_id: str,
        account_id: UUID,
        prospect_id: UUID,
        template_name: str | None = None,
        language_code: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return an eligibility decision; missing or ambiguous state fails closed."""
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("timezone_required")

        async with self._pool.acquire() as conn:
            account = await conn.fetchrow(
                """SELECT id FROM workspace_whatsapp_accounts
                   WHERE id=$1 AND workspace_id=$2 AND status='active'""",
                account_id,
                workspace_id,
            )
            if account is None:
                return {"allowed": False, "reason": "whatsapp_account_not_active"}

            prospect = await conn.fetchrow(
                """SELECT p.id,p.contact_phone_e164,p.stage,
                          cc.whatsapp_opt_in_at,cc.whatsapp_opt_in_evidence_url
                   FROM crm_prospects p
                   LEFT JOIN outreach_contact_controls cc
                     ON cc.workspace_id=p.workspace_id AND cc.prospect_id=p.id
                   WHERE p.id=$1 AND p.workspace_id=$2 AND p.archived_at IS NULL""",
                prospect_id,
                workspace_id,
            )
            if prospect is None:
                return {"allowed": False, "reason": "prospect_not_found"}
            if prospect["stage"] == "do_not_contact":
                return {"allowed": False, "reason": "contact_suppressed"}

            phone = "".join(ch for ch in str(prospect["contact_phone_e164"] or "") if ch.isdigit())
            if not phone:
                return {"allowed": False, "reason": "prospect_whatsapp_phone_required"}
            if prospect["whatsapp_opt_in_at"] is None or not prospect["whatsapp_opt_in_evidence_url"]:
                return {"allowed": False, "reason": "documented_whatsapp_opt_in_required"}

            preference = await conn.fetchrow(
                """SELECT opted_out_at,opted_in_at,last_inbound_at
                   FROM whatsapp_contact_preferences
                   WHERE workspace_id=$1 AND account_id=$2 AND wa_id=$3""",
                workspace_id,
                account_id,
                phone,
            )
            if preference and preference["opted_out_at"] is not None:
                opted_in_at = preference["opted_in_at"]
                if opted_in_at is None or preference["opted_out_at"] >= opted_in_at:
                    return {"allowed": False, "reason": "whatsapp_contact_opted_out"}

            last_inbound = preference["last_inbound_at"] if preference else None
            in_window = bool(
                last_inbound is not None
                and (instant - last_inbound).total_seconds() >= 0
                and (instant - last_inbound).total_seconds() < CUSTOMER_SERVICE_WINDOW_SECONDS
            )
            if in_window:
                return {
                    "allowed": True,
                    "reason": "customer_service_window_open",
                    "requires_approved_template": False,
                }

            if not template_name or not language_code:
                return {
                    "allowed": False,
                    "reason": "approved_template_required_outside_customer_service_window",
                }

            template = await conn.fetchrow(
                """SELECT provider_template_id FROM whatsapp_message_templates
                   WHERE workspace_id=$1 AND account_id=$2
                     AND template_name=$3 AND language_code=$4
                     AND status='approved' AND verified_at IS NOT NULL
                     AND provider_template_id IS NOT NULL""",
                workspace_id,
                account_id,
                template_name,
                language_code,
            )
            if template is None:
                return {"allowed": False, "reason": "approved_provider_template_not_found"}

            return {
                "allowed": True,
                "reason": "approved_template_outside_customer_service_window",
                "requires_approved_template": True,
            }
