"""One-shot scheduler adapter for the hardened WhatsApp dispatch worker."""
from __future__ import annotations

from uuid import UUID

from app.workers.whatsapp_dispatch_worker import (
    dispatch_is_enabled,
    process_claimed_delivery,
)
from app.services.subscription_store import SubscriptionStore
from app.services.whatsapp_outbound_store import WhatsAppOutboundStore


async def process_whatsapp_outbound(pool, *, limit: int = 10) -> dict[str, int]:
    if not dispatch_is_enabled():
        raise RuntimeError("whatsapp_dispatch_not_enabled")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("whatsapp_dispatch_limit_out_of_range")
    queue = WhatsAppOutboundStore(pool)
    subscriptions = SubscriptionStore(pool)
    recovered = await queue.mark_expired_claims_uncertain(limit=100)
    batch = await queue.claim_batch(limit=limit, lease_seconds=120)
    result = {
        "claimed": len(batch), "sent": 0, "provider_rejected": 0,
        "provider_uncertain": 0, "policy_denied": 0, "entitlement_denied": 0,
        "preflight_failed": 0, "sent_lease_completion_lost": 0,
        "expired_claims_recovered": recovered,
    }
    for delivery in batch:
        try:
            outcome = await process_claimed_delivery(
                pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery,
            )
        except Exception:
            # The worker's lease recovery makes any unresolved in-flight attempt terminal.
            try:
                await queue.finish_claim(
                    delivery_id=UUID(str(delivery["id"])),
                    lease_token=UUID(str(delivery["lease_token"])),
                    outcome="uncertain",
                    error_code="scheduler_iteration_uncertain",
                )
            except Exception:
                pass
            outcome = "provider_uncertain"
        result[outcome] = result.get(outcome, 0) + 1
    return result
