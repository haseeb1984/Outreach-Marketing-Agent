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
    ).strip().lower() in {"1", "true"}


async def _release_if_reserved(
    subscriptions: Any, *, workspace_id: str, reservation_id: str,
) -> None:
    try:
        await subscriptions.finish_reservation(
            workspace_id=workspace_id, reservation_id=reservation_id, outcome="released",
        )
    except Exception:
        logger.error("WhatsApp reservation release failed; manual billing reconciliation required")


async def _finish_pre_provider_failure(
    queue: Any, subscriptions: Any, *, delivery_id: UUID, lease_token: UUID,
    workspace_id: str, reservation_id: str, reservation_status: str | None,
    error_code: str,
) -> None:
    """Persist a no-send failure best-effort and release quota independently."""
    try:
        await queue.finish_claim(
            delivery_id=delivery_id, lease_token=lease_token, outcome="failed",
            error_code=error_code[:100],
        )
    except Exception:
        logger.error("WhatsApp pre-provider status write failed; lease recovery required")
    if reservation_status == "reserved":
        await _release_if_reserved(
            subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
        )


async def _consume_reservation(
    subscriptions: Any, *, workspace_id: str, reservation_id: str,
) -> None:
    try:
        await subscriptions.finish_reservation(
            workspace_id=workspace_id, reservation_id=reservation_id, outcome="consumed",
        )
    except Exception:
        logger.error("WhatsApp reservation consumption failed; manual billing reconciliation required")




async def _finish_provider_outcome(
    queue: Any, subscriptions: Any, *, delivery_id: UUID, lease_token: UUID,
    workspace_id: str, reservation_id: str, outcome: str,
    provider_message_id: str | None = None, error_code: str | None = None,
) -> bool:
    """Persist a post-provider outcome best-effort, but always settle its quota reservation.

    Provider outcomes are irreversible: once accepted or uncertain, a database error
    while writing queue state must not skip quota settlement. Lease-expiry recovery
    reconciles the queue row if the status write fails.
    """
    completed = False
    try:
        completed = await queue.finish_claim(
            delivery_id=delivery_id, lease_token=lease_token, outcome=outcome,
            provider_message_id=provider_message_id, error_code=error_code,
        )
    except Exception:
        logger.error(
            "WhatsApp post-provider status write failed; lease recovery required"
        )
    await _consume_reservation(
        subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
    )
    return completed


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
        await _finish_pre_provider_failure(
            queue, subscriptions, delivery_id=delivery_id, lease_token=lease_token,
            workspace_id=workspace_id, reservation_id=reservation_id,
            reservation_status=entitlement.get("reservation_status"),
            error_code=str(entitlement.get("reason", "whatsapp_entitlement_denied")),
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
            await _finish_pre_provider_failure(
                queue, subscriptions, delivery_id=delivery_id, lease_token=lease_token,
                workspace_id=workspace_id, reservation_id=reservation_id,
                reservation_status=entitlement.get("reservation_status"),
                error_code=reason,
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
        await _finish_pre_provider_failure(
            queue, subscriptions, delivery_id=delivery_id, lease_token=lease_token,
            workspace_id=workspace_id, reservation_id=reservation_id,
            reservation_status=entitlement.get("reservation_status"),
            error_code=code,
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
            approved_name = decision.get("template_name")
            approved_language = decision.get("language_code")
            if (
                not isinstance(approved_name, str) or not approved_name.strip()
                or not isinstance(approved_language, str) or not approved_language.strip()
                or not decision.get("template_id")
                or not decision.get("provider_template_id")
            ):
                raise ValueError("whatsapp_approved_template_identity_missing")
            result = await provider.send(
                **kwargs,
                template_name=approved_name,
                language_code=approved_language,
            )
        else:
            result = await provider.send(**kwargs, body=str(content["body"]))
    except MetaSendRejected as exc:
        # A definite rejection means no send occurred, so release quota even if the
        # queue status write fails; lease recovery can reconcile the delivery row.
        try:
            await queue.finish_claim(
                delivery_id=delivery_id, lease_token=lease_token, outcome="failed",
                error_code=exc.code[:100],
            )
        except Exception:
            logger.error(
                "WhatsApp rejection status write failed; lease recovery required"
            )
        if entitlement.get("reservation_status") == "reserved":
            await _release_if_reserved(
                subscriptions, workspace_id=workspace_id, reservation_id=reservation_id,
            )
        return "provider_rejected"
    except MetaSendUncertain as exc:
        # The provider may have accepted it; never retry and always settle reserved usage.
        await _finish_provider_outcome(
            queue, subscriptions, delivery_id=delivery_id, lease_token=lease_token,
            workspace_id=workspace_id, reservation_id=reservation_id,
            outcome="uncertain", error_code=exc.code[:100],
        )
        return "provider_uncertain"
    except Exception:
        # Once the sender has been invoked, any unclassified exception is treated as uncertain.
        await _finish_provider_outcome(
            queue, subscriptions, delivery_id=delivery_id, lease_token=lease_token,
            workspace_id=workspace_id, reservation_id=reservation_id,
            outcome="uncertain", error_code="provider_outcome_uncertain",
        )
        return "provider_uncertain"

    message_id = result.get("provider_message_id") if isinstance(result, dict) else None
    if not isinstance(message_id, str) or not message_id.strip():
        await _finish_provider_outcome(
            queue, subscriptions, delivery_id=delivery_id, lease_token=lease_token,
            workspace_id=workspace_id, reservation_id=reservation_id,
            outcome="uncertain", error_code="provider_message_id_missing",
        )
        return "provider_uncertain"

    # Provider confirmed a send; settle quota even if persisting the queue state fails.
    completed = await _finish_provider_outcome(
        queue, subscriptions, delivery_id=delivery_id, lease_token=lease_token,
        workspace_id=workspace_id, reservation_id=reservation_id,
        outcome="sent", provider_message_id=message_id,
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
