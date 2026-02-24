from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_yaml(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/divergence",
        description="PostgreSQL connection URL",
    )
    telegram_bot_token: str = Field(default="", description="Telegram Bot token from BotFather")
    config_path: str = Field(default="config/config.yaml", description="Path to admin YAML config")
    log_level: str = Field(default="INFO", description="Log level")


env = EnvSettings()


def get_config() -> dict[str, Any]:
    path = Path(env.config_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return _load_yaml(path)


def get_poll_interval_minutes() -> int:
    cfg = get_config()
    return cfg.get("polling", {}).get("interval_minutes", 10)


def get_z_score_window() -> int:
    cfg = get_config()
    return cfg.get("polling", {}).get("z_score_window", 24)


def get_default_thresholds() -> tuple[float, float, int]:
    cfg = get_config()
    d = cfg.get("defaults", {})
    return (
        float(d.get("open_threshold", 2.0)),
        float(d.get("close_threshold", 0.5)),
        int(d.get("cooldown_minutes", 60)),
    )


def get_series_config() -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = get_config()
    a = cfg.get("series_a", {})
    b = cfg.get("series_b", {})
    return a, b
