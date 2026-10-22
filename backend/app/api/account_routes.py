"""Authenticated account data export limited to the current user's active workspaces."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.auth_routes import _authenticated

router = APIRouter(prefix="/api/v1/account", tags=["account privacy"])
_MAX_EXPORT_ROWS = 10000


@router.get("/export")
async def export_account_data(request: Request) -> JSONResponse:
    """Download an export of the account and data in its active workspaces.

    Password hashes, session tokens, invitation tokens, provider credentials and raw
    payment details are deliberately excluded. Each query is scoped to active membership.
    """
    _, _, session = await _authenticated(request)
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="account_export_not_configured")
    user_id = session["user_id"]
    try:
        async with pool.acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                user = await conn.fetchrow(
                    """SELECT id,email,status,created_at,updated_at,last_login_at
                       FROM app_users WHERE id=$1""",
                    user_id,
                )
                memberships = await conn.fetch(
                    """SELECT w.id AS workspace_id,w.created_at AS workspace_created_at,
                              m.role,m.created_at AS membership_created_at
                       FROM workspaces w JOIN workspace_memberships m ON m.workspace_id=w.id
                       WHERE m.user_id=$1 AND m.status='active'
                       ORDER BY w.created_at,w.id LIMIT 100""",
                    user_id,
                )
                workspace_ids = [row["workspace_id"] for row in memberships]
                export = {
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "account": dict(user) if user is not None else None,
                    "workspaces": [dict(row) for row in memberships],
                    "projects": [],
                    "prospects": [],
                    "campaigns": [],
                    "drafts": [],
                    "deliveries": [],
                    "contact_controls": [],
                    "inbound_messages": [],
                    "account_audit_events": [],
                    "limits": {
                        "max_rows_per_collection": _MAX_EXPORT_ROWS,
                        "note": "Collections are capped to protect service availability; if any collection reaches the cap, request a larger operator-assisted export.",
                    },
                }
                if workspace_ids:
                    queries = {
                        "projects": """SELECT id,workspace_id,name,website_url,business_model,target_market,
                            language,audience,offer,conversion_goal,brand_voice,competitors,status,created_at,updated_at
                            FROM workspace_projects WHERE workspace_id=ANY($1::text[])
                            ORDER BY created_at,id LIMIT $2""",
                        "prospects": """SELECT id,workspace_id,name,company,role,contact_email,website_url,
                            evidence_url,evidence_observed_at,fit_reason,verified_facts,stage,notes,created_at,updated_at,archived_at
                            FROM crm_prospects WHERE workspace_id=ANY($1::text[])
                            ORDER BY created_at,id LIMIT $2""",
                        "campaigns": """SELECT id,workspace_id,name,client_business,client_offer,target_customer_profile,
                            status,created_at,updated_at FROM outreach_campaigns
                            WHERE workspace_id=ANY($1::text[]) ORDER BY created_at,id LIMIT $2""",
                        "drafts": """SELECT id,workspace_id,campaign_id,prospect_id,channel,subject,body,
                            source_evidence_url,verified_facts_used,status,review_note,reviewed_at,created_at,updated_at
                            FROM outreach_drafts WHERE workspace_id=ANY($1::text[])
                            ORDER BY created_at,id LIMIT $2""",
                        "deliveries": """SELECT id,workspace_id,draft_id,channel,status,attempt_count,error_code,
                            queued_at,processing_at,sent_at,updated_at FROM outreach_deliveries
                            WHERE workspace_id=ANY($1::text[]) ORDER BY queued_at,id LIMIT $2""",
                        "contact_controls": """SELECT workspace_id,prospect_id,email_suppressed,whatsapp_opt_in_at,
                            whatsapp_opt_in_evidence_url,updated_at FROM outreach_contact_controls
                            WHERE workspace_id=ANY($1::text[]) ORDER BY workspace_id,prospect_id LIMIT $2""",
                        "inbound_messages": """SELECT id,workspace_id,prospect_id,provider,provider_event_id,
                            provider_message_id,in_reply_to_provider_message_id,channel,direction,body,occurred_at,received_at
                            FROM outreach_conversation_messages WHERE workspace_id=ANY($1::text[])
                            ORDER BY occurred_at,id LIMIT $2""",
                    }
                    for collection, query in queries.items():
                        rows = await conn.fetch(query, workspace_ids, _MAX_EXPORT_ROWS)
                        export[collection] = [dict(row) for row in rows]
                    audit_rows = await conn.fetch(
                        """SELECT workspace_id,event_type,outcome,created_at
                           FROM security_audit_events
                           WHERE actor_user_id=$1 AND (workspace_id=ANY($2::text[]) OR workspace_id IS NULL)
                           ORDER BY created_at LIMIT $3""",
                        user_id, workspace_ids, _MAX_EXPORT_ROWS,
                    )
                    export["account_audit_events"] = [dict(row) for row in audit_rows]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="account_export_unavailable") from None

    payload = jsonable_encoder(export)
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": 'attachment; filename="outreach-marketing-agent-data-export.json"',
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )
