from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_stale_delivered_feedback_cannot_advance_followup_sequence():
    source = (ROOT / "app" / "services" / "email_provider_event_store.py").read_text(encoding="utf-8")
    update_start = source.index("status_applied = await conn.fetchval(")
    followup_start = source.index('if event_type == "delivered" and status_applied:')
    suppression_start = source.index("suppression_reason = {", followup_start)
    assert update_start < followup_start < suppression_start
    status_update = source[update_start:followup_start]
    assert "provider_status_at <= $3" in status_update
    assert "RETURNING TRUE" in status_update


def test_suppression_feedback_is_not_skipped_when_provider_event_is_stale():
    source = (ROOT / "app" / "services" / "email_provider_event_store.py").read_text(encoding="utf-8")
    followup_guard = source.index('if event_type == "delivered" and status_applied:')
    suppression_start = source.index("suppression_reason = {", followup_guard)
    assert "if status_applied" not in source[suppression_start:]


def test_provider_event_webhook_authenticates_exact_raw_body_and_limits_size():
    source = (ROOT / "app" / "api" / "email_provider_webhook_routes.py").read_text(encoding="utf-8")
    assert "MAX_BODY_BYTES = 64 * 1024" in source
    assert "expected_signature(raw, secret)" in source
    assert "hmac.compare_digest" in source
    assert "extra=\"forbid\"" in source
    assert "workspace_id" not in source[source.index("class EmailProviderEvent"):source.index("def expected_signature")]


def test_one_click_unsubscribe_is_recipient_bound_and_hmac_signed():
    source = (ROOT / "app" / "api" / "email_provider_webhook_routes.py").read_text(encoding="utf-8")
    assert "hmac.new(secret.encode(\"utf-8\"), payload, hashlib.sha256)" in source
    assert "workspace_id, prospect_raw, email = payload.decode(\"utf-8\").split(\"\\n\", 2)" in source
    assert "email=email" in source
