"""Worker process for recurring workspace growth schedules."""
from __future__ import annotations
import asyncio
import logging
import asyncpg
from app.core.config import settings
from app.services.workspace_growth_schedule_runner import WorkspaceGrowthScheduleRunner
from app.services.subscription_store import SubscriptionStore

logger = logging.getLogger("outreach.scheduler")
POLL_SECONDS = 10

async def run_scheduler(*, poll_seconds: float = POLL_SECONDS) -> None:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the scheduler")
    if not 1 <= poll_seconds <= 60:
        raise ValueError("poll_seconds must be between 1 and 60")
    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=3, timeout=5, command_timeout=15)
    runner = WorkspaceGrowthScheduleRunner(pool, SubscriptionStore(pool))
    logger.info("workspace growth schedule dispatcher started")
    try:
        while True:
            try:
                item = await runner.enqueue_one_due()
                if item is None:
                    await asyncio.sleep(poll_seconds)
                else:
                    logger.info("growth schedule processed schedule_id=%s outcome=%s", item["schedule_id"], item["outcome"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Avoid logging exception messages that may contain database or provider details.
                logger.error("growth schedule dispatch failed; retrying after a bounded delay error_type=%s",
                             type(exc).__name__)
                await asyncio.sleep(poll_seconds)
    finally:
        await pool.close()
        logger.info("workspace growth schedule dispatcher stopped")

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scheduler())

if __name__ == "__main__":
    main()
