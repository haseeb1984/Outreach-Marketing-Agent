"""Trusted PostgreSQL subscription snapshots and atomic feature quota reservations.

This store is deliberately not an HTTP endpoint or a payment-provider adapter.
Only verified server-side billing lifecycle handlers may write subscription snapshots.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json

from app.services.entitlements import EntitlementDecision, evaluate_entitlement


class SubscriptionStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def get_entitlement(
        self, *, workspace_id: str, feature: str, now: datetime | None = None,
    ) -> EntitlementDecision:
        """Evaluate a persisted snapshot; missing database state denies access."""
        current = now or datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT s.status, s.billing_period_starts_at, s.billing_period_ends_at,
                          s.entitlements,
                          count(u.id) FILTER (WHERE u.status IN ('reserved','consumed')) AS usage
                   FROM workspace_subscriptions s
                   LEFT JOIN feature_usage_reservations u
                     ON u.workspace_id=s.workspace_id
                    AND u.billing_period_starts_at=s.billing_period_starts_at
                    AND u.billing_period_ends_at=s.billing_period_ends_at
                    AND u.feature=$2
                   WHERE s.workspace_id=$1
                   GROUP BY s.workspace_id, s.status, s.billing_period_starts_at,
                            s.billing_period_ends_at, s.entitlements""",
                workspace_id, feature,
            )
        if row is None:
            return evaluate_entitlement(
                subscription_status=None, period_starts_at=None, period_ends_at=None,
                feature=feature, entitlements=None, usage=None, now=current,
            )
        return evaluate_entitlement(
            subscription_status=row["status"],
            period_starts_at=row["billing_period_starts_at"],
            period_ends_at=row["billing_period_ends_at"],
            feature=feature,
            entitlements=self._mapping(row["entitlements"]),
            usage=int(row["usage"]),
            now=current,
        )

    async def reserve_usage(
        self, *, workspace_id: str, feature: str, idempotency_key: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Atomically reserve one quota unit and return a stable reservation.

        Locking the subscription row serializes reservations for this workspace.
        Repeating the same key is idempotent; reusing it for a different feature
        is rejected. A caller must mark successful work consumed or explicitly
        release a reservation after proving no billable action occurred.
        """
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("invalid_workspace")
        if not isinstance(feature, str) or not feature.strip() or len(feature) > 100:
            raise ValueError("invalid_feature")
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 200:
            raise ValueError("invalid_idempotency_key")
        current = now or datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """SELECT workspace_id,status,billing_period_starts_at,
                              billing_period_ends_at,entitlements
                       FROM workspace_subscriptions WHERE workspace_id=$1 FOR UPDATE""",
                    workspace_id,
                )
                if row is None:
                    return {"allowed": False, "reason": "subscription_missing"}
                existing = await conn.fetchrow(
                    """SELECT id,feature,status,billing_period_starts_at,billing_period_ends_at
                       FROM feature_usage_reservations
                       WHERE workspace_id=$1 AND feature=$2 AND idempotency_key=$3""",
                    workspace_id, feature, idempotency_key,
                )
                if existing is not None:
                    if (existing["billing_period_starts_at"] != row["billing_period_starts_at"]
                            or existing["billing_period_ends_at"] != row["billing_period_ends_at"]):
                        return {"allowed": False, "reason": "idempotency_key_period_conflict"}
                    if existing["status"] == "released":
                        return {"allowed": False, "reason": "reservation_released"}
                    return {"allowed": True, "reason": "idempotent_replay",
                            "reservation_id": str(existing["id"]), "status": existing["status"]}

                usage = await conn.fetchval(
                    """SELECT count(*) FROM feature_usage_reservations
                       WHERE workspace_id=$1 AND feature=$2
                         AND billing_period_starts_at=$3 AND billing_period_ends_at=$4
                         AND status IN ('reserved','consumed')""",
                    workspace_id, feature, row["billing_period_starts_at"],
                    row["billing_period_ends_at"],
                )
                decision = evaluate_entitlement(
                    subscription_status=row["status"],
                    period_starts_at=row["billing_period_starts_at"],
                    period_ends_at=row["billing_period_ends_at"],
                    feature=feature,
                    entitlements=self._mapping(row["entitlements"]),
                    usage=int(usage),
                    now=current,
                )
                if not decision.allowed:
                    return {"allowed": False, "reason": decision.reason,
                            "remaining": decision.remaining}
                reserved = await conn.fetchrow(
                    """INSERT INTO feature_usage_reservations
                       (workspace_id,feature,idempotency_key,billing_period_starts_at,
                        billing_period_ends_at,status,created_at,updated_at)
                       VALUES ($1,$2,$3,$4,$5,'reserved',$6,$6)
                       RETURNING id,status""",
                    workspace_id, feature, idempotency_key,
                    row["billing_period_starts_at"], row["billing_period_ends_at"], current,
                )
                return {"allowed": True, "reason": "reserved",
                        "reservation_id": str(reserved["id"]), "status": reserved["status"],
                        "remaining": decision.remaining - 1 if decision.remaining is not None else None}

    async def finish_reservation(
        self, *, workspace_id: str, reservation_id: str, outcome: str,
    ) -> bool:
        """Move a reservation to consumed or released once; no silent double-finish."""
        if outcome not in {"consumed", "released"}:
            raise ValueError("invalid_reservation_outcome")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE feature_usage_reservations SET status=$3,updated_at=now()
                   WHERE id=$1::uuid AND workspace_id=$2 AND status='reserved'
                   RETURNING id""",
                reservation_id, workspace_id, outcome,
            )
        return row is not None

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any] | None:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return None
        return value if isinstance(value, dict) else None
