from typing import Any

import httpx

from app.config import get_series_config


def _get_by_path(obj: Any, path: str) -> float:
    """Get nested key value, e.g. 'bitcoin.usd' -> obj['bitcoin']['usd']."""
    for key in path.split("."):
        obj = obj[key]
    return float(obj)


async def fetch_series_value(series_key: str) -> float:
    """Fetch current value for series_a or series_b. Raises on failure."""
    a, b = get_series_config()
    cfg = a if series_key == "belief" else b
    url = cfg.get("url", "")
    params = cfg.get("params") or {}
    value_path = cfg.get("value_path", "")

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    return _get_by_path(data, value_path)
