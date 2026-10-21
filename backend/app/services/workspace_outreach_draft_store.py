"""Persistence for evidence-linked, human-reviewed workspace outreach drafts."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID
from urllib.parse import urlsplit

from app.services.prospect_outreach import draft_outreach


class WorkspaceOutreachDraftStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create(
        self, *, workspace_id: str, user_id: str, channel: str, campaign_id: UUID | None = None,
        prospect_id: UUID | None = None, client_business: str, client_offer: str, prospect_name: str,
        prospect_evidence_url: str, verified_relevance: str,
        verified_facts: list[str], call_to_action: str,
        whatsapp_opt_in_confirmed: bool = False,
    ) -> dict[str, Any]:
        """Create a draft only. This method never dispatches or schedules a message."""
        parsed = urlsplit(prospect_evidence_url)
        if (
            parsed.scheme.lower() != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment
        ):
            raise ValueError("prospect_evidence_url_must_be_https")
        draft = draft_outreach(
            channel=channel,
            client_business=client_business,
            client_offer=client_offer,
            prospect_name=prospect_name,
            prospect_evidence_url=prospect_evidence_url,
            verified_relevance=verified_relevance,
            verified_facts=verified_facts,
            call_to_action=call_to_action,
            whatsapp_opt_in_confirmed=whatsapp_opt_in_confirmed,
        )
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                if channel == "whatsapp" and prospect_id is None:
                    raise ValueError("whatsapp_consent_evidence_required")
                if prospect_id is not None:
                    prospect = await connection.fetchrow(
                        """SELECT id, campaign_id, display_name, opt_out, whatsapp_opt_in_at, whatsapp_opt_in_source, whatsapp_opt_in_evidence_url
                           FROM workspace_prospects
                           WHERE workspace_id=$1 AND id=$2
                           FOR UPDATE""",
                        workspace_id, prospect_id,
                    )
                    if prospect is None:
                        raise ValueError("linked_prospect_not_found")
                    if prospect["opt_out"]:
                        raise ValueError("prospect_opted_out")
                    if channel == "whatsapp" and not (
                        prospect["whatsapp_opt_in_at"] is not None
                        and prospect["whatsapp_opt_in_source"]
                        and prospect["whatsapp_opt_in_evidence_url"]
                    ):
                        raise ValueError("whatsapp_consent_evidence_required")
                    if campaign_id is not None and campaign_id != prospect["campaign_id"]:
                        raise ValueError("prospect_campaign_mismatch")
                    campaign_id = prospect["campaign_id"]
                    if prospect_name.strip().casefold() != prospect["display_name"].strip().casefold():
                        raise ValueError("prospect_name_mismatch")
                if campaign_id is not None:
                    campaign = await connection.fetchrow(
                        """SELECT id, status FROM workspace_campaigns
                           WHERE workspace_id=$1 AND id=$2
                           FOR UPDATE""",
                        workspace_id, campaign_id,
                    )
                    if campaign is None:
                        raise ValueError("linked_campaign_not_found")
                    if campaign["status"] not in {"draft", "active"}:
                        raise ValueError("campaign_not_open_for_drafts")
                row = await connection.fetchrow(
                    """INSERT INTO workspace_outreach_drafts
                       (workspace_id, campaign_id, prospect_id, created_by, channel, client_business, client_offer,
                        prospect_name, prospect_evidence_url, verified_relevance,
                        verified_facts, call_to_action, subject, body,
                        whatsapp_opt_in_confirmed)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13, $14, $15)
                       RETURNING *""",
                    workspace_id, campaign_id, prospect_id, UUID(str(user_id)), channel, client_business.strip(),
                    client_offer.strip(), prospect_name.strip(), prospect_evidence_url.strip(),
                    verified_relevance.strip(), json.dumps(draft["verified_facts_used"]),
                    call_to_action.strip(), draft["subject"], draft["body"],
                    whatsapp_opt_in_confirmed,
                )
                await connection.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id, actor_user_id, event_type, outcome, metadata)
                       VALUES ($1, $2, 'outreach_draft.created', 'success', $3::jsonb)""",
                    workspace_id, UUID(str(user_id)),
                    json.dumps({"draft_id": str(row["id"]), "channel": channel}),
                )
        return self._public(row)

    async def list_for_workspace(
        self, *, workspace_id: str, limit: int = 50, status: str | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("invalid_limit")
        if status is not None and status not in {
            "draft_requires_human_review", "approved", "rejected"
        }:
            raise ValueError("invalid_status")
        async with self._pool.acquire() as connection:
            if status is None:
                rows = await connection.fetch(
                    """SELECT * FROM workspace_outreach_drafts
                       WHERE workspace_id=$1 ORDER BY created_at DESC, id DESC LIMIT $2""",
                    workspace_id, limit,
                )
            else:
                rows = await connection.fetch(
                    """SELECT * FROM workspace_outreach_drafts
                       WHERE workspace_id=$1 AND status=$2
                       ORDER BY created_at DESC, id DESC LIMIT $3""",
                    workspace_id, status, limit,
                )
        return [self._public(row) for row in rows]

    async def review(
        self, *, workspace_id: str, draft_id: UUID, reviewer_id: str,
        decision: str, note: str | None = None,
    ) -> dict[str, Any] | None:
        """Make one irreversible review decision for a pending draft; never send it."""
        if decision not in {"approved", "rejected"}:
            raise ValueError("invalid_review_decision")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """UPDATE workspace_outreach_drafts
                       SET status=$3, reviewed_by=$4, review_note=$5,
                           reviewed_at=now(), updated_at=now()
                       WHERE workspace_id=$1 AND id=$2
                         AND status='draft_requires_human_review'
                       RETURNING *""",
                    workspace_id, draft_id, decision,
                    UUID(str(reviewer_id)), note.strip() if note else None,
                )
                if row is not None:
                    await connection.execute(
                        """INSERT INTO security_audit_events
                           (workspace_id, actor_user_id, event_type, outcome, metadata)
                           VALUES ($1, $2, 'outreach_draft.reviewed', 'success', $3::jsonb)""",
                        workspace_id, UUID(str(reviewer_id)),
                        json.dumps({"draft_id": str(draft_id), "decision": decision}),
                    )
        return self._public(row) if row is not None else None

    @staticmethod
    def _public(row: Any) -> dict[str, Any]:
        if row is None:
            raise ValueError("draft_not_found")
        result = dict(row)
        for key in ("id", "workspace_id", "campaign_id", "prospect_id", "created_by", "reviewed_by"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        for key in ("created_at", "updated_at", "reviewed_at"):
            if result.get(key) is not None:
                result[key] = result[key].isoformat()
        if isinstance(result.get("verified_facts"), str):
            result["verified_facts"] = json.loads(result["verified_facts"])
        return result
