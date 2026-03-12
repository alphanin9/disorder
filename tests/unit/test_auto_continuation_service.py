from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from control_plane.app.db.models import Run, RunResult
from control_plane.app.services.auto_continuation_service import evaluate_and_queue_auto_continuation


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, existing_child_id=None) -> None:
        self.existing_child_id = existing_child_id
        self.commit_calls = 0
        self.refresh_calls = 0

    def execute(self, _statement):
        return _ScalarResult(self.existing_child_id)

    def commit(self) -> None:
        self.commit_calls += 1

    def refresh(self, _obj) -> None:
        self.refresh_calls += 1


def _make_run(*, status: str = "blocked", depth: int = 0, policy: dict | None = None) -> Run:
    return Run(
        id=uuid4(),
        challenge_id=uuid4(),
        parent_run_id=None,
        continuation_depth=depth,
        continuation_input=None,
        continuation_type=None,
        continuation_origin="operator",
        backend="codex",
        budgets={"max_minutes": 30, "reasoning_effort": "medium"},
        stop_criteria={},
        agent_invocation={"model": "gpt-5.4"},
        auto_continuation_policy=policy,
        allowed_endpoints=[],
        paths={"chal_mount": "/workspace/chal", "run_mount": "/workspace/run"},
        local_deploy={"enabled": False, "network": None, "endpoints": []},
        status=status,
        error_message=None,
        started_at=datetime.now(timezone.utc),
    )


def _make_result(run: Run, *, status: str, metadata: dict | None = None) -> RunResult:
    return RunResult(
        run_id=run.id,
        status=status,
        result_json_object_key=f"runs/{run.id}/result.json",
        logs_object_key=f"runs/{run.id}/logs.txt",
        finalization_metadata=metadata or {},
        started_at=run.started_at,
        finished_at=datetime.now(timezone.utc),
    )


def test_auto_continuation_does_not_queue_when_target_already_met() -> None:
    run = _make_run(
        status="flag_found",
        policy={
            "enabled": True,
            "max_depth": 3,
            "target": {"final_status": "flag_found"},
            "when": {"statuses": ["blocked", "timeout"], "require_contract_match": False},
        },
    )
    result = _make_result(run, status="flag_found", metadata={"contract_valid": True, "failure_reason_code": "none"})
    session = _FakeSession()

    child = evaluate_and_queue_auto_continuation(
        db=session,
        run=run,
        result=result,
        settings=SimpleNamespace(max_continuation_depth=5),
        blob_store=object(),
    )

    assert child is None
    assert result.finalization_metadata["auto_continuation"]["reason"] == "target_already_met"
    assert session.commit_calls == 1


def test_auto_continuation_queues_child_when_policy_matches(monkeypatch) -> None:
    run = _make_run(
        policy={
            "enabled": True,
            "max_depth": 3,
            "target": {"final_status": "flag_found"},
            "when": {"statuses": ["blocked", "timeout"], "require_contract_match": False},
            "on_blocked_reasons": ["provider_quota_or_auth"],
            "inherit_agent_invocation": False,
        },
    )
    result = _make_result(
        run,
        status="blocked",
        metadata={"contract_valid": True, "failure_reason_code": "provider_quota_or_auth"},
    )
    session = _FakeSession()
    captured: dict[str, object] = {}

    def _fake_create_continuation_run(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(
        "control_plane.app.services.auto_continuation_service.create_continuation_run",
        _fake_create_continuation_run,
    )

    child = evaluate_and_queue_auto_continuation(
        db=session,
        run=run,
        result=result,
        settings=SimpleNamespace(max_continuation_depth=5),
        blob_store=object(),
    )

    assert child is not None
    assert captured["continuation_origin"] == "auto"
    assert captured["inherit_parent_agent_invocation"] is False
    assert captured["request"].message
    assert result.finalization_metadata["auto_continuation"]["queued"] is True
    assert session.commit_calls == 1


def test_auto_continuation_skips_when_child_already_exists() -> None:
    run = _make_run(
        policy={
            "enabled": True,
            "max_depth": 3,
            "target": {"final_status": "flag_found"},
            "when": {"statuses": ["blocked"], "require_contract_match": False},
        },
    )
    result = _make_result(
        run,
        status="blocked",
        metadata={"contract_valid": True, "failure_reason_code": "sandbox_exit_nonzero"},
    )
    session = _FakeSession(existing_child_id=uuid4())

    child = evaluate_and_queue_auto_continuation(
        db=session,
        run=run,
        result=result,
        settings=SimpleNamespace(max_continuation_depth=5),
        blob_store=object(),
    )

    assert child is None
    assert result.finalization_metadata["auto_continuation"]["reason"] == "child_already_exists"
