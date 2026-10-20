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
        self, *, workspace_id: str, user_id: str, channel: str,
        client_business: str, client_offer: str, prospect_name: str,
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
            row = await connection.fetchrow(
                """INSERT INTO workspace_outreach_drafts
                   (workspace_id, created_by, channel, client_business, client_offer,
                    prospect_name, prospect_evidence_url, verified_relevance,
                    verified_facts, call_to_action, subject, body,
                    whatsapp_opt_in_confirmed)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13)
                   RETURNING *""",
                workspace_id, UUID(str(user_id)), channel, client_business.strip(),
                client_offer.strip(), prospect_name.strip(), prospect_evidence_url.strip(),
                verified_relevance.strip(), json.dumps(draft["verified_facts_used"]),
                call_to_action.strip(), draft["subject"], draft["body"],
                whatsapp_opt_in_confirmed,
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
        return self._public(row) if row is not None else None

    @staticmethod
    def _public(row: Any) -> dict[str, Any]:
        if row is None:
            raise ValueError("draft_not_found")
        result = dict(row)
        for key in ("id", "workspace_id", "created_by", "reviewed_by"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        for key in ("created_at", "updated_at", "reviewed_at"):
            if result.get(key) is not None:
                result[key] = result[key].isoformat()
        if isinstance(result.get("verified_facts"), str):
            result["verified_facts"] = json.loads(result["verified_facts"])
        return result
