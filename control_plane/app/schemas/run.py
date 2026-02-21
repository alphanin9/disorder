from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ContinuationType = Literal["hint", "deliverable_fix", "strategy_change", "other"]


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


class RunContinueRequest(BaseModel):
    message: str = Field(min_length=1)
    type: ContinuationType | None = None
    time_limit_seconds: int | None = Field(default=None, ge=60, le=24 * 60 * 60)
    stop_criteria_override: dict | None = None
    reuse_parent_artifacts: bool = True

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message cannot be empty")
        return normalized

    @field_validator("stop_criteria_override")
    @classmethod
    def validate_stop_criteria_override(cls, value: dict | None) -> dict | None:
        if value is None:
            return None
        for key in ("primary", "secondary"):
            if key not in value:
                continue
            entry = value[key]
            if not isinstance(entry, dict):
                raise ValueError(f"stop_criteria_override.{key} must be an object")
            if "type" in entry and not isinstance(entry["type"], str):
                raise ValueError(f"stop_criteria_override.{key}.type must be a string")
            if "config" in entry and not isinstance(entry["config"], dict):
                raise ValueError(f"stop_criteria_override.{key}.config must be an object")
        return value


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
    parent_run_id: UUID | None = None
    continuation_depth: int
    continuation_input: str | None = None
    continuation_type: ContinuationType | None = None


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
    child_runs: list[RunRead] = Field(default_factory=list)


class RunListResponse(BaseModel):
    items: list[RunRead]
