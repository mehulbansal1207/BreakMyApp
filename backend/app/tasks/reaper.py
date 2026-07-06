"""Periodic reaper task — detects and cleans up stale scans.

Scans can get stuck at status="running" forever when the worker process dies
mid-task (OOM kill, container restart, hard time-limit SIGKILL, etc.) without
ever reaching the final DB update.  This task, scheduled via Celery Beat every
5 minutes, finds scans whose `updated_at` has not been bumped for 15+ minutes
and marks them as failed.

Why `updated_at` and not `created_at`?
    Every call to update_progress() in analysis.py triggers a session.commit(),
    which bumps the Scan model's `updated_at` via its onupdate=datetime.utcnow
    column default.  A legitimately-running scan on a large repo may take many
    minutes, but its `updated_at` keeps advancing.  Checking `created_at` would
    incorrectly kill these slow-but-healthy scans.

Staleness threshold (15 min) vs. time limits (hard=600s / soft=540s):
    The 15-minute threshold is deliberately longer than the 10-minute hard time
    limit so the reaper only catches scans where the worker process itself died —
    not scans that Celery's own time limits should have already caught.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.celery_app import celery_app
from app.core.config import settings
from app.models.scan import Scan

logger = logging.getLogger(__name__)

STALE_THRESHOLD_MINUTES = 15


async def _reap_stale_scans() -> int:
    """Find scans stuck at status='running' for over STALE_THRESHOLD_MINUTES
    and mark them as failed.  Returns the number of scans reaped."""

    engine = create_async_engine(settings.DATABASE_URL, future=True)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=STALE_THRESHOLD_MINUTES)

        async with session_factory() as session:
            result = await session.execute(
                select(Scan).where(
                    Scan.status == "running",
                    Scan.updated_at < cutoff,
                )
            )
            stale_scans = result.scalars().all()

            if not stale_scans:
                logger.info("Reaper: no stale scans found.")
                return 0

            reaped_ids = []
            for scan in stale_scans:
                scan.status = "failed"
                # Overwrite findings with the error — any partial results from a
                # dead worker are unreliable so we don't attempt to merge them.
                scan.findings = {
                    "error": (
                        "Scan timed out or the worker process died unexpectedly. "
                        "Please try again."
                    )
                }
                reaped_ids.append(str(scan.id))

            await session.commit()

            logger.warning(
                f"Reaper: reaped {len(reaped_ids)} stale scan(s): {reaped_ids}"
            )
            return len(reaped_ids)
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.reaper.reap_stale_scans")
def reap_stale_scans() -> int:
    """Celery entry-point — runs the async reaper and returns the count."""
    return asyncio.run(_reap_stale_scans())
