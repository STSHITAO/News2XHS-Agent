from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PublishResponse(BaseModel):
    success: bool
    task_id: int
    status: str
    message: str
    response_payload: dict | None = None


class PublishTaskOut(BaseModel):
    id: int
    draft_id: int
    status: str
    error_message: str
    created_at: datetime
    updated_at: datetime

