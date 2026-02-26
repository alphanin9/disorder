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
