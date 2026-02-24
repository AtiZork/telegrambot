import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.alerts import process_divergence_score
from app.config import get_poll_interval_minutes
from app.poller import run_poll_cycle
from app.telegram_client import send_alerts

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


async def _tick() -> None:
    try:
        score, div_id = await run_poll_cycle()
        if score is not None and div_id is not None:
            events = await process_divergence_score(score, div_id)
            if events:
                await send_alerts(events, score)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("Poll cycle error: %s", e)


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    interval_min = get_poll_interval_minutes()
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _tick,
        trigger=IntervalTrigger(minutes=interval_min),
        id="poll_divergence",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started (interval=%s min)", interval_min)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Scheduler stopped")
