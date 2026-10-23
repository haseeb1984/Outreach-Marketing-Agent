"""Allowlisted platform-level SaaS administration."""
from __future__ import annotations
import json, re
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings

router = APIRouter(prefix="/api/v1/platform-admin", tags=["platform administration"])
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
PRICE = re.compile(r"^pri_[A-Za-z0-9_-]+$")

class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    price_id: str = Field(min_length=5, max_length=120)
    display_price: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, max_length=8)
    billing_interval: str | None = Field(default=None, max_length=40)
    entitlements: dict[str, Any]
    active: bool = True

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value):
        if not SLUG.fullmatch(value): raise ValueError("invalid_plan_slug")
        return value

    @field_validator("price_id")
    @classmethod
    def valid_price_id(cls, value):
        if not PRICE.fullmatch(value): raise ValueError("invalid_paddle_price_id")
        return value

    @field_validator("entitlements")
    @classmethod
    def valid_entitlements(cls, value):
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
        if len(encoded) > 100_000: raise ValueError("entitlements_too_large")
        for feature, rule in value.items():
            if not isinstance(feature, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", feature):
                raise ValueError("invalid_entitlement_feature")
            if not isinstance(rule, dict) or not isinstance(rule.get("enabled"), bool):
                raise ValueError("invalid_entitlement_rule")
            limit = rule.get("monthly_limit")
            if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 0):
                raise ValueError("invalid_monthly_limit")
        return value

