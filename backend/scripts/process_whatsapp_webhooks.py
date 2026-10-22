"""Run one bounded batch of WhatsApp webhook events from a trusted scheduler.

Example (from the backend directory): python -m scripts.process_whatsapp_webhooks
The scheduler should invoke this command periodically; it is deliberately a one-shot job
so the platform's scheduler owns retries, timeouts and concurrency.
"""
from __future__ import annotations

import asyncio
import json
import sys

import asyncpg

from app.core.config import settings
from app.services.whatsapp_event_processor import process_pending_whatsapp_events


async def main() -> int:
    dsn = (settings.database_url or "").strip()
    if not dsn.startswith(("postgres://", "postgresql://")):
        print(json.dumps({"ok": False, "error": "database_url_not_configured"}))
        return 2
    pool = None
    try:
        pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=2,
            command_timeout=20,
            timeout=8,
            server_settings={"application_name": "outreach-whatsapp-event-worker"},
        )
        result = await process_pending_whatsapp_events(pool, batch_size=25)
        print(json.dumps({"ok": result["failed"] == 0, **result}, separators=(",", ":")))
        return 0 if result["failed"] == 0 else 1
    except Exception:
        # Never print DSNs, provider payloads, phone numbers or credentials.
        print(json.dumps({"ok": False, "error": "whatsapp_worker_unavailable"}))
        return 1
    finally:
        if pool is not None:
            await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
