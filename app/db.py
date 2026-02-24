import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

from app.config import env

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            env.database_url,
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
        logger.info("Database pool created")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


@asynccontextmanager
async def acquire() -> AsyncGenerator[asyncpg.Connection, None]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