def pool_for(request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None: raise HTTPException(status_code=503, detail="platform_admin_service_not_configured")
    return pool

async def require_platform_admin(request, write=False):
    _, _, session = await _authenticated(request)
    if write: _check_csrf(request, session)
    allowed = {x.strip().casefold() for x in (settings.platform_admin_emails or "").split(",") if x.strip()}
    if not allowed: raise HTTPException(status_code=503, detail="platform_admin_allowlist_not_configured")
    try:
        async with pool_for(request).acquire() as conn:
            email = await conn.fetchval("SELECT email FROM app_users WHERE id=$1::uuid AND status='active'", session["user_id"])
    except Exception:
        raise HTTPException(status_code=503, detail="platform_admin_identity_unavailable") from None
    if not isinstance(email, str) or email.strip().casefold() not in allowed:
        raise HTTPException(status_code=403, detail="platform_admin_required")
    return session

def public_plan(row):
    result = dict(row)
    entitlements = result.get("entitlements")
    if isinstance(entitlements, str): result["entitlements"] = json.loads(entitlements)
    for key in ("created_at", "updated_at"):
        if result.get(key) is not None: result[key] = result[key].isoformat()
    return result

@router.get("/overview")
async def overview(request: Request, client_limit: int = Query(default=100, ge=1, le=500), client_offset: int = Query(default=0, ge=0, le=1000000), usage_limit: int = Query(default=100, ge=1, le=500), usage_offset: int = Query(default=0, ge=0, le=1000000), audit_limit: int = Query(default=100, ge=1, le=500), audit_offset: int = Query(default=0, ge=0, le=1000000)):
    await require_platform_admin(request)
    try:
        async with pool_for(request).acquire() as conn:
            totals = await conn.fetchrow("""SELECT
              (SELECT count(*) FROM app_users WHERE status='active') AS active_users,
              (SELECT count(*) FROM workspaces) AS workspaces_total,
              (SELECT count(*) FROM workspace_subscriptions) AS subscriptions_total,
              (SELECT count(*) FROM workspace_subscriptions WHERE status IN ('active','trialing')) AS subscriptions_active,
              (SELECT count(*) FROM feature_usage_reservations WHERE status='consumed') AS usage_consumed,
              (SELECT count(*) FROM feature_usage_reservations WHERE status='reserved') AS usage_reserved""")
            clients = await conn.fetch("""SELECT w.id::text AS workspace_id,w.name AS workspace_name,
              u.email AS owner_email,s.status AS subscription_status,
              COALESCE((SELECT p.name FROM platform_billing_plans p WHERE p.slug=s.plan_slug),
                (SELECT p.name FROM platform_billing_plans p WHERE p.entitlements=s.entitlements
                  ORDER BY p.active DESC,p.created_at DESC LIMIT 1)) AS package_name,
              s.billing_period_starts_at,s.billing_period_ends_at,
              COALESCE(v.consumed,0)::bigint AS usage_consumed,COALESCE(v.reserved,0)::bigint AS usage_reserved,
              COALESCE(v.released,0)::bigint AS usage_released
              FROM workspaces w
              LEFT JOIN workspace_memberships m ON m.workspace_id=w.id AND m.role='owner' AND m.status='active'
              LEFT JOIN app_users u ON u.id=m.user_id
              LEFT JOIN workspace_subscriptions s ON s.workspace_id=w.id
              LEFT JOIN LATERAL (SELECT count(*) FILTER(WHERE status='consumed') consumed,
                count(*) FILTER(WHERE status='reserved') reserved,count(*) FILTER(WHERE status='released') released
                FROM feature_usage_reservations r WHERE r.workspace_id=w.id) v ON true
              ORDER BY w.created_at DESC LIMIT $1 OFFSET $2""", client_limit, client_offset)
            plans = await conn.fetch("SELECT slug,name,description,price_id,display_price,currency,billing_interval,entitlements,active,created_at,updated_at FROM platform_billing_plans ORDER BY created_at DESC")
            usage_by_feature = await conn.fetch("""SELECT workspace_id::text AS workspace_id,feature,
              count(*) FILTER(WHERE status='consumed')::bigint AS consumed,
              count(*) FILTER(WHERE status='reserved')::bigint AS reserved,
              count(*) FILTER(WHERE status='released')::bigint AS released
              FROM feature_usage_reservations GROUP BY workspace_id,feature ORDER BY workspace_id,feature LIMIT 2000""")
            recent_usage = await conn.fetch("""SELECT r.id::text AS reservation_id,r.workspace_id::text AS workspace_id,
              w.name AS workspace_name,r.feature,r.status,r.created_at,r.updated_at,
              r.billing_period_starts_at,r.billing_period_ends_at
              FROM feature_usage_reservations r LEFT JOIN workspaces w ON w.id=r.workspace_id
              ORDER BY r.created_at DESC LIMIT $1 OFFSET $2""", usage_limit, usage_offset)
            usage_total = await conn.fetchval("SELECT count(*) FROM feature_usage_reservations")
            admin_events = await conn.fetch("""SELECT e.id,e.actor_user_id::text AS actor_user_id,
              u.email AS actor_email,e.event_type,e.target_type,e.target_id,e.metadata,e.created_at
              FROM platform_admin_audit_events e JOIN app_users u ON u.id=e.actor_user_id
              ORDER BY e.created_at DESC LIMIT $1 OFFSET $2""", audit_limit, audit_offset)
            audit_total = await conn.fetchval("SELECT count(*) FROM platform_admin_audit_events")
        return {"totals": {k:int(v or 0) for k,v in dict(totals).items()},
          "clients":[{k:(v.isoformat() if hasattr(v,"isoformat") else v) for k,v in dict(row).items()} for row in clients],
          "plans":[public_plan(row) for row in plans],
          "usage_by_feature":[dict(row) for row in usage_by_feature],
          "recent_usage":[{k:(v.isoformat() if hasattr(v,"isoformat") else v) for k,v in dict(row).items()} for row in recent_usage],
          "admin_events":[{k:(v.isoformat() if hasattr(v,"isoformat") else v) for k,v in dict(row).items()} for row in admin_events],
          "clients_truncated":client_offset + len(clients) < int(totals["workspaces_total"] or 0), "clients_offset":client_offset, "clients_limit":client_limit, "clients_total":int(totals["workspaces_total"] or 0), "usage_offset":usage_offset, "usage_limit":usage_limit, "usage_total":int(usage_total or 0), "usage_truncated":usage_offset + len(recent_usage) < int(usage_total or 0), "audit_offset":audit_offset, "audit_limit":audit_limit, "audit_total":int(audit_total or 0), "audit_truncated":audit_offset + len(admin_events) < int(audit_total or 0)}
    except HTTPException: raise
    except Exception: raise HTTPException(status_code=503, detail="platform_admin_overview_unavailable") from None

@router.post("/plans/import-configured")
async def import_configured_plans(request: Request):
    """Import existing server-configured Paddle plans once, without overwriting admin edits."""
    actor = await require_platform_admin(request, write=True)
    try:
        from app.api.paddle_routes import _plans
        configured = _plans()
        imported = 0
        skipped = 0
        async with pool_for(request).acquire() as conn:
            async with conn.transaction():
                for slug, raw in configured.items():
                    if not isinstance(slug, str) or not isinstance(raw, dict):
                        skipped += 1
                        continue
                    display_name = raw.get("name")
                    if not isinstance(display_name, str) or not display_name.strip():
                        display_name = slug.replace("-", " ").replace("_", " ").title()
                    try:
                        item = PlanInput(
                            slug=slug, name=display_name, description=raw.get("description", ""),
                            price_id=raw.get("price_id"), display_price=raw.get("display_price"),
                            currency=raw.get("currency"), billing_interval=raw.get("billing_interval"),
                            entitlements=raw.get("entitlements"), active=raw.get("active", True),
                        )
                    except Exception:
                        skipped += 1
                        continue
                    row = await conn.fetchrow("""INSERT INTO platform_billing_plans
                        (slug,name,description,price_id,display_price,currency,billing_interval,entitlements,active)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
                        ON CONFLICT DO NOTHING RETURNING slug""",
                        item.slug,item.name.strip(),item.description,item.price_id,item.display_price,
                        item.currency,item.billing_interval,json.dumps(item.entitlements,allow_nan=False),item.active)
                    if row is None:
                        skipped += 1
                    else:
                        imported += 1
                await conn.execute("""INSERT INTO platform_admin_audit_events
                    (actor_user_id,event_type,target_type,target_id,metadata)
                    VALUES($1::uuid,'billing_plan.catalog_imported','billing_catalog','environment',
                           $2::jsonb)""", actor["user_id"],
                    json.dumps({"imported": imported, "skipped": skipped}))
        return {"imported": imported, "skipped": skipped, "configured": len(configured)}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="billing_plan_import_unavailable") from None

