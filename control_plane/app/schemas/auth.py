from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CodexAuthFileRead(BaseModel):
    id: str
    tag: str
    file_name: str
    sha256: str
    size_bytes: int
    uploaded_at: datetime


class CodexAuthTagRead(BaseModel):
    tag: str
    file_count: int
    files: list[CodexAuthFileRead]


class CodexAuthStatusResponse(BaseModel):
    configured: bool
    active_tag: str | None = None
    tags: list[CodexAuthTagRead] = Field(default_factory=list)


class CodexAuthSetActiveTagRequest(BaseModel):
    tag: str
