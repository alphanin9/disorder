from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from control_plane.app.db.models import ChallengeManifest, Run, RunResult
from control_plane.app.schemas.run import RunContinueRequest
from control_plane.app.services.run_service import RunContinuationError, create_continuation_run


class _FakeBlobStore:
    def __init__(self, result_payload: dict) -> None:
        self._result_payload = result_payload

    def get_bytes(self, _object_key: str) -> bytes:
        return json.dumps(self._result_payload, indent=2).encode("utf-8")


class _FakeSession:
    def __init__(self, *, challenge: ChallengeManifest, parent_run: Run, parent_result: RunResult | None) -> None:
        self.challenge = challenge
        self.parent_run = parent_run
        self.parent_result = parent_result
        self.child_run: Run | None = None
        self.commit_calls = 0
        self.rollback_calls = 0
        self.flush_calls = 0

    def get(self, model, key):
        if model is Run and key == self.parent_run.id:
            return self.parent_run
        if model is ChallengeManifest and key == self.challenge.id:
            return self.challenge
        if model is RunResult and key == self.parent_run.id:
            return self.parent_result
        if model is Run and self.child_run is not None and key == self.child_run.id:
            return self.child_run
        return None

    def add(self, obj) -> None:
        self.child_run = obj

    def flush(self) -> None:
        self.flush_calls += 1
        if self.child_run is not None and getattr(self.child_run, "id", None) is None:
            self.child_run.id = uuid4()

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def refresh(self, obj) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()


def _make_parent_run(challenge_id):
    return Run(
        id=uuid4(),
        challenge_id=challenge_id,
        backend="codex",
        budgets={"max_minutes": 30, "max_commands": None, "reasoning_effort": "high"},
        stop_criteria={
            "primary": {"type": "FLAG_FOUND", "config": {"regex": "flag\\{.*?\\}"}},
            "secondary": {"type": "DELIVERABLES_READY", "config": {"required_files": ["README.md"]}},
        },
        allowed_endpoints=[],
        paths={"chal_mount": "/workspace/chal", "run_mount": "/workspace/run"},
        local_deploy={"enabled": False, "network": None, "endpoints": []},
        status="deliverable_produced",
        started_at=datetime.now(timezone.utc),
        continuation_depth=0,
    )


def test_create_continuation_run_creates_child_and_context_bundle(tmp_path) -> None:
    challenge = ChallengeManifest(
        id=uuid4(),
        ctf_id=uuid4(),
        platform="manual",
        platform_challenge_id="chal-1",
        name="Warmup",
        category="misc",
        points=100,
        description_md="desc",
        description_raw=None,
        artifacts=[],
        remote_endpoints=[{"type": "tcp", "host": "example", "port": 31337}],
        local_deploy_hints={},
        flag_regex=None,
    )
    parent_run = _make_parent_run(challenge.id)
    parent_result = RunResult(
        run_id=parent_run.id,
        status="deliverable_produced",
        result_json_object_key="runs/parent/result.json",
        logs_object_key="runs/parent/logs.txt",
        started_at=parent_run.started_at,
        finished_at=datetime.now(timezone.utc),
    )

    parent_run_dir = tmp_path / str(parent_run.id) / "run"
    parent_run_dir.mkdir(parents=True)
    (parent_run_dir / "README.md").write_text("# Parent\n\nFindings", encoding="utf-8")

    session = _FakeSession(challenge=challenge, parent_run=parent_run, parent_result=parent_result)
    settings = SimpleNamespace(
        enable_run_continuation=True,
        max_continuation_message_chars=500,
        max_continuation_depth=3,
        runs_dir=tmp_path,
    )

    request = RunContinueRequest.model_validate(
        {
            "message": "recheck stack canary with pwndbg",
            "type": "hint",
            "time_limit_seconds": 120,
            "reuse_parent_artifacts": True,
            "stop_criteria_override": {
                "secondary": {"config": {"required_files": ["README.md", "solve.py"]}},
            },
        }
    )

    child_run = create_continuation_run(
        session,
        parent_run_id=parent_run.id,
        request=request,
        settings=settings,
        blob_store=_FakeBlobStore(result_payload={"status": "deliverable_produced"}),
    )

    assert child_run.parent_run_id == parent_run.id
    assert child_run.continuation_depth == 1
    assert child_run.continuation_input == "recheck stack canary with pwndbg"
    assert child_run.continuation_type == "hint"
    assert child_run.budgets["max_minutes"] == 2
    assert child_run.paths["continuation_mount"] == "/workspace/continuation"

    context_dir = tmp_path / str(child_run.id) / "continuation"
    assert (context_dir / "parent_result.json").exists()
    assert (context_dir / "parent_readme.md").exists()
    request_payload = json.loads((context_dir / "continuation_request.json").read_text(encoding="utf-8"))
    assert request_payload["message"] == "recheck stack canary with pwndbg"
    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    assert session.flush_calls == 1


