"""One-shot bounded reconciliation of persisted WhatsApp delivery statuses.

Run from the backend directory:
  python -m scripts.reconcile_whatsapp_delivery_statuses
Schedule periodically after webhook processing and dispatch workers.
"""
from __future__ import annotations

import asyncio
import json
import sys

import asyncpg

from app.core.config import settings
from app.services.whatsapp_status_reconciliation import reconcile_whatsapp_delivery_statuses


async def main() -> int:
    dsn = (settings.database_url or "").strip()
    if not dsn.startswith(("postgres://", "postgresql://")):
        print(json.dumps({"ok": False, "error": "database_url_not_configured"}))
        return 2
    pool = None
    try:
        pool = await asyncpg.create_pool(
            dsn=dsn, min_size=1, max_size=2, command_timeout=20, timeout=8,
            server_settings={"application_name": "outreach-whatsapp-status-reconciler"},
        )
        result = await reconcile_whatsapp_delivery_statuses(pool, batch_size=250)
        print(json.dumps({"ok": True, **result}, separators=(",", ":")))
        return 0
    except Exception:
        print(json.dumps({"ok": False, "error": "whatsapp_status_reconciliation_unavailable"}))
        return 1
    finally:
        if pool is not None:
            await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
