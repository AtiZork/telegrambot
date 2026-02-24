import logging
from typing import List, Tuple

import asyncpg

from app.config import get_config, get_z_score_window
from app.db import acquire
from app.fetcher import fetch_series_value
from app.zscore import rolling_z_score

logger = logging.getLogger(__name__)

SERIES_BELIEF = "belief"
SERIES_PRICE = "price"


async def get_recent_changes(conn: asyncpg.Connection, series_type: str, limit: int) -> List[float]:
    """Last `limit` value_change values for the series (oldest first for consistent order)."""
    rows = await conn.fetch(
        """
        SELECT value_change FROM snapshots
        WHERE series_type = $1 AND value_change IS NOT NULL
        ORDER BY ts DESC
        LIMIT $2
        """,
        series_type,
        limit,
    )
    changes = [float(r["value_change"]) for r in reversed(rows)]
    return changes


async def save_snapshot(
    conn: asyncpg.Connection,
    series_type: str,
    value_raw: float,
    value_change: float | None,
    z_score: float | None,
    window_size: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO snapshots (ts, series_type, value_raw, value_change, z_score, window_size)
        VALUES (NOW(), $1, $2, $3, $4, $5)
        """,
        series_type,
        value_raw,
        value_change,
        z_score,
        window_size,
    )


async def save_divergence(
    conn: asyncpg.Connection,
    score: float,
    belief_change: float | None,
    price_change: float | None,
    belief_z: float | None,
    price_z: float | None,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO divergence_scores (ts, score, belief_change, price_change, belief_z, price_z)
        VALUES (NOW(), $1, $2, $3, $4, $5)
        RETURNING id
        """,
        score,
        belief_change,
        price_change,
        belief_z,
        price_z,
    )
    return row["id"]


async def get_previous_value(conn: asyncpg.Connection, series_type: str) -> float | None:
    row = await conn.fetchrow(
        "SELECT value_raw FROM snapshots WHERE series_type = $1 ORDER BY ts DESC LIMIT 1",
        series_type,
    )
    return float(row["value_raw"]) if row else None


async def run_poll_cycle() -> Tuple[float | None, int | None]:
    """
    Fetch both series, compute changes, rolling z-scores, and divergence.
    Returns (divergence_score, divergence_scores.id) or (None, None) if insufficient data.
    """
    window = get_z_score_window()
    async with acquire() as conn:
        # Fetch current values
        try:
            belief_raw = await fetch_series_value(SERIES_BELIEF)
            price_raw = await fetch_series_value(SERIES_PRICE)
        except Exception as e:
            logger.exception("Failed to fetch series: %s", e)
            return None, None

        # Previous values for change
        prev_belief = await get_previous_value(conn, SERIES_BELIEF)
        prev_price = await get_previous_value(conn, SERIES_PRICE)

        belief_change = (belief_raw - prev_belief) if prev_belief is not None else None
        price_change = (price_raw - prev_price) if prev_price is not None else None

        # Rolling z-scores of changes
        belief_changes = await get_recent_changes(conn, SERIES_BELIEF, window)
        price_changes = await get_recent_changes(conn, SERIES_PRICE, window)

        if belief_change is not None:
            belief_changes_for_z = belief_changes.copy()
            z_belief = rolling_z_score(belief_changes_for_z, belief_change)
        else:
            z_belief = None

        if price_change is not None:
            price_changes_for_z = price_changes.copy()
            z_price = rolling_z_score(price_changes_for_z, price_change)
        else:
            z_price = None

        # Persist snapshots (always store raw; change/z when available)
        await save_snapshot(
            conn, SERIES_BELIEF, belief_raw, belief_change, z_belief, window
        )
        await save_snapshot(
            conn, SERIES_PRICE, price_raw, price_change, z_price, window
        )

        # Divergence = z(belief change) - z(price change)
        if z_belief is not None and z_price is not None:
            score = z_belief - z_price
            div_id = await save_divergence(
                conn, score, belief_change, price_change, z_belief, z_price
            )
            logger.info(
                "divergence computed score=%.4f belief_z=%.4f price_z=%.4f",
                score, z_belief, z_price,
            )
            return score, div_id

        logger.info("Insufficient history for divergence; skipping")
        return None, None