def test_create_continuation_run_rejects_non_terminal_parent(tmp_path) -> None:
    challenge = ChallengeManifest(
        id=uuid4(),
        ctf_id=uuid4(),
        platform="manual",
        platform_challenge_id="chal-1",
        name="Warmup",
        category="misc",
        points=100,
        description_md="desc",
        description_raw=None,
        artifacts=[],
        remote_endpoints=[],
        local_deploy_hints={},
        flag_regex=None,
    )
    parent_run = _make_parent_run(challenge.id)
    parent_run.status = "running"

    session = _FakeSession(challenge=challenge, parent_run=parent_run, parent_result=None)
    settings = SimpleNamespace(
        enable_run_continuation=True,
        max_continuation_message_chars=500,
        max_continuation_depth=3,
        runs_dir=tmp_path,
    )

    with pytest.raises(RunContinuationError, match="terminal status"):
        create_continuation_run(
            session,
            parent_run_id=parent_run.id,
            request=RunContinueRequest(message="retry"),
            settings=settings,
            blob_store=_FakeBlobStore(result_payload={}),
        )


def test_create_continuation_run_rejects_depth_limit(tmp_path) -> None:
    challenge = ChallengeManifest(
        id=uuid4(),
        ctf_id=uuid4(),
        platform="manual",
        platform_challenge_id="chal-1",
        name="Warmup",
        category="misc",
        points=100,
        description_md="desc",
        description_raw=None,
        artifacts=[],
        remote_endpoints=[],
        local_deploy_hints={},
        flag_regex=None,
    )
    parent_run = _make_parent_run(challenge.id)
    parent_run.continuation_depth = 2

    session = _FakeSession(challenge=challenge, parent_run=parent_run, parent_result=None)
    settings = SimpleNamespace(
        enable_run_continuation=True,
        max_continuation_message_chars=500,
        max_continuation_depth=2,
        runs_dir=tmp_path,
    )

    with pytest.raises(RunContinuationError, match="depth limit"):
        create_continuation_run(
            session,
            parent_run_id=parent_run.id,
            request=RunContinueRequest(message="retry"),
            settings=settings,
            blob_store=_FakeBlobStore(result_payload={}),
        )


def test_create_continuation_run_rejects_long_message(tmp_path) -> None:
    challenge = ChallengeManifest(
        id=uuid4(),
        ctf_id=uuid4(),
        platform="manual",
        platform_challenge_id="chal-1",
        name="Warmup",
        category="misc",
        points=100,
        description_md="desc",
        description_raw=None,
        artifacts=[],
        remote_endpoints=[],
        local_deploy_hints={},
        flag_regex=None,
    )
    parent_run = _make_parent_run(challenge.id)

    session = _FakeSession(challenge=challenge, parent_run=parent_run, parent_result=None)
    settings = SimpleNamespace(
        enable_run_continuation=True,
        max_continuation_message_chars=8,
        max_continuation_depth=3,
        runs_dir=tmp_path,
    )

    with pytest.raises(RunContinuationError, match="max length"):
        create_continuation_run(
            session,
            parent_run_id=parent_run.id,
            request=RunContinueRequest(message="message too long"),
            settings=settings,
            blob_store=_FakeBlobStore(result_payload={}),
        )


def test_create_continuation_run_rolls_back_when_context_bundle_write_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    challenge = ChallengeManifest(
        id=uuid4(),
        ctf_id=uuid4(),
        platform="manual",
        platform_challenge_id="chal-1",
        name="Warmup",
        category="misc",
        points=100,
        description_md="desc",
        description_raw=None,
        artifacts=[],
        remote_endpoints=[],
        local_deploy_hints={},
        flag_regex=None,
    )
    parent_run = _make_parent_run(challenge.id)
    parent_result = RunResult(
        run_id=parent_run.id,
        status="deliverable_produced",
        result_json_object_key="runs/parent/result.json",
        logs_object_key="runs/parent/logs.txt",
        started_at=parent_run.started_at,
        finished_at=datetime.now(timezone.utc),
    )
    session = _FakeSession(challenge=challenge, parent_run=parent_run, parent_result=parent_result)
    settings = SimpleNamespace(
        enable_run_continuation=True,
        max_continuation_message_chars=500,
        max_continuation_depth=3,
        runs_dir=tmp_path,
    )

    def _raise_bundle_error(**_kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "control_plane.app.services.run_service.create_continuation_context_bundle",
        _raise_bundle_error,
    )

    with pytest.raises(OSError, match="disk full"):
        create_continuation_run(
            session,
            parent_run_id=parent_run.id,
            request=RunContinueRequest(message="retry", reuse_parent_artifacts=True),
            settings=settings,
            blob_store=_FakeBlobStore(result_payload={}),
        )

    assert session.flush_calls == 1
    assert session.commit_calls == 0
    assert session.rollback_calls == 1
