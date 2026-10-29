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
                       AND occurred_at >= now() - ($2::int * interval '1 day')) AS inbound_replies,
                    (SELECT count(*) FROM whatsapp_inbound_messages messages
                     JOIN whatsapp_conversations conversations
                       ON conversations.id=messages.conversation_id
                      AND conversations.workspace_id=messages.workspace_id
                     WHERE messages.workspace_id=$1
                       AND messages.received_at >= now() - ($2::int * interval '1 day')) AS whatsapp_inbound_messages,
                    (SELECT count(*) FROM whatsapp_delivery_status_events
                     WHERE workspace_id=$1
                       AND received_at >= now() - ($2::int * interval '1 day')) AS whatsapp_status_events
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
            "inbound_replies": "Persisted generic inbound reply events received during the selected period; WhatsApp webhook messages are counted separately.",
            "whatsapp_inbound_messages": "Persisted inbound messages received from mapped WhatsApp accounts during the selected period; not necessarily qualified replies.",
            "whatsapp_status_events": "Persisted WhatsApp provider status event records received during the selected period; event counts are not unique campaign conversions.",
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


@router.get("/campaigns")
async def campaign_performance_analytics(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    since_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Return per-campaign persisted workflow counts, not fabricated ROI attribution."""
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
            rows = await connection.fetch(
                """SELECT c.id, c.name, c.status, c.created_at, c.updated_at,
                    (SELECT count(DISTINCT d.prospect_id) FROM outreach_drafts d
                     WHERE d.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND d.created_at >= now() - ($2::int * interval '1 day')) AS prospects_in_campaign,
                    (SELECT count(*) FROM outreach_drafts d
                     WHERE d.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND d.created_at >= now() - ($2::int * interval '1 day')
                       AND d.status='pending_approval') AS drafts_pending_approval,
                    (SELECT count(*) FROM outreach_drafts d
                     WHERE d.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND d.created_at >= now() - ($2::int * interval '1 day')
                       AND d.status='approved') AS drafts_approved,
                    (SELECT count(*) FROM outreach_drafts d
                     WHERE d.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND d.created_at >= now() - ($2::int * interval '1 day')
                       AND d.status='rejected') AS drafts_rejected,
                    (SELECT count(*) FROM outreach_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.channel='email' AND q.sent_at >= now() - ($2::int * interval '1 day')
                       AND q.status='sent') AS email_sent_marked,
                    (SELECT count(*) FROM outreach_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.channel='email' AND q.updated_at >= now() - ($2::int * interval '1 day')
                       AND q.status='failed') AS email_failed,
                    (SELECT count(*) FROM outreach_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.channel='email' AND q.updated_at >= now() - ($2::int * interval '1 day')
                       AND q.status='uncertain') AS email_uncertain,
                    (SELECT count(*) FROM outreach_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.channel='email' AND q.queued_at >= now() - ($2::int * interval '1 day')
                       AND q.status IN ('queued','processing')) AS email_pending,
                    (SELECT count(*) FROM whatsapp_outbound_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.updated_at >= now() - ($2::int * interval '1 day')
                       AND q.status IN ('sent','delivered','read')) AS whatsapp_sent_or_confirmed,
                    (SELECT count(*) FROM whatsapp_outbound_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.updated_at >= now() - ($2::int * interval '1 day')
                       AND q.status='delivered') AS whatsapp_delivered,
                    (SELECT count(*) FROM whatsapp_outbound_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.updated_at >= now() - ($2::int * interval '1 day')
                       AND q.status='read') AS whatsapp_read,
                    (SELECT count(*) FROM whatsapp_outbound_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.updated_at >= now() - ($2::int * interval '1 day')
                       AND q.status='failed') AS whatsapp_failed,
                    (SELECT count(*) FROM whatsapp_outbound_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.updated_at >= now() - ($2::int * interval '1 day')
                       AND q.status='uncertain') AS whatsapp_uncertain,
                    (SELECT count(*) FROM whatsapp_outbound_deliveries q
                     JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                     WHERE q.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND q.queued_at >= now() - ($2::int * interval '1 day')
                       AND q.status IN ('queued','processing')) AS whatsapp_pending,
                    (SELECT count(DISTINCT m.id) FROM outreach_conversation_messages m
                     JOIN outreach_drafts d ON d.prospect_id=m.prospect_id
                       AND d.workspace_id=m.workspace_id AND d.campaign_id=c.id
                     WHERE m.workspace_id=c.workspace_id AND m.direction='inbound'
                       AND m.occurred_at >= now() - ($2::int * interval '1 day')) AS replies_from_campaign_prospects,
                    (SELECT count(DISTINCT p.id) FROM crm_prospects p
                     JOIN outreach_drafts d ON d.prospect_id=p.id AND d.workspace_id=p.workspace_id
                     WHERE p.workspace_id=c.workspace_id AND d.campaign_id=c.id
                       AND d.created_at >= now() - ($2::int * interval '1 day')
                       AND p.archived_at IS NULL AND p.stage='converted') AS converted_stage_prospects
                   FROM outreach_campaigns c
                   WHERE c.workspace_id=$1 AND c.status <> 'archived'
                   ORDER BY c.updated_at DESC, c.id
                   LIMIT $3""",
                workspace_id, since_days, limit,
            )
        items = []
        for row in rows:
            item = dict(row)
            item["id"] = str(item["id"])
            item["counts"] = {
                key: int(item.pop(key))
                for key in (
                    "prospects_in_campaign", "drafts_pending_approval", "drafts_approved",
                    "drafts_rejected", "email_sent_marked", "email_failed", "email_uncertain",
                    "email_pending", "whatsapp_sent_or_confirmed", "whatsapp_delivered",
                    "whatsapp_read", "whatsapp_failed", "whatsapp_uncertain", "whatsapp_pending",
                    "replies_from_campaign_prospects", "converted_stage_prospects",
                )
            }
            items.append(item)
    except Exception:
        raise HTTPException(status_code=503, detail="campaign_analytics_unavailable") from None

    return {
        "workspace_id": workspace_id,
        "period_days": since_days,
        "items": items,
        "definitions": {
            "email_sent_marked": "SMTP adapter accepted the send operation; not proof of inbox delivery.",
            "whatsapp_sent_or_confirmed": "Outbound records currently marked sent, delivered or read; a record is counted once.",
            "replies_from_campaign_prospects": "Inbound messages from a prospect who has a draft in this campaign. This is association, not proof the campaign caused the reply; a prospect can belong to multiple campaigns.",
            "converted_stage_prospects": "Distinct prospects linked to this campaign with CRM stage converted; not verified revenue or causal attribution.",
        },
        "unavailable_metrics": [
            "provider-confirmed email inbox delivery",
            "email opens and clicks",
            "attributed signups",
            "verified sales revenue",
            "ROI",
        ],
    }
