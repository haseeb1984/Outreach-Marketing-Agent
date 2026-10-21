"""Authenticated read-only subscription entitlement inspection for workspace dashboards.

This endpoint exposes the trusted server-side decision only. It does not accept
plan claims from clients, reserve quota, or make a paid operation billable.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.auth_routes import _authenticated

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
