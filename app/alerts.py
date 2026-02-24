import logging
from datetime import datetime, timezone, timedelta
from typing import List, Tuple

import asyncpg

from app.config import get_default_thresholds
from app.db import acquire

logger = logging.getLogger(__name__)

STATUS_OPEN = "OPEN"
STATUS_UPDATE = "UPDATE"
STATUS_CLOSED = "CLOSED"


async def get_user_thresholds(conn: asyncpg.Connection, user_id: int) -> Tuple[float, float, int]:
    """(open_threshold, close_threshold, cooldown_minutes) for user."""
    row = await conn.fetchrow(
        "SELECT open_threshold, close_threshold, cooldown_minutes FROM user_thresholds WHERE user_id = $1",
        user_id,
    )
    if row:
        return float(row["open_threshold"]), float(row["close_threshold"]), int(row["cooldown_minutes"])
    return get_default_thresholds()


async def get_users_to_notify() -> List[Tuple[int, int]]:
    """List of (user_id, telegram_id) for all users with thresholds."""
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT u.id, u.telegram_id FROM users u"
        )
        return [(r["id"], r["telegram_id"]) for r in rows]


async def get_open_alert(conn: asyncpg.Connection, user_id: int) -> asyncpg.Record | None:
    """Current OPEN alert for user, if any."""
    return await conn.fetchrow(
        "SELECT id, score_at_open, score_current, opened_at FROM alerts WHERE user_id = $1 AND status = $2",
        user_id,
        STATUS_OPEN,
    )


async def cooldown_until(conn: asyncpg.Connection, user_id: int) -> datetime | None:
    """Earliest time we can OPEN a new alert for this user."""
    row = await conn.fetchrow(
        "SELECT cooldown_until FROM alerts WHERE user_id = $1 AND cooldown_until IS NOT NULL AND cooldown_until > NOW() ORDER BY cooldown_until DESC LIMIT 1",
        user_id,
    )
    return row["cooldown_until"].replace(tzinfo=timezone.utc) if row and row["cooldown_until"] else None


async def process_divergence_for_user(
    conn: asyncpg.Connection,
    user_id: int,
    score: float,
    divergence_score_id: int,
) -> str | None:
    """
    Apply lifecycle and cooldown for one user. Returns new status if something changed (OPEN/UPDATE/CLOSED), else None.
    """
    open_thresh, close_thresh, cooldown_min = await get_user_thresholds(conn, user_id)
    now = datetime.now(timezone.utc)
    open_alert = await get_open_alert(conn, user_id)

    # Already have an OPEN alert
    if open_alert:
        aid = open_alert["id"]
        if score <= close_thresh:
            # Close it
            await conn.execute(
                """
                UPDATE alerts SET status = $1, score_current = $2, last_updated_at = $3, closed_at = $3,
                cooldown_until = $4
                WHERE id = $5
                """,
                STATUS_CLOSED,
                score,
                now,
                now + timedelta(minutes=cooldown_min),
                aid,
            )
            await conn.execute(
                "INSERT INTO alert_events (alert_id, from_status, to_status, score) VALUES ($1, $2, $3, $4)",
                aid, STATUS_OPEN, STATUS_CLOSED, score,
            )
            logger.info("User %s alert %s CLOSED (score %.4f <= %.4f)", user_id, aid, score, close_thresh)
            return STATUS_CLOSED
        else:
            # Update
            await conn.execute(
                "UPDATE alerts SET score_current = $1, last_updated_at = $2, divergence_score_id = $3 WHERE id = $4",
                score, now, divergence_score_id, aid,
            )
            await conn.execute(
                "INSERT INTO alert_events (alert_id, from_status, to_status, score) VALUES ($1, $2, $3, $4)",
                aid, STATUS_OPEN, STATUS_UPDATE, score,
            )
            logger.info("User %s alert %s UPDATE (score %.4f)", user_id, aid, score)
            return STATUS_UPDATE

    # No open alert: maybe open one
    if score < open_thresh:
        return None

    until = await cooldown_until(conn, user_id)
    if until and now < until:
        logger.info("User %s in cooldown until %s; skip OPEN (score %.4f)", user_id, until, score)
        return None

    # Open new alert
    row = await conn.fetchrow(
        """
        INSERT INTO alerts (user_id, status, divergence_score_id, score_at_open, score_current, cooldown_until)
        VALUES ($1, $2, $3, $4, $5, NULL)
        RETURNING id
        """,
        user_id,
        STATUS_OPEN,
        divergence_score_id,
        score,
        score,
    )
    aid = row["id"]
    await conn.execute(
        "INSERT INTO alert_events (alert_id, from_status, to_status, score) VALUES ($1, NULL, $2, $3)",
        aid, STATUS_OPEN, score,
    )
    logger.info("User %s new OPEN alert (score %.4f >= %.4f)", user_id, score, open_thresh)
    return STATUS_OPEN


async def process_divergence_score(score: float, divergence_score_id: int) -> List[Tuple[int, int, str]]:
    """
    For each user, apply lifecycle. Returns list of (user_id, telegram_id, status) for users that got OPEN/UPDATE/CLOSED.
    """
    users = await get_users_to_notify()
    if not users:
        return []

    results: List[Tuple[int, int, str]] = []
    async with acquire() as conn:
        for user_id, telegram_id in users:
            new_status = await process_divergence_for_user(conn, user_id, score, divergence_score_id)
            if new_status:
                results.append((user_id, telegram_id, new_status))
    return results
