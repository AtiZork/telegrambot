import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.alerts import process_divergence_score
from app.config import get_default_thresholds, get_config
from app.db import acquire
from app.poller import run_poll_cycle
from app.telegram_client import send_alert, send_alerts

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Health ---

class HealthResponse(BaseModel):
    status: str
    database: str
    config_loaded: bool


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    config_loaded = bool(get_config())
    try:
        async with acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "ok"
    except Exception as e:
        logger.warning("Health check DB failed: %s", e)
        db_status = "error"
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        config_loaded=config_loaded,
    )


# --- Users and thresholds ---

class RegisterUserRequest(BaseModel):
    telegram_id: int
    username: Optional[str] = None


class RegisterUserResponse(BaseModel):
    user_id: int
    telegram_id: int
    message: str


@router.post("/users/register", response_model=RegisterUserResponse)
async def register_user(body: RegisterUserRequest) -> RegisterUserResponse:
    open_th, close_th, cooldown = get_default_thresholds()
    async with acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO users (telegram_id, username)
                VALUES ($1, $2)
                ON CONFLICT (telegram_id) DO UPDATE SET username = EXCLUDED.username, updated_at = NOW()
                RETURNING id, telegram_id
                """,
                body.telegram_id,
                body.username,
            )
        except Exception as e:
            logger.exception("Register user failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))
        uid = row["id"]
        # Ensure thresholds exist for user
        await conn.execute(
            """
            INSERT INTO user_thresholds (user_id, open_threshold, close_threshold, cooldown_minutes)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO NOTHING
            """,
            uid,
            open_th,
            close_th,
            cooldown,
        )
    return RegisterUserResponse(
        user_id=uid,
        telegram_id=body.telegram_id,
        message="Registered; using default thresholds. Set custom thresholds via PATCH /users/{user_id}/thresholds",
    )


class ThresholdsUpdate(BaseModel):
    open_threshold: Optional[float] = None
    close_threshold: Optional[float] = None
    cooldown_minutes: Optional[int] = None


@router.patch("/users/{user_id}/thresholds")
async def update_thresholds(user_id: int, body: ThresholdsUpdate) -> dict:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        updates = []
        values = []
        pos = 1
        if body.open_threshold is not None:
            updates.append(f"open_threshold = ${pos}")
            values.append(body.open_threshold)
            pos += 1
        if body.close_threshold is not None:
            updates.append(f"close_threshold = ${pos}")
            values.append(body.close_threshold)
            pos += 1
        if body.cooldown_minutes is not None:
            updates.append(f"cooldown_minutes = ${pos}")
            values.append(body.cooldown_minutes)
            pos += 1
        if not updates:
            return {"message": "No changes"}
        values.append(user_id)
        await conn.execute(
            f"UPDATE user_thresholds SET {', '.join(updates)} WHERE user_id = ${pos}",
            *values,
        )
    return {"message": "Thresholds updated"}


# --- Test Telegram (debug) ---


@router.post("/test-telegram/{user_id}")
async def test_telegram(user_id: int) -> dict:
    """Send a test message to this user's Telegram. Use to verify token and chat_id."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT telegram_id FROM users WHERE id = $1",
            user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        telegram_id = row["telegram_id"]
    ok = await send_alert(
        telegram_id,
        status="TEST",
        score=0.0,
    )
    if not ok:
        raise HTTPException(status_code=502, detail="Telegram send failed; check server logs and TELEGRAM_BOT_TOKEN")
    return {"message": "Test message sent", "telegram_id": telegram_id}


# --- Trigger one poll now (for testing) ---


@router.post("/trigger-poll")
async def trigger_poll() -> dict:
    """Run one poll cycle now. If divergence score crosses thresholds, alerts are sent."""
    score, div_id = await run_poll_cycle()
    if score is None or div_id is None:
        return {"message": "Poll done; no divergence score yet (need more history)", "score": None}
    events = await process_divergence_score(score, div_id)
    if events:
        await send_alerts(events, score)
    return {
        "message": "Poll done",
        "score": round(score, 4),
        "alerts_sent": len(events),
    }
