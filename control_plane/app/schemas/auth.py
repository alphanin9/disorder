from __future__ import annotations

from datetime import datetime

from typing import Any

from pydantic import BaseModel, Field


class CodexAuthFileRead(BaseModel):
    id: str
    tag: str
    file_name: str
    sha256: str
    size_bytes: int
    uploaded_at: datetime
    source: str | None = None
    health_status: str | None = None
    last_checked_at: datetime | None = None
    last_health_error: str | None = None
    limit_status: str | None = None
    last_limit_checked_at: datetime | None = None
    last_limit_error: str | None = None
    quota_snapshot: dict[str, Any] | None = None


class CodexAuthTagRead(BaseModel):
    tag: str
    file_count: int
    files: list[CodexAuthFileRead]


class CodexAuthStatusResponse(BaseModel):
    configured: bool
    active_tag: str | None = None
    tags: list[CodexAuthTagRead] = Field(default_factory=list)
    health_status: str = "unknown"
    reauth_required: bool = False
    limit_status: str = "unknown"


class CodexAuthSetActiveTagRequest(BaseModel):
    tag: str


class CodexDeviceAuthStartRequest(BaseModel):
    tag: str = "default"


class CodexDeviceAuthStartResponse(BaseModel):
    flow_id: str
    tag: str
    user_code: str
    verification_uri: str
    expires_at: datetime
    interval_seconds: int
    status: str = "pending"


class CodexDeviceAuthPollResponse(BaseModel):
    flow_id: str
    tag: str
    status: str
    message: str | None = None
    auth_file: CodexAuthFileRead | None = None
    auth_status: CodexAuthStatusResponse | None = None
