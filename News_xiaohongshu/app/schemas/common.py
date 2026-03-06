from __future__ import annotations

from pydantic import BaseModel


class MessageResponse(BaseModel):
    success: bool
    message: str


class HealthResponse(BaseModel):
    success: bool
    service: str
    env: str

