from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 18060
    LOG_LEVEL: str = "INFO"

    MCP_PROTOCOL_VERSION: str = "2025-06-18"

    HEADLESS: bool = True
    # Publishing on XHS creator center is more stable in headed mode.
    PUBLISH_HEADLESS: bool = False
    BROWSER_SLOW_MO: int = 0
    BROWSER_TIMEOUT_MS: int = 60_000
    STORAGE_STATE_PATH: str = "./cookies.json"
    DOWNLOAD_DIR: str = "./downloads"
    USER_AGENT: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def storage_state_path(self) -> Path:
        return Path(self.STORAGE_STATE_PATH).resolve()

    @property
    def download_dir(self) -> Path:
        return Path(self.DOWNLOAD_DIR).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
