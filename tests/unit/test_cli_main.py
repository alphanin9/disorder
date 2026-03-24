import json
import sys
import types
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
sys.modules.setdefault("httpx", types.SimpleNamespace(request=None))
if "typer" not in sys.modules:
    class _DummyTyper:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def add_typer(self, *args, **kwargs) -> None:
            pass

        def command(self, *args, **kwargs):
            def _decorator(func):
                return func

            return _decorator

    class _DummyTyperModule:
        Typer = _DummyTyper
        BadParameter = ValueError

        @staticmethod
        def Option(*args, **kwargs):
            return None

        @staticmethod
        def echo(*args, **kwargs) -> None:
            return None

        @staticmethod
        def Argument(*args, **kwargs):
            return None

    sys.modules["typer"] = _DummyTyperModule()

from cli.main import _build_runner_loop_policy_payload


def test_runner_loop_policy_file_can_disable_runner_loop(tmp_path) -> None:
    policy_file = tmp_path / "runner-loop-policy.json"
    policy_file.write_text(json.dumps({"enabled": False}), encoding="utf-8")

    payload = _build_runner_loop_policy_payload(
        enabled=False,
        disable=False,
        target_status=None,
        max_attempts=None,
        retry_on_statuses=None,
        reason_codes=[],
        continue_on_partial_success=True,
        min_seconds_remaining=None,
        instruction_template=None,
        policy_file=policy_file,
    )

    assert payload == {"enabled": False}


def test_runner_loop_policy_explicit_values_enable_runner_loop_when_unspecified() -> None:
    payload = _build_runner_loop_policy_payload(
        enabled=False,
        disable=False,
        target_status=None,
        max_attempts=3,
        retry_on_statuses=None,
        reason_codes=[],
        continue_on_partial_success=False,
        min_seconds_remaining=None,
        instruction_template=None,
        policy_file=None,
    )

    assert payload == {
        "enabled": True,
        "max_attempts": 3,
        "continue_on_partial_success": False,
    }
