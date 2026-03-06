from __future__ import annotations

from pydantic import BaseModel, Field


class CoverGenerateRequest(BaseModel):
    prompt: str | None = Field(default=None, description="Image prompt. If omitted and draft_id is provided, auto-build from draft.")
    draft_id: int | None = Field(default=None)
    size: str | None = Field(default=None, description="Image size such as 1024x1024")
    overwrite_draft_cover: bool = Field(default=True)


class CoverGenerateResponse(BaseModel):
    success: bool
    provider: str
    model: str
    prompt: str
    cover_image_url: str
    cover_preview_url: str
    draft_id: int | None = None
    draft_updated: bool = False

