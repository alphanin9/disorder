import pytest
from pydantic import ValidationError

from control_plane.app.schemas.run import RunContinueRequest, RunCreateRequest


def test_run_create_accepts_budget_overrides() -> None:
    payload = RunCreateRequest.model_validate(
        {
            "challenge_id": "11111111-1111-1111-1111-111111111111",
            "backend": "mock",
            "reasoning_effort": "high",
            "budgets": {"max_minutes": 45, "max_commands": 120},
            "local_deploy_enabled": False,
        }
    )
    assert payload.budgets is not None
    assert payload.reasoning_effort == "high"
    assert payload.budgets.max_minutes == 45
    assert payload.budgets.max_commands == 120


def test_run_create_accepts_agent_invocation_and_auto_continuation_policy() -> None:
    payload = RunCreateRequest.model_validate(
        {
            "challenge_id": "11111111-1111-1111-1111-111111111111",
            "backend": "codex",
            "agent_invocation": {
                "model": "gpt-5.4",
                "extra_args": ["--search", "full"],
                "env": {"CODEX_BASE_URL": "https://api.example"},
            },
            "auto_continuation_policy": {
                "enabled": True,
                "max_depth": 4,
                "target": {"final_status": "flag_found"},
                "when": {"statuses": ["blocked", "timeout"]},
                "on_blocked_reasons": ["provider_quota_or_auth"],
            },
        }
    )
    assert payload.agent_invocation is not None
    assert payload.agent_invocation.model == "gpt-5.4"
    assert payload.auto_continuation_policy is not None
    assert payload.auto_continuation_policy.max_depth == 4


def test_run_create_rejects_agent_invocation_env_for_wrong_backend() -> None:
    with pytest.raises(ValidationError):
        RunCreateRequest.model_validate(
            {
                "challenge_id": "11111111-1111-1111-1111-111111111111",
                "backend": "mock",
                "agent_invocation": {
                    "env": {"CODEX_BASE_URL": "https://api.example"},
                },
            }
        )


def test_run_create_rejects_invalid_max_minutes() -> None:
    with pytest.raises(ValidationError):
        RunCreateRequest.model_validate(
            {
                "challenge_id": "11111111-1111-1111-1111-111111111111",
                "backend": "mock",
                "budgets": {"max_minutes": 0, "max_commands": None},
                "local_deploy_enabled": False,
            }
        )


def test_run_create_rejects_invalid_reasoning_effort() -> None:
    with pytest.raises(ValidationError):
        RunCreateRequest.model_validate(
            {
                "challenge_id": "11111111-1111-1111-1111-111111111111",
                "backend": "mock",
                "reasoning_effort": "ultra",
                "local_deploy_enabled": False,
            }
        )


def test_run_continue_requires_non_empty_message() -> None:
    with pytest.raises(ValidationError):
        RunContinueRequest.model_validate({"message": "   "})


def test_run_continue_accepts_valid_stop_override_shape() -> None:
    payload = RunContinueRequest.model_validate(
        {
            "message": "use angr for path exploration",
            "type": "strategy_change",
            "stop_criteria_override": {
                "primary": {"type": "FLAG_FOUND", "config": {"regex": "flag\\{.+\\}"}},
                "secondary": {"config": {"required_files": ["README.md", "solve.py"]}},
            },
        }
    )
    assert payload.type == "strategy_change"
    assert payload.stop_criteria_override is not None


def test_run_continue_rejects_non_object_stop_override_entry() -> None:
    with pytest.raises(ValidationError):
        RunContinueRequest.model_validate(
            {
                "message": "retry",
                "stop_criteria_override": {"primary": "FLAG_FOUND"},
            }
        )


def test_run_continue_accepts_agent_invocation_override() -> None:
    payload = RunContinueRequest.model_validate(
        {
            "message": "retry with different model",
            "agent_invocation_override": {
                "model": "gpt-5.4",
                "extra_args": ["--full-auto"],
            },
            "auto_continuation_policy_override": {
                "enabled": False,
                "max_depth": 2,
            },
        }
    )
    assert payload.agent_invocation_override is not None
    assert payload.agent_invocation_override.extra_args == ["--full-auto"]
    assert payload.auto_continuation_policy_override is not None
    assert payload.auto_continuation_policy_override.enabled is False
