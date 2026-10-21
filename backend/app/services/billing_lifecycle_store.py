"""Provider-neutral billing lifecycle persistence.

This is an internal persistence boundary, not a webhook endpoint. Callers must verify
provider signatures and map provider identifiers to an authorized workspace before
constructing a VerifiedBillingEvent. Raw payloads and credentials are never stored.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
import json


_ALLOWED_STATUSES = frozenset({
    "active", "trialing", "past_due", "cancelled", "incomplete", "unpaid", "paused"
})


@dataclass(frozen=True)
class VerifiedBillingEvent:
    provider: str
    event_id: str
    workspace_id: str
    provider_customer_id: str | None
    provider_subscription_id: str
    event_created_at: datetime
    subscription_status: str
    period_starts_at: datetime
    period_ends_at: datetime
    entitlements: Mapping[str, object]


class BillingLifecycleStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def apply_verified_event(self, event: VerifiedBillingEvent) -> dict[str, str]:
        """Deduplicate an already-verified event and apply only newer snapshots."""
        self._validate(event)
        entitlements_json = json.dumps(dict(event.entitlements), separators=(",", ":"))
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                inserted = await conn.fetchrow(
                    """INSERT INTO billing_provider_events
                       (provider,provider_event_id,workspace_id,provider_subscription_id,
                        event_created_at,outcome)
                       VALUES ($1,$2,$3,$4,$5,'stale')
                       ON CONFLICT (provider,provider_event_id) DO NOTHING
                       RETURNING id""",
                    event.provider, event.event_id, event.workspace_id,
                    event.provider_subscription_id, event.event_created_at,
                )
                if inserted is None:
                    return {"outcome": "duplicate"}

                current = await conn.fetchrow(
                    """SELECT provider,provider_subscription_id
                       FROM workspace_subscriptions WHERE workspace_id=$1 FOR UPDATE""",
                    event.workspace_id,
                )
                if current is not None and (
                    current["provider"] != event.provider
                    or current["provider_subscription_id"] != event.provider_subscription_id
                ):
                    raise ValueError("billing_subscription_identity_conflict")

                applied = await conn.fetchrow(
                    """INSERT INTO workspace_subscriptions
                       (workspace_id,provider,provider_customer_id,provider_subscription_id,
                        status,billing_period_starts_at,billing_period_ends_at,entitlements,
                        provider_event_created_at,updated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,now())
                       ON CONFLICT (workspace_id) DO UPDATE SET
                         provider_customer_id=EXCLUDED.provider_customer_id,
                         status=EXCLUDED.status,
                         billing_period_starts_at=EXCLUDED.billing_period_starts_at,
                         billing_period_ends_at=EXCLUDED.billing_period_ends_at,
                         entitlements=EXCLUDED.entitlements,
                         provider_event_created_at=EXCLUDED.provider_event_created_at,
                         updated_at=now()
                       WHERE workspace_subscriptions.provider=EXCLUDED.provider
                         AND workspace_subscriptions.provider_subscription_id=EXCLUDED.provider_subscription_id
                         AND (workspace_subscriptions.provider_event_created_at IS NULL
                           OR EXCLUDED.provider_event_created_at > workspace_subscriptions.provider_event_created_at)
                       RETURNING workspace_id""",
                    event.workspace_id, event.provider, event.provider_customer_id,
                    event.provider_subscription_id, event.subscription_status,
                    event.period_starts_at, event.period_ends_at, entitlements_json,
                    event.event_created_at,
                )
                if applied is None:
                    # Event remains in the ledger as stale; a retry cannot replay it.
                    return {"outcome": "stale"}
                await conn.execute(
                    """UPDATE billing_provider_events SET outcome='applied'
                       WHERE provider=$1 AND provider_event_id=$2""",
                    event.provider, event.event_id,
                )
                return {"outcome": "applied"}

    @staticmethod
    def _validate(event: VerifiedBillingEvent) -> None:
        for name, value, maximum in (
            ("provider", event.provider, 40),
            ("event_id", event.event_id, 300),
            ("workspace_id", event.workspace_id, 200),
            ("provider_subscription_id", event.provider_subscription_id, 300),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"invalid_{name}")
        if event.provider_customer_id is not None and (
            not isinstance(event.provider_customer_id, str)
            or not event.provider_customer_id.strip()
            or len(event.provider_customer_id) > 300
        ):
            raise ValueError("invalid_provider_customer_id")
        if event.subscription_status not in _ALLOWED_STATUSES:
            raise ValueError("invalid_subscription_status")
        dates = (event.event_created_at, event.period_starts_at, event.period_ends_at)
        if any(not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None
               for value in dates):
            raise ValueError("timezone_required")
        if event.period_ends_at <= event.period_starts_at:
            raise ValueError("invalid_billing_period")
        if not isinstance(event.entitlements, Mapping):
            raise ValueError("invalid_entitlements")
        try:
            encoded = json.dumps(dict(event.entitlements), allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("invalid_entitlements") from None
        if len(encoded) > 100_000:
            raise ValueError("entitlements_too_large")
