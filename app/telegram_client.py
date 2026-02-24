"""Send Telegram alerts to users."""

import logging
from typing import List, Tuple

from telegram import Bot
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

from app.config import env

logger = logging.getLogger(__name__)

# Longer timeouts so Telegram API doesn't time out on slow networks (default is 5s)
TELEGRAM_REQUEST = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0)


def _format_message(user_id: int, status: str, score: float) -> str:
    return (
        f"🔔 Divergence Alert\n"
        f"Status: {status}\n"
        f"Score: {score:.4f}\n"
        f"(Event A vs Market B divergence)"
    )


async def send_alert(telegram_id: int, status: str, score: float) -> bool:
    if not env.telegram_bot_token:
        logger.warning("Telegram token not set; skipping send")
        return False
    try:
        bot = Bot(token=env.telegram_bot_token, request=TELEGRAM_REQUEST)
        text = _format_message(0, status, score)
        await bot.send_message(chat_id=telegram_id, text=text)
        logger.info("Telegram alert sent to %s: %s", telegram_id, status)
        return True
    except TelegramError as e:
        logger.exception("Telegram send failed for %s: %s", telegram_id, e)
        return False


async def send_alerts(events: List[Tuple[int, int, str]], score: float) -> None:
    """events: list of (user_id, telegram_id, status)."""
    for user_id, telegram_id, status in events:
        await send_alert(telegram_id, status, score)
