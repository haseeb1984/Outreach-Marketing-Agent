"""Workspace-scoped prospect CRM persistence; authorization belongs in the HTTP boundary."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID


class ProspectStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def list_prospects(
        self, *, workspace_id: str, stage: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100 or not 0 <= offset <= 100_000:
            raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, workspace_id, name, company, role, contact_email,
                          website_url, evidence_url, evidence_observed_at, fit_reason,
                          verified_facts, stage, notes, created_by, created_at, updated_at
                   FROM crm_prospects
                   WHERE workspace_id=$1 AND archived_at IS NULL
                     AND ($2::text IS NULL OR stage=$2)
                   ORDER BY updated_at DESC, id
                   LIMIT $3 OFFSET $4""",
                workspace_id, stage, limit, offset,
            )
        return [self._serialize(dict(row)) for row in rows]

    async def create_prospect(
        self, *, workspace_id: str, created_by: UUID | str, name: str,
        company: str, website_url: str, evidence_url: str, fit_reason: str,
        role: str | None = None, contact_email: str | None = None,
        verified_facts: list[str] | None = None,
    ) -> dict[str, Any]:
        facts = self._clean_facts(verified_facts)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO crm_prospects
                   (workspace_id, created_by, name, company, role, contact_email,
                    website_url, evidence_url, fit_reason, verified_facts)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
                   RETURNING id, workspace_id, name, company, role, contact_email,
                             website_url, evidence_url, evidence_observed_at, fit_reason,
                             verified_facts, stage, notes, created_by, created_at, updated_at""",
                workspace_id, UUID(str(created_by)), name.strip(), company.strip(),
                role.strip() if role else None, contact_email.strip() if contact_email else None,
                website_url.strip(), evidence_url.strip(), fit_reason.strip(),
                json.dumps(facts),
            )
        return self._serialize(dict(row))

    async def update_prospect(
        self, *, workspace_id: str, prospect_id: UUID, stage: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        if stage is None and notes is None:
            raise ValueError("no_updates_supplied")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE crm_prospects
                   SET stage=COALESCE($3,stage), notes=COALESCE($4,notes), updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL
                   RETURNING id, workspace_id, name, company, role, contact_email,
                             website_url, evidence_url, evidence_observed_at, fit_reason,
                             verified_facts, stage, notes, created_by, created_at, updated_at""",
                prospect_id, workspace_id, stage, notes,
            )
        return self._serialize(dict(row)) if row else None

    async def archive_prospect(self, *, workspace_id: str, prospect_id: UUID) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE crm_prospects SET archived_at=now(), updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL""",
                prospect_id, workspace_id,
            )
        return result.endswith(" 1")

    @staticmethod
    def _clean_facts(value: list[str] | None) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or len(value) > 30:
            raise ValueError("verified_facts_invalid")
        cleaned = list(dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip()))
        if any(len(item) > 1000 for item in cleaned):
            raise ValueError("verified_fact_too_long")
        return cleaned

    @staticmethod
    def _serialize(row: dict[str, Any]) -> dict[str, Any]:
        facts = row.get("verified_facts")
        if isinstance(facts, str):
            try:
                facts = json.loads(facts)
            except json.JSONDecodeError:
                facts = []
        row["verified_facts"] = facts if isinstance(facts, list) else []
        for key in ("id", "created_by"):
            if row.get(key) is not None:
                row[key] = str(row[key])
        return row
