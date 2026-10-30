"""Fail-closed WhatsApp send eligibility checks.

This module does not send messages. A future provider sender must call this policy
immediately before dispatch and must keep outbound WhatsApp disabled until that
sender is integrated, reviewed, and verified against Meta sandbox/live requirements.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import json
from typing import Any
from uuid import UUID


CUSTOMER_SERVICE_WINDOW_SECONDS = 24 * 60 * 60
_E164_PHONE = re.compile(r"^\+[1-9][0-9]{6,14}$")


class WhatsAppSendPolicy:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def evaluate(
        self,
        *,
        workspace_id: str,
        account_id: UUID,
        prospect_id: UUID,
        draft_id: UUID,
        template_name: str | None = None,
        language_code: str | None = None,
        template_parameters: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return an eligibility decision; missing or ambiguous state fails closed."""
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("timezone_required")

        async with self._pool.acquire() as conn:
            account = await conn.fetchrow(
                """SELECT id, (encrypted_access_token IS NOT NULL) AS has_credentials
                   FROM workspace_whatsapp_accounts
                   WHERE id=$1 AND workspace_id=$2 AND status='active'""",
                account_id,
                workspace_id,
            )
            if account is None:
                return {"allowed": False, "reason": "whatsapp_account_not_active"}
            if not account["has_credentials"]:
                return {"allowed": False, "reason": "whatsapp_account_credentials_missing"}

            prospect = await conn.fetchrow(
                """SELECT p.id,p.contact_phone_e164,p.stage,
                          cc.whatsapp_opt_in_at,cc.whatsapp_opt_in_evidence_url,cc.whatsapp_account_id
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

            raw_phone = prospect["contact_phone_e164"]
            if not isinstance(raw_phone, str) or not _E164_PHONE.fullmatch(raw_phone):
                return {"allowed": False, "reason": "prospect_whatsapp_phone_invalid"}
            phone = raw_phone[1:]
            if prospect["whatsapp_opt_in_at"] is None or not prospect["whatsapp_opt_in_evidence_url"]:
                return {"allowed": False, "reason": "documented_whatsapp_opt_in_required"}
            if str(prospect["whatsapp_account_id"] or "") != str(account_id):
                return {"allowed": False, "reason": "whatsapp_opt_in_for_account_required"}

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

            draft = await conn.fetchrow(
                """SELECT d.id
                   FROM outreach_drafts d
                   JOIN outreach_campaigns c
                     ON c.id=d.campaign_id AND c.workspace_id=d.workspace_id
                   WHERE d.id=$1 AND d.workspace_id=$2 AND d.prospect_id=$3
                     AND d.channel='whatsapp' AND d.status='approved'
                     AND c.status='active'""",
                draft_id,
                workspace_id,
                prospect_id,
            )
            if draft is None:
                return {"allowed": False, "reason": "approved_whatsapp_draft_required"}

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
                """SELECT id,template_name,language_code,provider_template_id,components
                   FROM whatsapp_message_templates
                   WHERE workspace_id=$1 AND account_id=$2
                     AND template_name=$3 AND language_code=$4
                     AND status='approved' AND verified_at IS NOT NULL
                     AND provider_template_id IS NOT NULL
                     AND btrim(provider_template_id) <> ''""",
                workspace_id,
                account_id,
                template_name,
                language_code,
            )
            if template is None:
                return {"allowed": False, "reason": "approved_provider_template_not_found"}

            raw_components = template["components"]
            if isinstance(raw_components, str):
                try:
                    raw_components = json.loads(raw_components)
                except (TypeError, ValueError):
                    return {"allowed": False, "reason": "approved_template_schema_invalid"}
            expected: dict[str, int] = {}
            expected_buttons: dict[int, int] = {}
            if not isinstance(raw_components, list):
                return {"allowed": False, "reason": "approved_template_schema_invalid"}
            for component in raw_components:
                if not isinstance(component, dict):
                    return {"allowed": False, "reason": "approved_template_schema_invalid"}
                kind = str(component.get("type") or "").lower()
                if kind == "buttons":
                    buttons = component.get("buttons")
                    if not isinstance(buttons, list) or len(buttons) > 10:
                        return {"allowed": False, "reason": "approved_template_schema_invalid"}
                    for index, button in enumerate(buttons):
                        if not isinstance(button, dict):
                            return {"allowed": False, "reason": "approved_template_schema_invalid"}
                        button_type = str(button.get("type") or "").upper()
                        url_value = button.get("url")
                        if button_type == "URL" and isinstance(url_value, str):
                            matches = re.findall(r"{{([1-9][0-9]?)}}", url_value)
                            if matches:
                                if len(matches) != 1 or int(matches[0]) != 1:
                                    return {"allowed": False, "reason": "whatsapp_template_button_schema_unsupported"}
                                expected_buttons[index] = 1
                        elif button_type not in {"QUICK_REPLY", "PHONE_NUMBER", "COPY_CODE"}:
                            return {"allowed": False, "reason": "whatsapp_template_button_type_unsupported"}
                    continue
                if kind not in {"body", "header"}:
                    continue
                if kind == "header" and str(component.get("format") or "").upper() != "TEXT":
                    return {"allowed": False, "reason": "whatsapp_template_media_header_not_supported"}
                text_value = component.get("text")
                if isinstance(text_value, str):
                    indexes = [int(value) for value in re.findall(r"{{([1-9][0-9]?)}}", text_value)]
                    expected[kind] = max(indexes, default=0)
            supplied = template_parameters or {}
            if not isinstance(supplied, dict) or set(supplied) - {"body", "header", "buttons"}:
                return {"allowed": False, "reason": "whatsapp_template_parameters_invalid"}
            for kind in ("body", "header"):
                values = supplied.get(kind, [])
                if not isinstance(values, list) or len(values) != expected.get(kind, 0):
                    return {"allowed": False, "reason": "whatsapp_template_parameter_count_mismatch"}
                if any(not isinstance(value, str) or not value.strip() or len(value) > 1024 for value in values):
                    return {"allowed": False, "reason": "whatsapp_template_parameter_invalid"}
            supplied_buttons = supplied.get("buttons", [])
            if not isinstance(supplied_buttons, list) or len(supplied_buttons) != len(expected_buttons):
                return {"allowed": False, "reason": "whatsapp_template_button_parameter_count_mismatch"}
            seen_button_indexes: set[int] = set()
            for button in supplied_buttons:
                if not isinstance(button, dict) or set(button) != {"index", "sub_type", "value"}:
                    return {"allowed": False, "reason": "whatsapp_template_button_parameters_invalid"}
                index, value = button.get("index"), button.get("value")
                if (isinstance(index, bool) or not isinstance(index, int)
                    or index not in expected_buttons or index in seen_button_indexes
                    or button.get("sub_type") != "url" or expected_buttons[index] != 1
                    or not isinstance(value, str) or not value.strip() or len(value) > 2000):
                    return {"allowed": False, "reason": "whatsapp_template_button_parameters_invalid"}
                seen_button_indexes.add(index)
            if seen_button_indexes != set(expected_buttons):
                return {"allowed": False, "reason": "whatsapp_template_button_parameter_count_mismatch"}
            return {
                "allowed": True,
                "reason": "approved_template_outside_customer_service_window",
                "requires_approved_template": True,
                "template_parameters": supplied,
                "required_template_parameters": expected,
                # Dispatch must use the exact canonical identity verified above,
                # never template metadata copied from the mutable queue payload.
                "template_id": str(template["id"]),
                "provider_template_id": str(template["provider_template_id"]),
                "template_name": str(template["template_name"]),
                "language_code": str(template["language_code"]),
            }
