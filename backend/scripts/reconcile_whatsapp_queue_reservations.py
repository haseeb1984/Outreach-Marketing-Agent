"""Release abandoned WhatsApp quota reservations with no durable queue row.

Run from the backend directory with a trusted scheduler:
    python -m scripts.reconcile_whatsapp_queue_reservations

This bounded worker never sends messages and never touches reservations linked to
an outbound queue record. It only releases old orphan reservations after a one-hour
safety window, covering a process crash between quota reservation and queue insert.
"""
from __future__ import annotations

import asyncio
import json
import sys

import asyncpg

from app.core.config import settings

ORPHAN_AGE_SECONDS = 3600
BATCH_LIMIT = 250


async def reconcile_once(pool, *, older_than_seconds: int = ORPHAN_AGE_SECONDS,
                         limit: int = BATCH_LIMIT) -> dict[str, int]:
    if not 3600 <= older_than_seconds <= 604800:
        raise ValueError("orphan_age_out_of_range")
    if not 1 <= limit <= 1000:
        raise ValueError("batch_limit_out_of_range")

    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """WITH orphaned AS (
                       SELECT u.id
                       FROM feature_usage_reservations u
                       WHERE u.feature='whatsapp_sends'
                         AND u.status='reserved'
                         AND u.idempotency_key LIKE 'whatsapp-send:%'
                         AND u.created_at < now() - ($1 * interval '1 second')
                         AND NOT EXISTS (
                             SELECT 1 FROM whatsapp_outbound_deliveries q
                             WHERE q.usage_reservation_id=u.id
                         )
                       ORDER BY u.created_at,u.id
                       LIMIT $2
                       FOR UPDATE OF u SKIP LOCKED
                   )
                   UPDATE feature_usage_reservations u
                   SET status='released',updated_at=now()
                   FROM orphaned o
                   WHERE u.id=o.id AND u.status='reserved'
                   RETURNING u.id""",
                older_than_seconds, limit,
            )
    return {"orphan_reservations_released": len(rows)}


async def main() -> int:
    dsn = (settings.database_url or "").strip()
    if not dsn.startswith(("postgres://", "postgresql://")):
        print(json.dumps({"ok": False, "error": "database_url_not_configured"}))
        return 2
    pool = None
    try:
        pool = await asyncpg.create_pool(
            dsn=dsn, min_size=1, max_size=2, timeout=8, command_timeout=20,
            server_settings={"application_name": "outreach-whatsapp-quota-reconciliation"},
        )
        result = await reconcile_once(pool)
        print(json.dumps({"ok": True, **result}, separators=(",", ":")))
        return 0
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 2
    except Exception:
        # Never log DSNs, credentials, contact details, or provider payloads.
        print(json.dumps({
            "ok": False,
            "error": "whatsapp_quota_reconciliation_unavailable",
        }, separators=(",", ":")))
        return 1
    finally:
        if pool is not None:
            await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
