"""PostgreSQL integration tests for provider connection lifecycle invariants."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from app.services.auth_security import hash_password


MIGRATIONS = (
    "001_workspace_domain_verification.sql",
    "002_workspace_jobs.sql",
    "003_authentication_foundation.sql",
    "004_auth_rate_limits.sql",
    "005_session_csrf_tokens.sql",
    "006_password_reset_tokens.sql",
    "007_workspace_outreach_drafts.sql",
    "008_workspace_campaigns.sql",
    "009_workspace_prospects.sql",
    "010_draft_prospect_link.sql",
    "011_whatsapp_opt_in_evidence.sql",
    "012_workspace_provider_connections.sql",
    "013_provider_connection_lifecycle_guard.sql",
    "014_provider_oauth_transactions.sql",
)


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_provider_connection_lifecycle_guard_enforces_validation_and_terminal_revocation():
    asyncio.run(_exercise_lifecycle_guard())


async def _exercise_lifecycle_guard() -> None:
    connection = await asyncpg.connect(os.environ["OMA_TEST_DATABASE_URL"])
    try:
        migrations = Path(__file__).resolve().parents[1] / "migrations"
        for migration_name in MIGRATIONS:
            await connection.execute((migrations / migration_name).read_text(encoding="utf-8"))

        user_id = uuid4()
        workspace_id = "provider-lifecycle-" + uuid4().hex
        await connection.execute(
            """INSERT INTO app_users
               (id, email, password_hash, email_verified_at, status)
               VALUES ($1, $2, $3, now(), 'active')""",
            user_id, f"{user_id.hex}@example.test",
            hash_password("provider-lifecycle-test-password").encoded,
        )
        await connection.execute("INSERT INTO workspaces (id) VALUES ($1)", workspace_id)
        await connection.execute(
            """INSERT INTO workspace_memberships (workspace_id, user_id, role, status)
               VALUES ($1, $2, 'owner', 'active')""",
            workspace_id, user_id,
        )
        connection_id = await connection.fetchval(
            """INSERT INTO workspace_provider_connections
               (workspace_id, provider, display_label, created_by)
               VALUES ($1, 'email', 'Integration test mailbox', $2)
               RETURNING id""",
            workspace_id, user_id,
        )

        # A raw status update cannot fabricate a successful provider authorization.
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "UPDATE workspace_provider_connections SET status='connected' WHERE id=$1",
                connection_id,
            )

        # A complete validation record is required before the connected state is allowed.
        await connection.execute(
            """UPDATE workspace_provider_connections
               SET status='connected', provider_account_id='provider-account-test',
                   secret_reference='vault-prod:provider-connection-test',
                   granted_scopes=ARRAY['messages.read'], last_validated_at=now()
               WHERE id=$1""",
            connection_id,
        )
        assert await connection.fetchval(
            "SELECT status FROM workspace_provider_connections WHERE id=$1", connection_id
        ) == "connected"

        # A later metadata-only update must not be able to erase connected-state proof.
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "UPDATE workspace_provider_connections SET secret_reference=NULL WHERE id=$1",
                connection_id,
            )

        await connection.execute(
            "UPDATE workspace_provider_connections SET status='revoked' WHERE id=$1",
            connection_id,
        )
        assert await connection.fetchval(
            "SELECT revoked_at IS NOT NULL FROM workspace_provider_connections WHERE id=$1",
            connection_id,
        ) is True

        # Revocation is terminal; reconnecting must create a fresh intent/record.
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                """UPDATE workspace_provider_connections
                   SET status='connected', provider_account_id='provider-account-test',
                       secret_reference='vault-prod:provider-connection-test',
                       granted_scopes=ARRAY['messages.read'], last_validated_at=now()
                   WHERE id=$1""",
                connection_id,
            )

        # OAuth state is bound to one pending connection and can be consumed only once.
        from app.services.workspace_provider_oauth_transaction_store import (
            WorkspaceProviderOAuthTransactionStore, new_oauth_state,
        )
        pending_id = await connection.fetchval(
            """INSERT INTO workspace_provider_connections
               (workspace_id, provider, display_label, created_by)
               VALUES ($1, 'email', 'OAuth integration mailbox', $2) RETURNING id""",
            workspace_id, user_id,
        )
        pool = await asyncpg.create_pool(os.environ["OMA_TEST_DATABASE_URL"], min_size=1, max_size=2)
        try:
            oauth_store = WorkspaceProviderOAuthTransactionStore(pool)
            state = new_oauth_state()
            nonce = new_oauth_state()
            transaction = await oauth_store.create(
                workspace_id=workspace_id, connection_id=pending_id, user_id=user_id,
                provider="email", state=state, pkce_challenge="A" * 43,
                verifier_secret_reference="vault-prod:pkce-verifier-ref",
                redirect_uri="https://app.example.test/oauth/email/callback",
                allowed_redirect_uris=("https://app.example.test/oauth/email/callback",),
                nonce=nonce, lifetime_seconds=600,
            )
            assert transaction["connection_id"] == str(pending_id)
            assert "verifier_secret_reference" not in transaction
            consumed = await oauth_store.consume(state=state)
            assert consumed is not None
            assert consumed["verifier_secret_reference"] == "vault-prod:pkce-verifier-ref"
            assert "nonce_sha256" in consumed
            assert await oauth_store.consume(state=state) is None
            assert await oauth_store.consume(state="x") is None

            # Only the verified-metadata persistence method can move an intent into
            # connected state through the application store, and it audits the transition.
            from app.services.workspace_provider_connection_store import WorkspaceProviderConnectionStore
            connected_intent = await pool.fetchval(
                """INSERT INTO workspace_provider_connections
                   (workspace_id, provider, display_label, created_by)
                   VALUES ($1, 'email', 'Verified connection test', $2) RETURNING id""",
                workspace_id, user_id,
            )
            connection_store = WorkspaceProviderConnectionStore(pool)
            connected = await connection_store.mark_connected_after_validation(
                workspace_id=workspace_id,
                connection_id=connected_intent,
                user_id=str(user_id),
                provider="email",
                provider_account_id="provider-account-verified-test",
                secret_reference="vault-prod:provider-credentials-test",
                granted_scopes=("messages.read",),
            )
            assert connected is not None
            assert connected["status"] == "connected"
            assert "secret_reference" not in connected

            # Another workspace member cannot activate a connection they did not create.
            other_user_id = uuid4()
            await pool.execute(
                """INSERT INTO app_users
                   (id, email, password_hash, email_verified_at, status)
                   VALUES ($1, $2, $3, now(), 'active')""",
                other_user_id, f"{other_user_id.hex}@example.test",
                hash_password("provider-lifecycle-other-user-password").encoded,
            )
            with pytest.raises(ValueError, match="invalid_granted_scopes"):
                await connection_store.mark_connected_after_validation(
                    workspace_id=workspace_id,
                    connection_id=connected_intent,
                    user_id=str(user_id),
                    provider="email",
                    provider_account_id="provider-account-verified-test",
                    secret_reference="vault-prod:provider-credentials-test",
                    granted_scopes=(),
                )
            other_intent = await pool.fetchval(
                """INSERT INTO workspace_provider_connections
                   (workspace_id, provider, display_label, created_by)
                   VALUES ($1, 'email', 'Other creator test', $2) RETURNING id""",
                workspace_id, user_id,
            )
            assert await connection_store.mark_connected_after_validation(
                workspace_id=workspace_id,
                connection_id=other_intent,
                user_id=str(other_user_id),
                provider="email",
                provider_account_id="provider-account-wrong-actor",
                secret_reference="vault-prod:provider-credentials-test",
                granted_scopes=("messages.read",),
            ) is None
            assert await pool.fetchval(
                "SELECT status FROM workspace_provider_connections WHERE id=$1",
                other_intent,
            ) == "pending"

            assert await pool.fetchval(
                """SELECT count(*) FROM security_audit_events
                   WHERE workspace_id=$1 AND event_type='provider_connection.verified_connected'
                     AND metadata->>'connection_id'=$2""",
                workspace_id, str(connected_intent),
            ) == 1
        finally:
            await pool.close()
    finally:
        await connection.close()
