import pytest
from pydantic import ValidationError

from control_plane.app.schemas.run import RunCreateRequest


def test_run_create_accepts_budget_overrides() -> None:
    payload = RunCreateRequest.model_validate(
        {
            "challenge_id": "11111111-1111-1111-1111-111111111111",
            "backend": "mock",
            "budgets": {"max_minutes": 45, "max_commands": 120},
            "local_deploy_enabled": False,
        }
    )
    assert payload.budgets is not None
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
