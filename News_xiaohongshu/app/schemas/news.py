from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HotFetchRequest(BaseModel):
    query: str = Field(default="热点新闻", min_length=1)
    limit: int = Field(default=20, ge=1, le=100)
    period: str = Field(default="24h")


class NewsItemOut(BaseModel):
    id: int
    title: str
    url: str
    summary: str
    source: str
    published_at: datetime | None = None


class HotFetchResponse(BaseModel):
    success: bool
    query: str
    provider: str
    selected_tool: str
    count: int
    items: list[NewsItemOut]

