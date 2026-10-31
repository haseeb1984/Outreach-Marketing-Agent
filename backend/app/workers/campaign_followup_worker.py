"""Supervised worker that materializes due follow-up steps as approval drafts only."""
from __future__ import annotations

import asyncio
import logging

import asyncpg

from app.core.config import settings
from app.services.followup_store import FollowupStore

logger = logging.getLogger("outreach.followup_scheduler")
POLL_SECONDS = 15
BATCH_SIZE = 50


async def run_worker(*, poll_seconds: float = POLL_SECONDS, batch_size: int = BATCH_SIZE) -> None:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the follow-up scheduler")
    if not 1 <= poll_seconds <= 60:
        raise ValueError("poll_seconds must be between 1 and 60")
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100")
    pool = await asyncpg.create_pool(
        dsn=settings.database_url, min_size=1, max_size=3, timeout=5, command_timeout=20,
    )
    store = FollowupStore(pool)
    logger.info("campaign follow-up scheduler started")
    try:
        while True:
            try:
                result = await store.process_due(limit=batch_size)
                if result["drafts_created"] or result["stopped"] or result["skipped"]:
                    logger.info(
                        "follow-up batch completed drafts_created=%s stopped=%s skipped=%s",
                        result["drafts_created"], result["stopped"], result["skipped"],
                    )
                else:
                    await asyncio.sleep(poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("follow-up scheduler failed error_type=%s", type(exc).__name__)
                await asyncio.sleep(poll_seconds)
    finally:
        await pool.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
