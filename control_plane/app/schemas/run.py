from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContinuationType = Literal["hint", "deliverable_fix", "strategy_change", "other"]
RunFinalStatus = Literal["flag_found", "deliverable_produced", "blocked", "timeout"]
ContinuationOrigin = Literal["operator", "auto"]

_ALLOWED_AGENT_INVOCATION_ENV_KEYS = {
    "codex": {
        "CODEX_BASE_URL",
        "OPENAI_BASE_URL",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
    },
    "claude_code": {
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
    },
    "mock": set(),
}


class RunBudgetOverrides(BaseModel):
    max_minutes: int = Field(default=30, ge=1, le=24 * 60)
    max_commands: int | None = Field(default=None, ge=1, le=1_000_000)


class AgentInvocationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, min_length=1, max_length=128)
    profile: str | None = Field(default=None, min_length=1, max_length=128)
    extra_args: list[str] = Field(default_factory=list, max_length=32)
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("model", "profile")
    @classmethod
    def validate_scalar_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be empty")
        return normalized

    @field_validator("extra_args")
    @classmethod
    def validate_extra_args(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for entry in value:
            rendered = str(entry).strip()
            if not rendered:
                raise ValueError("extra_args entries must be non-empty strings")
            if len(rendered) > 512:
                raise ValueError("extra_args entries must be 512 characters or fewer")
            normalized.append(rendered)
        return normalized

    @field_validator("env")
    @classmethod
    def validate_env_values(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_val in value.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("env keys must be non-empty strings")
            if len(key) > 128:
                raise ValueError("env keys must be 128 characters or fewer")
            rendered = str(raw_val)
            if len(rendered) > 4096:
                raise ValueError(f"env value for {key} must be 4096 characters or fewer")
            normalized[key] = rendered
        return normalized


class AutoContinuationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_status: RunFinalStatus = "flag_found"


class AutoContinuationWhen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statuses: list[RunFinalStatus] = Field(default_factory=lambda: ["blocked", "timeout"])
    require_contract_match: bool = False

    @field_validator("statuses")
    @classmethod
    def validate_statuses(cls, value: list[RunFinalStatus]) -> list[RunFinalStatus]:
        if not value:
            raise ValueError("statuses must contain at least one terminal status")
        deduped: list[RunFinalStatus] = []
        for entry in value:
            if entry not in deduped:
                deduped.append(entry)
        return deduped


class AutoContinuationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_depth: int = Field(default=3, ge=1, le=20)
    target: AutoContinuationTarget = Field(default_factory=AutoContinuationTarget)
    when: AutoContinuationWhen = Field(default_factory=AutoContinuationWhen)
    on_blocked_reasons: list[str] = Field(default_factory=list, max_length=32)
    continuation_type: ContinuationType = "strategy_change"
    message_template: str = Field(
        default=(
            "Previous run {parent_run_id} ended with status {parent_status} "
            "and reason {failure_reason_code}. Reuse /workspace/continuation "
            "deliverables where useful and continue toward {target_final_status}."
        ),
        min_length=1,
        max_length=2000,
    )
    inherit_agent_invocation: bool = True

    @field_validator("on_blocked_reasons")
    @classmethod
    def validate_reason_codes(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for entry in value:
            rendered = str(entry).strip()
            if not rendered:
                raise ValueError("on_blocked_reasons entries must be non-empty strings")
            if len(rendered) > 128:
                raise ValueError("on_blocked_reasons entries must be 128 characters or fewer")
            if rendered not in normalized:
                normalized.append(rendered)
        return normalized

    @field_validator("message_template")
    @classmethod
    def validate_message_template(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message_template cannot be empty")
        return normalized


def validate_agent_invocation_backend(backend: str, invocation: AgentInvocationConfig | None) -> AgentInvocationConfig | None:
    if invocation is None:
        return None
    allowed = _ALLOWED_AGENT_INVOCATION_ENV_KEYS.get(backend, set())
    unknown = sorted(set(invocation.env) - allowed)
    if unknown:
        raise ValueError(
            f"agent_invocation.env contains unsupported keys for backend {backend}: {', '.join(unknown)}"
        )
    return invocation


class RunCreateRequest(BaseModel):
    challenge_id: UUID
    backend: str = "mock"
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    budgets: RunBudgetOverrides | None = None
    stop_criteria: dict | None = None
    agent_invocation: AgentInvocationConfig | None = None
    auto_continuation_policy: AutoContinuationPolicy | None = None
    local_deploy_enabled: bool = False

    @model_validator(mode="after")
    def validate_agent_invocation(self) -> "RunCreateRequest":
        validate_agent_invocation_backend(self.backend, self.agent_invocation)
        return self


class RunContinueRequest(BaseModel):
    message: str = Field(min_length=1)
    type: ContinuationType | None = None
    time_limit_seconds: int | None = Field(default=None, ge=60, le=24 * 60 * 60)
    stop_criteria_override: dict | None = None
    agent_invocation_override: AgentInvocationConfig | None = None
    auto_continuation_policy_override: AutoContinuationPolicy | None = None
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
    agent_invocation: AgentInvocationConfig = Field(default_factory=AgentInvocationConfig)
    auto_continuation_policy: AutoContinuationPolicy | None = None
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
    continuation_origin: ContinuationOrigin = "operator"


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
    finalization_metadata: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime


class RunFlagSubmissionAttemptRead(BaseModel):
    id: UUID
    run_id: UUID
    challenge_id: UUID
    platform: str
    auth_mode: str | None = None
    submission_hash: str
    verdict_normalized: str
    http_status: int | None = None
    error_message: str | None = None
    submitted_at: datetime


class RunFlagSubmissionListResponse(BaseModel):
    items: list[RunFlagSubmissionAttemptRead]


class RunFlagSubmitRequest(BaseModel):
    flag: str = Field(min_length=1)

    @field_validator("flag")
    @classmethod
    def validate_flag(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("flag cannot be empty")
        return normalized


class RunFlagVerificationRead(BaseModel):
    method: str
    verified: bool
    details: str


class RunFlagSubmitResponse(BaseModel):
    run_id: UUID
    challenge_id: UUID
    flag_verification: RunFlagVerificationRead


class RunStatusResponse(BaseModel):
    run: RunRead
    result: RunResultRead | None = None
    child_runs: list[RunRead] = Field(default_factory=list)


class RunListResponse(BaseModel):
    items: list[RunRead]
