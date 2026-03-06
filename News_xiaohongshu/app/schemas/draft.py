from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DraftGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    max_news_items: int = Field(default=5, ge=1, le=20)


class DraftStatusUpdateRequest(BaseModel):
    notes: str = ""


class DraftUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=20)
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    cover_image_url: str = ""
    editor_notes: str = ""


class DraftOut(BaseModel):
    id: int
    topic: str
    title: str
    content: str
    tags: list[str]
    cover_image_url: str
    status: str
    editor_notes: str
    created_at: datetime
    updated_at: datetime


class DraftGenerateResponse(BaseModel):
    success: bool
    draft: DraftOut
    auto_cover_generated: bool = False
    auto_cover_provider: str = ""
    auto_cover_error: str = ""
