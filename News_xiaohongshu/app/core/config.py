from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "News Xiaohongshu"
    APP_ENV: str = "dev"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 5100
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = ""
    DB_DIALECT: str = "mysql"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456789"
    DB_NAME: str = "news_xiaohongshu"
    DB_CHARSET: str = "utf8mb4"

    SEARCH_TOOL_TYPE: str = "AnspireAPI"
    ENABLE_FUNCTION_CALLING: bool = True

    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = ""
    QWEN_MODEL: str = "Qwen/Qwen2.5-72B-Instruct"
    QWEN_TIMEOUT: int = 90

    ANSPIRE_API_KEY: str = ""
    ANSPIRE_BASE_URL: str = "https://plugin.anspire.cn/api/ntsearch/search"
    BOCHA_WEB_SEARCH_API_KEY: str = ""
    BOCHA_BASE_URL: str = "https://api.bocha.cn/v1/ai-search"
    TAVILY_API_KEY: str = ""

    # Text-to-image provider (OpenAI-compatible by default)
    IMAGE_GEN_PROVIDER: str = "MockAPI"
    IMAGE_GEN_API_KEY: str = ""
    IMAGE_GEN_BASE_URL: str = ""
    IMAGE_GEN_MODEL: str = ""
    IMAGE_GEN_TIMEOUT: int = 120
    IMAGE_GEN_DEFAULT_SIZE: str = "1024x1024"
    IMAGE_GEN_OUTPUT_DIR: str = "static/uploads/covers/generated"
    AUTO_GENERATE_COVER_ON_DRAFT: bool = True
    AUTO_GENERATE_COVER_STRICT: bool = False

    XHS_MCP_BASE_URL: str = "http://127.0.0.1:18060"
    XHS_MCP_API_KEY: str = ""
    XHS_PUBLISH_TIMEOUT: int = 180
    PUBLISH_GUARD_TOKEN: str = ""

    # Cover image strategy
    LOCAL_COVER_ONLY: bool = True
    DEFAULT_LOCAL_COVER_IMAGE_PATH: str = "./DJI_20240603095231_0001_D_bottom_left.JPG"

    SCHEDULER_ENABLED: bool = True
    HOT_NEWS_DEFAULT_QUERY: str = "热点新闻"
    HOT_NEWS_INTERVAL_MINUTES: int = 30
    HOT_NEWS_DEFAULT_LIMIT: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlachemy_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.DB_DIALECT.lower() == "sqlite":
            return "sqlite:///./news_xiaohongshu.db"
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset={self.DB_CHARSET}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
