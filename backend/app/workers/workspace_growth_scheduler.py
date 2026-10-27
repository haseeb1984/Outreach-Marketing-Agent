"""Worker process for recurring workspace growth schedules."""
from __future__ import annotations
import asyncio
import logging
import asyncpg
from app.core.config import settings
from app.services.workspace_growth_schedule_runner import WorkspaceGrowthScheduleRunner

logger = logging.getLogger("outreach.scheduler")
POLL_SECONDS = 10

async def run_scheduler(*, poll_seconds: float = POLL_SECONDS) -> None:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the scheduler")
    if not 1 <= poll_seconds <= 60:
        raise ValueError("poll_seconds must be between 1 and 60")
    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=3, timeout=5, command_timeout=15)
    runner = WorkspaceGrowthScheduleRunner(pool)
    logger.info("workspace growth schedule dispatcher started")
    try:
        while True:
            try:
                item = await runner.enqueue_one_due()
                if item is None:
                    await asyncio.sleep(poll_seconds)
                else:
                    logger.info("growth schedule enqueued schedule_id=%s job_id=%s", item["schedule_id"], item["job_id"])
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("growth schedule dispatch failed; retrying after a bounded delay")
                await asyncio.sleep(poll_seconds)
    finally:
        await pool.close()

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scheduler())

if __name__ == "__main__":
    main()
