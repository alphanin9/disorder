from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RunBudgetOverrides(BaseModel):
    max_minutes: int = Field(default=30, ge=1, le=24 * 60)
    max_commands: int | None = Field(default=None, ge=1, le=1_000_000)


class RunCreateRequest(BaseModel):
    challenge_id: UUID
    backend: str = "mock"
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    budgets: RunBudgetOverrides | None = None
    stop_criteria: dict | None = None
    local_deploy_enabled: bool = False


class RunRead(BaseModel):
    id: UUID
    challenge_id: UUID
    backend: str
    budgets: dict
    stop_criteria: dict
    allowed_endpoints: list[dict]
    paths: dict
    local_deploy: dict
    status: str
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class RunLogsResponse(BaseModel):
    run_id: UUID
    offset: int
    next_offset: int
    eof: bool
    logs: str


class RunResultRead(BaseModel):
    run_id: UUID
    status: str
    result_json_object_key: str
    logs_object_key: str
    started_at: datetime
    finished_at: datetime


class RunStatusResponse(BaseModel):
    run: RunRead
    result: RunResultRead | None = None


class RunListResponse(BaseModel):
    items: list[RunRead]
