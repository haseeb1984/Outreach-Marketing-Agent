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
        limit: int = 50, offset: int = 0, search: str | None = None,
        project_id: UUID | None = None, unlinked_only: bool = False,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100 or not 0 <= offset <= 100_000:
            raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT p.id, p.workspace_id, p.name, p.company, p.role, p.contact_email, p.contact_phone_e164,
                          p.website_url, p.evidence_url, p.evidence_observed_at, p.fit_reason,
                          p.verified_facts, p.stage, p.notes, p.project_id, wp.name AS project_name, wp.status AS project_status, p.created_by, p.created_at, p.updated_at,
                          COALESCE(cc.email_suppressed, FALSE) AS email_suppressed,
                          (cc.whatsapp_opt_in_at IS NOT NULL AND cc.whatsapp_opt_in_evidence_url IS NOT NULL) AS whatsapp_opt_in_documented,
                          cc.whatsapp_account_id AS whatsapp_opt_in_account_id
                   FROM crm_prospects p
                   LEFT JOIN workspace_projects wp ON wp.id=p.project_id AND wp.workspace_id=p.workspace_id
                   LEFT JOIN outreach_contact_controls cc
                     ON cc.workspace_id=p.workspace_id AND cc.prospect_id=p.id
                   WHERE p.workspace_id=$1 AND p.archived_at IS NULL
                     AND ($2::text IS NULL OR p.stage=$2)
                     AND ($5::text IS NULL OR
                          p.name ILIKE '%' || $5 || '%' OR p.company ILIKE '%' || $5 || '%' OR
                          COALESCE(p.contact_email,'') ILIKE '%' || $5 || '%' OR
                          COALESCE(p.contact_phone_e164,'') ILIKE '%' || $5 || '%' OR
                          COALESCE(p.role,'') ILIKE '%' || $5 || '%' OR p.website_url ILIKE '%' || $5 || '%' OR COALESCE(wp.name,'') ILIKE '%' || $5 || '%')
                     AND ($6::uuid IS NULL OR p.project_id=$6)
                     AND (NOT $7::boolean OR p.project_id IS NULL)
                   ORDER BY p.updated_at DESC, p.id
                   LIMIT $3 OFFSET $4""",
                workspace_id, stage, limit, offset, search.strip()[:120] if search and search.strip() else None,
                project_id, unlinked_only,
            )
        return [self._serialize(dict(row)) for row in rows]

    async def create_prospect(
        self, *, workspace_id: str, created_by: UUID | str, name: str,
        company: str, website_url: str, evidence_url: str, fit_reason: str,
        role: str | None = None, contact_email: str | None = None, contact_phone_e164: str | None = None,
        verified_facts: list[str] | None = None, project_id: UUID | None = None,
    ) -> dict[str, Any]:
        facts = self._clean_facts(verified_facts)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if project_id is not None:
                    project = await conn.fetchrow("SELECT id FROM workspace_projects WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL FOR KEY SHARE", project_id, workspace_id)
                    if project is None: raise ValueError("project_not_found_or_archived")
                row = await conn.fetchrow(
                """INSERT INTO crm_prospects
                   (workspace_id, created_by, name, company, role, contact_email, contact_phone_e164,
                    website_url, evidence_url, fit_reason, verified_facts, project_id)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12)
                   RETURNING id, workspace_id, name, company, role, contact_email, contact_phone_e164,
                             website_url, evidence_url, evidence_observed_at, fit_reason,
                             verified_facts, stage, notes, project_id, created_by, created_at, updated_at""",
                workspace_id, UUID(str(created_by)), name.strip(), company.strip(),
                role.strip() if role else None, contact_email.strip() if contact_email else None,
                contact_phone_e164.strip() if contact_phone_e164 else None,
                website_url.strip(), evidence_url.strip(), fit_reason.strip(),
                json.dumps(facts), project_id,
                )
        return self._serialize(dict(row))

    async def update_prospect(
        self, *, workspace_id: str, prospect_id: UUID, stage: str | None = None, notes: str | None = None,
        name: str | None = None, company: str | None = None, role: str | None = None,
        contact_email: str | None = None, contact_phone_e164: str | None = None,
        website_url: str | None = None, evidence_url: str | None = None, fit_reason: str | None = None,
        project_id: UUID | None = None, project_id_supplied: bool = False,
    ) -> dict[str, Any] | None:
        if all(value is None for value in (stage, notes, name, company, role, contact_email, contact_phone_e164, website_url, evidence_url, fit_reason)) and not project_id_supplied:
            raise ValueError("no_updates_supplied")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if project_id_supplied and project_id is not None:
                    project = await conn.fetchrow("""SELECT id FROM workspace_projects WHERE id=$1 AND workspace_id=$2 AND (archived_at IS NULL OR EXISTS (SELECT 1 FROM crm_prospects WHERE id=$3 AND workspace_id=$2 AND project_id=$1)) FOR KEY SHARE""", project_id, workspace_id, prospect_id)
                    if project is None: raise ValueError("project_not_found_or_archived")
                row = await conn.fetchrow(
                """UPDATE crm_prospects
                   SET stage=COALESCE($3,stage), notes=COALESCE($4,notes),
                       name=COALESCE($5,name), company=COALESCE($6,company), role=COALESCE($7,role),
                       contact_email=COALESCE($8,contact_email), contact_phone_e164=COALESCE($9,contact_phone_e164),
                       website_url=COALESCE($10,website_url), evidence_url=COALESCE($11,evidence_url),
                       fit_reason=COALESCE($12,fit_reason), project_id=CASE WHEN $13 THEN $14 ELSE project_id END, updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL
                   RETURNING id, workspace_id, name, company, role, contact_email, contact_phone_e164,
                             website_url, evidence_url, evidence_observed_at, fit_reason,
                             verified_facts, stage, notes, project_id, created_by, created_at, updated_at""",
                prospect_id, workspace_id, stage, notes, name.strip() if name else None,
                company.strip() if company else None, role.strip() if role else None,
                contact_email.strip().lower() if contact_email else None,
                contact_phone_e164.strip() if contact_phone_e164 else None,
                website_url.strip() if website_url else None, evidence_url.strip() if evidence_url else None,
                fit_reason.strip() if fit_reason else None, project_id_supplied, project_id,
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


    async def find_duplicate(
        self, *, workspace_id: str, contact_email: str | None = None, evidence_url: str | None = None,
    ) -> dict[str, Any] | None:
        """Find high-confidence workspace duplicates without conflating multiple contacts at one company."""
        email = contact_email.strip().lower() if contact_email and contact_email.strip() else None
        evidence = evidence_url.strip().rstrip("/") if evidence_url and evidence_url.strip() else None
        if not email and not evidence:
            return None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, name, company, contact_email, evidence_url
                   FROM crm_prospects
                   WHERE workspace_id=$1 AND archived_at IS NULL
                     AND (($2::text IS NOT NULL AND lower(contact_email)=$2)
                       OR ($3::text IS NOT NULL AND rtrim(evidence_url, '/')=$3))
                   ORDER BY CASE WHEN $2::text IS NOT NULL AND lower(contact_email)=$2 THEN 0 ELSE 1 END,
                            updated_at DESC
                   LIMIT 1""",
                workspace_id, email, evidence,
            )
        return self._serialize(dict(row)) if row else None

    async def count_prospects(
        self, *, workspace_id: str, stage: str | None = None, search: str | None = None,
        project_id: UUID | None = None, unlinked_only: bool = False,
    ) -> int:
        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                """SELECT count(*) FROM crm_prospects p
                   LEFT JOIN workspace_projects wp ON wp.id=p.project_id AND wp.workspace_id=p.workspace_id
                   WHERE p.workspace_id=$1 AND p.archived_at IS NULL
                     AND ($2::text IS NULL OR p.stage=$2)
                     AND ($3::text IS NULL OR
                          p.name ILIKE '%' || $3 || '%' OR p.company ILIKE '%' || $3 || '%' OR
                          COALESCE(p.contact_email,'') ILIKE '%' || $3 || '%' OR
                          COALESCE(p.contact_phone_e164,'') ILIKE '%' || $3 || '%' OR
                          COALESCE(p.role,'') ILIKE '%' || $3 || '%' OR p.website_url ILIKE '%' || $3 || '%' OR
                          COALESCE(wp.name,'') ILIKE '%' || $3 || '%')
                     AND ($4::uuid IS NULL OR p.project_id=$4)
                     AND (NOT $5::boolean OR p.project_id IS NULL)""",
                workspace_id, stage, search.strip()[:120] if search and search.strip() else None,
                project_id, unlinked_only,
            )
        return int(count or 0)

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
        for key in ("id", "created_by", "project_id", "whatsapp_opt_in_account_id"):
            if row.get(key) is not None:
                row[key] = str(row[key])
        return row
