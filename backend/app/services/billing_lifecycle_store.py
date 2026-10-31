"""Provider-neutral billing lifecycle persistence.

This is an internal persistence boundary, not a webhook endpoint. Callers must verify
provider signatures and map provider identifiers to an authorized workspace before
constructing a VerifiedBillingEvent. Raw payloads and credentials are never stored.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
import json
import re


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
    plan_slug: str
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
                    # Provider event IDs are the idempotency key. Do not silently
                    # acknowledge an ID collision that points at a different tenant,
                    # subscription, or event timestamp.
                    prior_event = await conn.fetchrow(
                        """SELECT workspace_id,provider_subscription_id,event_created_at
                           FROM billing_provider_events
                           WHERE provider=$1 AND provider_event_id=$2 FOR UPDATE""",
                        event.provider, event.event_id,
                    )
                    if prior_event is None or not self._same_event_identity(prior_event, event):
                        raise ValueError("billing_event_identity_conflict")
                    return {"outcome": "duplicate"}

                current = await conn.fetchrow(
                    """SELECT provider,provider_subscription_id,provider_customer_id
                       FROM workspace_subscriptions WHERE workspace_id=$1 FOR UPDATE""",
                    event.workspace_id,
                )
                if current is not None and (
                    current["provider"] != event.provider
                    or current["provider_subscription_id"] != event.provider_subscription_id
                    or (
                        current["provider_customer_id"] is not None
                        and event.provider_customer_id is not None
                        and current["provider_customer_id"] != event.provider_customer_id
                    )
                ):
                    raise ValueError("billing_subscription_identity_conflict")

                applied = await conn.fetchrow(
                    """INSERT INTO workspace_subscriptions
                       (workspace_id,provider,provider_customer_id,provider_subscription_id,plan_slug,
                        status,billing_period_starts_at,billing_period_ends_at,entitlements,
                        provider_event_created_at,updated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,now())
                       ON CONFLICT (workspace_id) DO UPDATE SET
                         provider_customer_id=COALESCE(EXCLUDED.provider_customer_id,workspace_subscriptions.provider_customer_id),
                         plan_slug=EXCLUDED.plan_slug,
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
                    event.provider_subscription_id, event.plan_slug, event.subscription_status,
                    event.period_starts_at, event.period_ends_at, entitlements_json,
                    event.event_created_at,
                )
                if applied is None:
                    # The initial SELECT cannot lock a row that does not yet exist.
                    # A concurrent first event may create a different subscription after
                    # that SELECT; re-check after ON CONFLICT has waited for its winner.
                    # Without this second check, that identity conflict was mislabeled stale.
                    current_after_conflict = await conn.fetchrow(
                        """SELECT provider,provider_subscription_id,provider_customer_id
                           FROM workspace_subscriptions WHERE workspace_id=$1 FOR UPDATE""",
                        event.workspace_id,
                    )
                    if current_after_conflict is not None and (
                        current_after_conflict["provider"] != event.provider
                        or current_after_conflict["provider_subscription_id"] != event.provider_subscription_id
                        or (
                            current_after_conflict["provider_customer_id"] is not None
                            and event.provider_customer_id is not None
                            and current_after_conflict["provider_customer_id"] != event.provider_customer_id
                        )
                    ):
                        raise ValueError("billing_subscription_identity_conflict")
                    # Event remains in the ledger as stale; a retry cannot replay it.
                    return {"outcome": "stale"}
                await conn.execute(
                    """UPDATE billing_provider_events SET outcome='applied'
                       WHERE provider=$1 AND provider_event_id=$2""",
                    event.provider, event.event_id,
                )
                return {"outcome": "applied"}

    async def record_verified_transaction(self, *, event_id: str, event_created_at: datetime,
        transaction_id: str, workspace_id: str, subscription_id: str | None,
        invoice_number: str | None, status: str, currency_code: str | None,
        total_minor: str | None) -> dict[str, str]:
        """Persist sanitized invoice state from a signature-verified Paddle transaction event."""
        if status not in {"completed", "payment_failed"}:
            raise ValueError("invalid_transaction_status")
        for name, value, maximum in (("event_id", event_id, 300),
            ("transaction_id", transaction_id, 120), ("workspace_id", workspace_id, 200)):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"invalid_{name}")
        if subscription_id is not None and (
            not isinstance(subscription_id, str) or not subscription_id.strip()
            or len(subscription_id) > 120
        ):
            raise ValueError("invalid_subscription_id")
        if invoice_number is not None and (
            not isinstance(invoice_number, str) or not invoice_number.strip()
            or len(invoice_number) > 120
        ):
            raise ValueError("invalid_invoice_number")
        if currency_code is not None and (
            not isinstance(currency_code, str) or re.fullmatch(r"[A-Z]{3}", currency_code) is None
        ):
            raise ValueError("invalid_currency_code")
        if total_minor is not None and (not isinstance(total_minor, str) or not total_minor.isdigit() or len(total_minor) > 20):
            raise ValueError("invalid_transaction_total")
        if not isinstance(event_created_at, datetime) or event_created_at.tzinfo is None:
            raise ValueError("timezone_required")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                inserted = await conn.fetchrow(
                    """INSERT INTO billing_transaction_events(provider,provider_event_id,transaction_id,event_created_at)
                       VALUES ('paddle',$1,$2,$3) ON CONFLICT(provider,provider_event_id) DO NOTHING
                       RETURNING provider_event_id""", event_id, transaction_id, event_created_at)
                if inserted is None:
                    prior = await conn.fetchrow(
                        """SELECT transaction_id,event_created_at FROM billing_transaction_events
                           WHERE provider='paddle' AND provider_event_id=$1 FOR UPDATE""", event_id)
                    if prior is None or prior["transaction_id"] != transaction_id or prior["event_created_at"] != event_created_at:
                        raise ValueError("billing_transaction_event_identity_conflict")
                    return {"outcome": "duplicate"}
                row = await conn.fetchrow(
                    """INSERT INTO billing_transactions
                       (provider,transaction_id,workspace_id,provider_subscription_id,invoice_number,
                        status,currency_code,total_minor,billed_at,provider_event_created_at,updated_at)
                       VALUES ('paddle',$1,$2,$3,$4,$5,$6,$7,$8,$8,now())
                       ON CONFLICT(provider,transaction_id) DO UPDATE SET
                         provider_subscription_id=COALESCE(EXCLUDED.provider_subscription_id,billing_transactions.provider_subscription_id),
                         invoice_number=COALESCE(EXCLUDED.invoice_number,billing_transactions.invoice_number),
                         status=EXCLUDED.status,currency_code=COALESCE(EXCLUDED.currency_code,billing_transactions.currency_code),
                         total_minor=COALESCE(EXCLUDED.total_minor,billing_transactions.total_minor),
                         billed_at=EXCLUDED.billed_at,provider_event_created_at=EXCLUDED.provider_event_created_at,updated_at=now()
                       WHERE billing_transactions.workspace_id=EXCLUDED.workspace_id
                         AND (billing_transactions.provider_subscription_id IS NULL
                              OR EXCLUDED.provider_subscription_id IS NULL
                              OR billing_transactions.provider_subscription_id=EXCLUDED.provider_subscription_id)
                         AND (billing_transactions.invoice_number IS NULL
                              OR EXCLUDED.invoice_number IS NULL
                              OR billing_transactions.invoice_number=EXCLUDED.invoice_number)
                         AND (billing_transactions.provider_event_created_at IS NULL
                              OR EXCLUDED.provider_event_created_at > billing_transactions.provider_event_created_at)
                       RETURNING transaction_id""",
                    transaction_id, workspace_id, subscription_id, invoice_number, status,
                    currency_code, total_minor, event_created_at)
                if row is None:
                    current = await conn.fetchrow(
                        """SELECT workspace_id,provider_subscription_id,invoice_number
                           FROM billing_transactions
                           WHERE provider='paddle' AND transaction_id=$1 FOR UPDATE""", transaction_id)
                    if current is None or current["workspace_id"] != workspace_id:
                        raise ValueError("billing_transaction_workspace_conflict")
                    if not self._same_transaction_identity(
                        current, subscription_id=subscription_id, invoice_number=invoice_number
                    ):
                        raise ValueError("billing_transaction_identity_conflict")
                    return {"outcome": "stale"}
                return {"outcome": "applied"}

    @staticmethod
    def _same_transaction_identity(
        prior: Mapping[str, Any], *, subscription_id: str | None, invoice_number: str | None
    ) -> bool:
        """Prevent a transaction ID from being rebound to another subscription or invoice."""
        return (
            (prior["provider_subscription_id"] is None
             or subscription_id is None
             or prior["provider_subscription_id"] == subscription_id)
            and (prior["invoice_number"] is None
                 or invoice_number is None
                 or prior["invoice_number"] == invoice_number)
        )

    @staticmethod
    def _same_event_identity(prior: Mapping[str, Any], event: VerifiedBillingEvent) -> bool:
        return (
            prior["workspace_id"] == event.workspace_id
            and prior["provider_subscription_id"] == event.provider_subscription_id
            and prior["event_created_at"] == event.event_created_at
        )

    @staticmethod
    def _validate(event: VerifiedBillingEvent) -> None:
        for name, value, maximum in (
            ("provider", event.provider, 40),
            ("event_id", event.event_id, 300),
            ("workspace_id", event.workspace_id, 200),
            ("provider_subscription_id", event.provider_subscription_id, 300),
            ("plan_slug", event.plan_slug, 80),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"invalid_{name}")
        if event.provider_customer_id is not None and (
            not isinstance(event.provider_customer_id, str)
            or not event.provider_customer_id.strip()
            or len(event.provider_customer_id) > 300
        ):
            raise ValueError("invalid_provider_customer_id")
        if not isinstance(event.subscription_status, str) or event.subscription_status not in _ALLOWED_STATUSES:
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
