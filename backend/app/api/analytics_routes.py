"""Workspace-scoped, database-backed campaign activity summaries.

Only persisted events are counted. This endpoint deliberately does not estimate clicks,
sales, revenue, or ROI when no verified integration data exists.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.auth_routes import _authenticated

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary")
async def analytics_summary(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    since_days: int = Query(default=30, ge=1, le=365),
):
    """Return persisted workspace activity counts without fabricating marketing outcomes."""
    _, _, session = await _authenticated(request)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="viewer"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")

    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="analytics_service_not_configured")

    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT
                    (SELECT count(*) FROM crm_prospects
                     WHERE workspace_id=$1 AND archived_at IS NULL) AS prospects_total,
                    (SELECT count(*) FROM crm_prospects
                     WHERE workspace_id=$1 AND archived_at IS NULL AND stage='qualified') AS prospects_qualified,
                    (SELECT count(*) FROM crm_prospects
                     WHERE workspace_id=$1 AND archived_at IS NULL AND stage='replied') AS prospects_replied,
                    (SELECT count(*) FROM crm_prospects
                     WHERE workspace_id=$1 AND archived_at IS NULL AND stage='converted') AS prospects_converted,
                    (SELECT count(*) FROM outreach_campaigns
                     WHERE workspace_id=$1 AND status='active') AS campaigns_active,
                    (SELECT count(*) FROM outreach_drafts
                     WHERE workspace_id=$1 AND status='pending_approval') AS drafts_pending_approval,
                    (SELECT count(*) FROM outreach_drafts
                     WHERE workspace_id=$1 AND status='approved') AS drafts_approved,
                    (SELECT count(*) FROM outreach_deliveries
                     WHERE workspace_id=$1 AND status='sent'
                       AND sent_at >= now() - ($2::int * interval '1 day')) AS emails_marked_sent,
                    (SELECT count(*) FROM outreach_deliveries
                     WHERE workspace_id=$1 AND status='failed'
                       AND updated_at >= now() - ($2::int * interval '1 day')) AS deliveries_failed,
                    (SELECT count(*) FROM outreach_deliveries
                     WHERE workspace_id=$1 AND status='uncertain'
                       AND updated_at >= now() - ($2::int * interval '1 day')) AS deliveries_uncertain,
                    (SELECT count(*) FROM outreach_deliveries
                     WHERE workspace_id=$1 AND status IN ('queued','processing')) AS deliveries_pending,
                    (SELECT count(*) FROM outreach_conversation_messages
                     WHERE workspace_id=$1 AND direction='inbound'
                       AND occurred_at >= now() - ($2::int * interval '1 day')) AS inbound_replies
                """,
                workspace_id,
                since_days,
            )
        counts = {key: int(value) for key, value in dict(row).items()}
    except Exception:
        raise HTTPException(status_code=503, detail="analytics_query_unavailable") from None

    return {
        "workspace_id": workspace_id,
        "period_days": since_days,
        "counts": counts,
        "definitions": {
            "emails_marked_sent": "Application records marked sent after the SMTP adapter returned successfully; this is not proof of inbox delivery.",
            "inbound_replies": "Persisted inbound reply events received during the selected period.",
            "prospects_converted": "Prospects explicitly moved to the converted CRM stage; not independently verified revenue.",
        },
        "unavailable_metrics": [
            "provider-confirmed delivery",
            "opens",
            "clicks",
            "attributed signups",
            "verified sales revenue",
            "ROI",
        ],
    }