@router.post("/plans", status_code=201)
async def create_plan(payload: PlanInput, request: Request):
    actor = await require_platform_admin(request, write=True)
    try:
        async with pool_for(request).acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""INSERT INTO platform_billing_plans
                  (slug,name,description,price_id,display_price,currency,billing_interval,entitlements,active)
                  VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
                  RETURNING slug,name,description,price_id,display_price,currency,billing_interval,entitlements,active,created_at,updated_at""",
                  payload.slug,payload.name.strip(),payload.description,payload.price_id,payload.display_price,
                  payload.currency,payload.billing_interval,json.dumps(payload.entitlements,allow_nan=False),payload.active)
                await conn.execute("""INSERT INTO platform_admin_audit_events
                  (actor_user_id,event_type,target_type,target_id,metadata)
                  VALUES($1::uuid,'billing_plan.created','billing_plan',$2,$3::jsonb)""",
                  actor["user_id"],payload.slug,json.dumps({"active":payload.active}))
        return {"plan":public_plan(row)}
    except Exception as exc:
        if "unique" in str(exc).casefold() or "duplicate" in str(exc).casefold():
            raise HTTPException(status_code=409,detail="billing_plan_already_exists") from None
        raise HTTPException(status_code=503,detail="billing_plan_create_unavailable") from None

@router.patch("/plans/{slug}")
async def update_plan(slug: str, payload: PlanInput, request: Request):
    actor = await require_platform_admin(request, write=True)
    if slug != payload.slug: raise HTTPException(status_code=422,detail="plan_slug_mismatch")
    try:
        async with pool_for(request).acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow("SELECT price_id,entitlements FROM platform_billing_plans WHERE slug=$1 FOR UPDATE",slug)
                if current is not None and current["price_id"] != payload.price_id:
                    current_entitlements = current["entitlements"]
                    if isinstance(current_entitlements, str):
                        current_entitlements = json.loads(current_entitlements)
                    linked_subscriptions = await conn.fetchval(
                        """SELECT count(*) FROM workspace_subscriptions
                           WHERE plan_slug=$1
                              OR (plan_slug IS NULL AND entitlements=$2::jsonb)""",
                        slug, json.dumps(current_entitlements,allow_nan=False))
                    if linked_subscriptions:
                        raise HTTPException(status_code=409,detail="price_id_immutable_for_existing_subscriptions_create_new_plan")
                row = await conn.fetchrow("""UPDATE platform_billing_plans SET name=$2,description=$3,price_id=$4,
                  display_price=$5,currency=$6,billing_interval=$7,entitlements=$8::jsonb,active=$9,updated_at=now()
                  WHERE slug=$1 RETURNING slug,name,description,price_id,display_price,currency,billing_interval,entitlements,active,created_at,updated_at""",
                  slug,payload.name.strip(),payload.description,payload.price_id,payload.display_price,payload.currency,
                  payload.billing_interval,json.dumps(payload.entitlements,allow_nan=False),payload.active)
                if row is not None:
                    await conn.execute("""INSERT INTO platform_admin_audit_events
                      (actor_user_id,event_type,target_type,target_id,metadata)
                      VALUES($1::uuid,'billing_plan.updated','billing_plan',$2,$3::jsonb)""",
                      actor["user_id"],slug,json.dumps({"active":payload.active}))
        if row is None: raise HTTPException(status_code=404,detail="billing_plan_not_found")
        return {"plan":public_plan(row)}
    except HTTPException: raise
    except Exception: raise HTTPException(status_code=503,detail="billing_plan_update_unavailable") from None

@router.delete("/plans/{slug}")
async def deactivate_plan(slug: str, request: Request):
    actor = await require_platform_admin(request, write=True)
    try:
        async with pool_for(request).acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("UPDATE platform_billing_plans SET active=false,updated_at=now() WHERE slug=$1 AND active=true RETURNING slug",slug)
                if row is not None:
                    await conn.execute("""INSERT INTO platform_admin_audit_events
                      (actor_user_id,event_type,target_type,target_id,metadata)
                      VALUES($1::uuid,'billing_plan.deactivated','billing_plan',$2,'{}'::jsonb)""",
                      actor["user_id"],slug)
        if row is None: raise HTTPException(status_code=404,detail="active_billing_plan_not_found")
        return {"slug":slug,"active":False,"deleted":True}
    except HTTPException: raise
    except Exception: raise HTTPException(status_code=503,detail="billing_plan_deactivation_unavailable") from None
