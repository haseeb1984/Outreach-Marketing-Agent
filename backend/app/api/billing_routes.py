"""Authenticated read-only subscription entitlement inspection for workspace dashboards.

This endpoint exposes the trusted server-side decision only. It does not accept
plan claims from clients, reserve quota, or make a paid operation billable.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth_routes import _authenticated, _check_csrf

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/entitlements")
async def get_workspace_entitlement(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    feature: str = Query(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$"),
):
    """Return one feature decision from a verified subscription snapshot."""
    _, _, session = await _authenticated(request)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="viewer"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")

    subscription_store = getattr(request.app.state, "subscription_store", None)
    if subscription_store is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        decision = await subscription_store.get_entitlement(
            workspace_id=workspace_id, feature=feature
        )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    return {
        "workspace_id": workspace_id,
        "feature": feature,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "remaining": decision.remaining,
    }


@router.get("/account")
async def get_billing_account(request: Request, workspace_id: str = Query(min_length=1, max_length=200)):
    """Expose the verified plan, current-period quota usage and invoice history to workspace viewers."""
    _, _, session = await _authenticated(request)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(user_id=session["user_id"], workspace_id=workspace_id, minimum_role="viewer"):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        async with pool.acquire() as conn:
            subscription = await conn.fetchrow(
                """SELECT s.provider,s.provider_customer_id,s.provider_subscription_id,s.plan_slug,
                          s.status,s.billing_period_starts_at,s.billing_period_ends_at,s.entitlements,
                          p.name AS plan_name,p.display_price,p.currency,p.billing_interval
                   FROM workspace_subscriptions s LEFT JOIN platform_billing_plans p ON p.slug=s.plan_slug
                   WHERE s.workspace_id=$1""", workspace_id)
            usage = await conn.fetch(
                """SELECT feature,count(*) FILTER(WHERE status='consumed')::bigint AS consumed,
                          count(*) FILTER(WHERE status='reserved')::bigint AS reserved,
                          count(*) FILTER(WHERE status='released')::bigint AS released
                   FROM feature_usage_reservations WHERE workspace_id=$1
                     AND billing_period_starts_at=(SELECT billing_period_starts_at FROM workspace_subscriptions WHERE workspace_id=$1)
                     AND billing_period_ends_at=(SELECT billing_period_ends_at FROM workspace_subscriptions WHERE workspace_id=$1)
                   GROUP BY feature ORDER BY feature""", workspace_id)
            transactions = await conn.fetch(
                """SELECT transaction_id,invoice_number,status,currency_code,total_minor,billed_at,updated_at
                   FROM billing_transactions WHERE workspace_id=$1
                   ORDER BY billed_at DESC,transaction_id DESC LIMIT 100""", workspace_id)
        if subscription is None:
            return {"workspace_id": workspace_id, "subscription": None, "usage": [], "invoices": []}
        sub = dict(subscription)
        entitlements = sub.get("entitlements")
        if isinstance(entitlements, str):
            entitlements = json.loads(entitlements)
        sub["entitlements"] = entitlements if isinstance(entitlements, dict) else {}
        for key in ("billing_period_starts_at", "billing_period_ends_at"):
            if sub.get(key) is not None:
                sub[key] = sub[key].isoformat()
        return {"workspace_id": workspace_id, "subscription": sub, "usage": [dict(row) for row in usage],
            "invoices": [{"transaction_id": row["transaction_id"], "invoice_number": row["invoice_number"],
                "status": row["status"], "currency_code": row["currency_code"], "total_minor": str(row["total_minor"]) if row["total_minor"] is not None else None,
                "billed_at": row["billed_at"].isoformat() if row["billed_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None} for row in transactions]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="billing_account_unavailable") from None
