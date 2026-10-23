"""One bounded reconciliation pass for abandoned email deliveries.

Run from the backend directory with a trusted scheduler:
    python -m scripts.reconcile_stale_deliveries

This worker never sends or retries messages. It only moves old processing records to
an operator-visible uncertain state, scoped to each workspace.
"""
from __future__ import annotations

import asyncio
import json
import sys

import asyncpg

from app.core.config import settings
from app.services.delivery_store import DeliveryStore

STALE_AGE_SECONDS = 900
PER_WORKSPACE_BATCH = 100
MAX_WORKSPACES_PER_RUN = 100


async def reconcile_once(pool, *, older_than_seconds: int = STALE_AGE_SECONDS,
                         per_workspace_limit: int = PER_WORKSPACE_BATCH,
                         max_workspaces: int = MAX_WORKSPACES_PER_RUN) -> dict[str, int]:
    """Reconcile a bounded number of workspaces without crossing tenant boundaries."""
    if not 60 <= older_than_seconds <= 86400:
        raise ValueError("stale_processing_age_out_of_range")
    if not 1 <= per_workspace_limit <= 500:
        raise ValueError("reconciliation_limit_out_of_range")
    if not 1 <= max_workspaces <= 1000:
        raise ValueError("workspace_batch_limit_out_of_range")

    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """SELECT DISTINCT workspace_id
               FROM outreach_deliveries
               WHERE status='processing'
                 AND processing_at IS NOT NULL
                 AND processing_at < now() - ($1 * interval '1 second')
               ORDER BY workspace_id
               LIMIT $2""",
            older_than_seconds,
            max_workspaces,
        )
    store = DeliveryStore(pool)
    reconciled = 0
    failed_workspaces = 0
    for row in rows:
        workspace_id = row["workspace_id"]
        try:
            reconciled += await store.reconcile_stale_processing(
                workspace_id=workspace_id,
                older_than_seconds=older_than_seconds,
                limit=per_workspace_limit,
            )
        except Exception:
            # Do not print workspace identifiers, message data, DSNs or credentials.
            failed_workspaces += 1
    return {
        "workspaces_seen": len(rows),
        "deliveries_marked_uncertain": reconciled,
        "workspace_errors": failed_workspaces,
    }


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
            timeout=8,
            command_timeout=20,
            server_settings={"application_name": "outreach-delivery-reconciliation"},
        )
        result = await reconcile_once(pool)
        print(json.dumps({"ok": result["workspace_errors"] == 0, **result},
                         separators=(",", ":")))
        return 0 if result["workspace_errors"] == 0 else 1
    except Exception:
        # Keep database connection details and record identifiers out of logs.
        print(json.dumps({"ok": False, "error": "delivery_reconciliation_worker_unavailable"}))
        return 1
    finally:
        if pool is not None:
            await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
