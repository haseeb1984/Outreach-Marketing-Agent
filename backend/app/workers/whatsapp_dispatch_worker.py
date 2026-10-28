"""Fail-closed WhatsApp outbound dispatch worker.

Run from backend with DATABASE_URL configured and WHATSAPP_DISPATCH_ENABLED=true.
The feature flag defaults off; enable only after Meta sandbox acceptance, migration
038, consent/template review, and operational reconciliation are verified.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.services.subscription_store import SubscriptionStore
from app.services.whatsapp_credential_store import (
    WhatsAppCredentialStore,
    WhatsAppCredentialUnavailable,
)
from app.services.whatsapp_meta_sender import (
    MetaSendRejected,
    MetaSendUncertain,
    MetaWhatsAppSender,
)
from app.services.whatsapp_outbound_store import WhatsAppOutboundStore
from app.services.whatsapp_send_policy import WhatsAppSendPolicy

logger = logging.getLogger("outreach.whatsapp_worker")
POLL_SECONDS = 2.0
BATCH_SIZE = 5
LEASE_SECONDS = 120


def dispatch_is_enabled() -> bool:
    """Both explicit app config and an exact opt-in environment value are required."""
    return bool(settings.whatsapp_dispatch_enabled) and os.getenv(
        "WHATSAPP_DISPATCH_ENABLED", ""
    ).strip().lower() in {"1", "true", "yes"}


async def _release_if_reserved(
    subscriptions: Any, *, workspace_id: str, reservation_id: str,
) -> None:
    try:
        await subscriptions.finish_reservation(
            workspace_id=workspace_id, reservation_id=reservation_id, outcome="released",
        )
    except Exception:
        logger.error("WhatsApp reservation release failed; manual billing reconciliation required")


async def _consume_reservation(
    subscriptions: Any, *, workspace_id: str, reservation_id: str,
) -> None:
    try:
        await subscriptions.finish_reservation(
            workspace_id=workspace_id, reservation_id=reservation_id, outcome="consumed",
        )
    except Exception:
        logger.error("WhatsApp reservation consumption failed; manual billing reconciliation required")


async def process_claimed_delivery(
    *,
    pool: Any,
    queue: Any,
    subscriptions: Any,
    delivery: dict[str, Any],
    sender: Any | None = None,
) -> str:
    """Re-check current eligibility immediately before a single provider attempt."""
    if not dispatch_is_enabled():
        return "dispatch_disabled"

    workspace_id = str(delivery["workspace_id"])
    delivery_id = UUID(str(delivery["id"]))
    lease_token = UUID(str(delivery["lease_token"]))
    reservation_id = str(delivery["usage_reservation_id"])

    try:
        entitlement = await subscriptions.validate_job_reservation(
            workspace_id=workspace_id,
            reservation_id=reservation_id,
            feature="whatsapp_sends",
        )
    except Exception:
        entitlement = {"allowed": False, "reason": "subscription_recheck_unavailable"}
    if not entitlement.get("allowed"):
        await queue.finish_claim(
            delivery_id=delivery_id, lease_token=lease_token, outcome="failed",
            error_code=str(entitlement.get("reason", "whatsapp_entitlement_denied"))[:100],
        )
        if entitlement.get("reservation_status") == "reserved":
            await _release_if_reserved(
                subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
            )
        return "entitlement_denied"

    try:
        async with pool.acquire() as conn:
            content = await conn.fetchrow(
                """SELECT d.body,p.contact_phone_e164
                   FROM outreach_drafts d
                   JOIN crm_prospects p
                     ON p.id=d.prospect_id AND p.workspace_id=d.workspace_id
                   WHERE d.id=$1 AND d.workspace_id=$2 AND p.id=$3""",
                UUID(str(delivery["draft_id"])), workspace_id,
                UUID(str(delivery["prospect_id"])),
            )
        if content is None:
            raise LookupError("whatsapp_draft_or_prospect_missing")
        decision = await WhatsAppSendPolicy(pool).evaluate(
            workspace_id=workspace_id,
            account_id=UUID(str(delivery["account_id"])),
            prospect_id=UUID(str(delivery["prospect_id"])),
            draft_id=UUID(str(delivery["draft_id"])),
            template_name=delivery.get("template_name"),
            language_code=delivery.get("language_code"),
        )
        if not decision.get("allowed"):
            reason = str(decision.get("reason", "whatsapp_policy_denied"))[:100]
            await queue.finish_claim(
                delivery_id=delivery_id, lease_token=lease_token, outcome="failed",
                error_code=reason,
            )
            if entitlement.get("reservation_status") == "reserved":
                await _release_if_reserved(
                    subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
                )
            return "policy_denied"
        credentials = await WhatsAppCredentialStore(pool).get_active_credentials(
            workspace_id=workspace_id, account_id=UUID(str(delivery["account_id"])),
        )
        recipient = "".join(
            char for char in str(content["contact_phone_e164"] or "") if char.isdigit()
        )
        if not 7 <= len(recipient) <= 15:
            raise ValueError("whatsapp_recipient_invalid")
    except Exception as exc:
        # No provider call has happened yet, so the reservation can safely be released.
        code = str(exc) if isinstance(exc, (ValueError, LookupError, WhatsAppCredentialUnavailable)) else "whatsapp_preflight_unavailable"
        await queue.finish_claim(
            delivery_id=delivery_id, lease_token=lease_token, outcome="failed",
            error_code=code[:100],
        )
        if entitlement.get("reservation_status") == "reserved":
            await _release_if_reserved(
                subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
            )
        return "preflight_failed"

    provider = sender or MetaWhatsAppSender()
    kwargs = {
        "version": settings.meta_graph_api_version or "",
        "phone_number_id": credentials.phone_number_id,
        "access_token": credentials.access_token,
        "recipient": recipient,
    }
    try:
        if decision.get("requires_approved_template"):
            result = await provider.send(
                **kwargs,
                template_name=str(delivery["template_name"]),
                language_code=str(delivery["language_code"]),
            )
        else:
            result = await provider.send(**kwargs, body=str(content["body"]))
    except MetaSendRejected as exc:
        await queue.finish_claim(
            delivery_id=delivery_id, lease_token=lease_token, outcome="failed",
            error_code=exc.code[:100],
        )
        if entitlement.get("reservation_status") == "reserved":
            await _release_if_reserved(
                subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
            )
        return "provider_rejected"
    except MetaSendUncertain as exc:
        await queue.finish_claim(
            delivery_id=delivery_id, lease_token=lease_token, outcome="uncertain",
            error_code=exc.code[:100],
        )
        # The provider may have accepted it; charge/reserve usage and never auto-retry.
        await _consume_reservation(
            subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
        )
        return "provider_uncertain"
    except Exception:
        # Once the sender has been invoked, any unclassified exception is treated as uncertain.
        await queue.finish_claim(
            delivery_id=delivery_id, lease_token=lease_token, outcome="uncertain",
            error_code="provider_outcome_uncertain",
        )
        await _consume_reservation(
            subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
        )
        return "provider_uncertain"

    message_id = result.get("provider_message_id") if isinstance(result, dict) else None
    if not isinstance(message_id, str) or not message_id.strip():
        await queue.finish_claim(
            delivery_id=delivery_id, lease_token=lease_token, outcome="uncertain",
            error_code="provider_message_id_missing",
        )
        await _consume_reservation(
            subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
        )
        return "provider_uncertain"

    completed = await queue.finish_claim(
        delivery_id=delivery_id, lease_token=lease_token, outcome="sent",
        provider_message_id=message_id,
    )
    # Even if lease fencing rejects completion, the provider already confirmed a send.
    await _consume_reservation(
        subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
    )
    return "sent" if completed else "sent_lease_completion_lost"


async def run_worker(*, poll_seconds: float = POLL_SECONDS) -> None:
    """Poll safely; no connection or dispatch occurs unless both opt-in flags are true."""
    if not dispatch_is_enabled():
        raise RuntimeError("WhatsApp dispatch is disabled; explicitly configure WHATSAPP_DISPATCH_ENABLED=true")
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the WhatsApp worker")
    if not 0.2 <= poll_seconds <= 30:
        raise ValueError("poll_seconds must be between 0.2 and 30")

    pool = await asyncpg.create_pool(
        dsn=settings.database_url, min_size=1, max_size=5, timeout=5, command_timeout=20,
    )
    worker_id = "whatsapp-dispatch-" + secrets.token_hex(12)
    queue = WhatsAppOutboundStore(pool)
    subscriptions = SubscriptionStore(pool)
    logger.info("WhatsApp dispatch worker started worker_id=%s", worker_id)
    try:
        while True:
            try:
                await queue.mark_expired_claims_uncertain(limit=100)
                batch = await queue.claim_batch(limit=BATCH_SIZE, lease_seconds=LEASE_SECONDS)
                if not batch:
                    await asyncio.sleep(poll_seconds)
                    continue
                for delivery in batch:
                    try:
                        outcome = await process_claimed_delivery(
                            pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery,
                        )
                        logger.info("WhatsApp delivery processed outcome=%s", outcome)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # A claim with a possibly-started provider request must never be blindly retried.
                        try:
                            await queue.finish_claim(
                                delivery_id=UUID(str(delivery["id"])),
                                lease_token=UUID(str(delivery["lease_token"])),
                                outcome="uncertain",
                                error_code="worker_iteration_uncertain",
                            )
                        except Exception:
                            logger.error("WhatsApp delivery requires lease-expiry recovery")
                        logger.error("WhatsApp dispatch iteration failed; delivery marked uncertain where possible")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("WhatsApp worker poll failed; retrying after bounded delay")
                await asyncio.sleep(poll_seconds)
    finally:
        await pool.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
