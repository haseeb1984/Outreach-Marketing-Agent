"""Explicitly gated Meta WhatsApp outbound dispatcher.

A single attempt is made per claimed delivery. Policy is re-evaluated immediately
before send; transport ambiguity is terminal and never automatically retried.
"""
from __future__ import annotations

from uuid import UUID

from app.core.config import settings
from app.services.whatsapp_credential_store import WhatsAppCredentialStore, WhatsAppCredentialUnavailable
from app.services.whatsapp_meta_sender import MetaSendRejected, MetaSendUncertain, MetaWhatsAppSender
from app.services.whatsapp_outbound_store import WhatsAppOutboundStore
from app.services.whatsapp_send_policy import WhatsAppSendPolicy


async def process_whatsapp_outbound(pool, *, limit: int = 10) -> dict[str, int]:
    if not settings.whatsapp_dispatch_enabled:
        raise RuntimeError("whatsapp_dispatch_not_enabled")
    if not 1 <= limit <= 50:
        raise ValueError("whatsapp_dispatch_limit_out_of_range")

    store = WhatsAppOutboundStore(pool)
    subscriptions = None
    from app.services.subscription_store import SubscriptionStore
    subscriptions = SubscriptionStore(pool)
    claimed = await store.claim_batch(limit=limit, lease_seconds=180)
    result = {"claimed": len(claimed), "sent": 0, "failed": 0, "cancelled": 0, "uncertain": 0}

    for item in claimed:
        delivery_id = UUID(item["id"])
        lease_token = UUID(item["lease_token"])
        workspace_id = item["workspace_id"]
        reservation_id = item["usage_reservation_id"]
        outcome = "uncertain"
        error_code = "whatsapp_dispatch_unexpected_failure"
        provider_message_id = None
        try:
            async with pool.acquire() as conn:
                context = await conn.fetchrow(
                    """SELECT d.body,p.contact_phone_e164
                       FROM outreach_drafts d
                       JOIN crm_prospects p
                         ON p.id=d.prospect_id AND p.workspace_id=d.workspace_id
                       WHERE d.id=$1 AND d.workspace_id=$2 AND p.id=$3""",
                    UUID(item["draft_id"]), workspace_id, UUID(item["prospect_id"]),
                )
            if context is None:
                outcome, error_code = "cancelled", "whatsapp_draft_or_prospect_missing"
            else:
                decision = await WhatsAppSendPolicy(pool).evaluate(
                    workspace_id=workspace_id,
                    account_id=UUID(item["account_id"]),
                    prospect_id=UUID(item["prospect_id"]),
                    draft_id=UUID(item["draft_id"]),
                    template_name=item.get("template_name"),
                    language_code=item.get("language_code"),
                )
                if not decision.get("allowed"):
                    outcome, error_code = "cancelled", str(decision.get("reason") or "whatsapp_policy_denied")[:100]
                else:
                    credentials = await WhatsAppCredentialStore(pool).get_active_credentials(
                        workspace_id=workspace_id, account_id=UUID(item["account_id"]),
                    )
                    if decision.get("requires_approved_template"):
                        sent = await MetaWhatsAppSender().send(
                            version=(settings.meta_graph_api_version or ""),
                            phone_number_id=credentials.phone_number_id,
                            access_token=credentials.access_token,
                            recipient=context["contact_phone_e164"],
                            template_name=decision["template_name"],
                            language_code=decision["language_code"],
                        )
                    else:
                        sent = await MetaWhatsAppSender().send(
                            version=(settings.meta_graph_api_version or ""),
                            phone_number_id=credentials.phone_number_id,
                            access_token=credentials.access_token,
                            recipient=context["contact_phone_e164"],
                            body=context["body"],
                        )
                    outcome = "sent"
                    provider_message_id = sent["provider_message_id"]
                    error_code = None
        except MetaSendRejected:
            outcome, error_code = "failed", "meta_provider_rejected_request"
        except MetaSendUncertain:
            outcome, error_code = "uncertain", "meta_provider_outcome_uncertain"
        except WhatsAppCredentialUnavailable:
            outcome, error_code = "failed", "whatsapp_credentials_unavailable"
        except ValueError:
            outcome, error_code = "failed", "whatsapp_dispatch_payload_invalid"
        except Exception:
            # The adapter itself converts ambiguous network outcomes to uncertain;
            # other exceptions here are preflight failures before provider dispatch.
            outcome, error_code = "failed", "whatsapp_dispatch_preflight_failed"

        try:
            finished = await store.finish_claim(
                delivery_id=delivery_id, lease_token=lease_token, outcome=outcome,
                provider_message_id=provider_message_id, error_code=error_code,
            )
        except Exception:
            finished = False
        if not finished:
            # Lease expiry recovery consumes quota and marks uncertain. Never retry.
            continue
        reservation_outcome = "released" if outcome in {"failed", "cancelled"} else "consumed"
        await subscriptions.finish_reservation(
            workspace_id=workspace_id,
            reservation_id=reservation_id,
            outcome=reservation_outcome,
        )
        result[outcome] += 1

    result["expired_claims_recovered"] = await store.mark_expired_claims_uncertain(limit=100)
    return result
