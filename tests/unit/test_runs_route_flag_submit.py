from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.app.api.routes import runs as runs_routes
from control_plane.app.db.models import Run, RunResult


class _FakeDB:
    def __init__(self, challenge) -> None:
        self._challenge = challenge
        self.commit_calls = 0
        self.rollback_calls = 0
        self.result_row = None

    def get(self, model, key):
        if model is runs_routes.ChallengeManifest:
            return self._challenge
        if model is runs_routes.RunResult:
            return self.result_row
        return None

    def add(self, obj) -> None:
        if isinstance(obj, RunResult):
            self.result_row = obj

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def refresh(self, _obj) -> None:
        return None


def test_submit_run_flag_route_returns_verification_and_commits(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(runs_routes.router)

    run_id = uuid4()
    challenge_id = uuid4()
    fake_run = SimpleNamespace(id=run_id, challenge_id=challenge_id)
    fake_challenge = SimpleNamespace(
        id=challenge_id,
        flag_regex=None,
        ctf=SimpleNamespace(default_flag_regex=r"^flag\{.+\}$"),
    )
    fake_db = _FakeDB(fake_challenge)
    captured: dict[str, object] = {}

    monkeypatch.setattr(runs_routes, "get_run_or_none", lambda _db, rid: fake_run if rid == run_id else None)

    def _fake_build_flag_verification(db, *, run_id, challenge, flag, regex):
        captured["db"] = db
        captured["run_id"] = run_id
        captured["challenge"] = challenge
        captured["flag"] = flag
        captured["regex"] = regex
        return {"method": "platform_submit", "verified": True, "details": "CTFd submission verdict: Correct"}

    monkeypatch.setattr(runs_routes, "build_flag_verification", _fake_build_flag_verification)

    def _override_get_db():
        yield fake_db

    app.dependency_overrides[runs_routes.get_db] = _override_get_db
    client = TestClient(app)

    response = client.post(f"/runs/{run_id}/submit-flag", json={"flag": "  flag{demo}  "})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == str(run_id)
    assert payload["challenge_id"] == str(challenge_id)
    assert payload["flag_verification"]["method"] == "platform_submit"
    assert payload["flag_verification"]["verified"] is True

    assert captured["db"] is fake_db
    assert captured["run_id"] == run_id
    assert captured["challenge"] is fake_challenge
    assert captured["flag"] == "flag{demo}"
    assert captured["regex"] == r"^flag\{.+\}$"
    assert fake_db.commit_calls == 1
    assert fake_db.rollback_calls == 0


def test_terminate_run_route_does_not_queue_auto_continuation(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(runs_routes.router)

    run_id = uuid4()
    challenge_id = uuid4()
    fake_run = Run(
        id=run_id,
        challenge_id=challenge_id,
        parent_run_id=None,
        continuation_depth=0,
        continuation_input=None,
        continuation_type=None,
        continuation_origin="operator",
        backend="codex",
        budgets={"max_minutes": 30, "reasoning_effort": "medium"},
        stop_criteria={},
        agent_invocation={"model": "gpt-5.4"},
        auto_continuation_policy={"enabled": True},
        allowed_endpoints=[],
        paths={"chal_mount": "/workspace/chal", "run_mount": "/workspace/run"},
        local_deploy={"enabled": False, "network": None, "endpoints": []},
        status="running",
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        error_message=None,
    )
    fake_challenge = SimpleNamespace(
        id=challenge_id,
        name="Warmup",
    )
    fake_db = _FakeDB(fake_challenge)
    terminate_calls: list[str] = []
    with TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(runs_routes, "settings", SimpleNamespace(runs_dir=Path(tmpdir)))
        monkeypatch.setattr(runs_routes, "blob_store", SimpleNamespace(put_file=lambda *_args, **_kwargs: None))
        monkeypatch.setattr(
            runs_routes,
            "get_run_or_none",
            lambda _db, rid: fake_run if rid == run_id else None,
        )
        monkeypatch.setattr(
            runs_routes,
            "get_orchestrator",
            lambda: SimpleNamespace(
                terminate_run=lambda rid: terminate_calls.append(rid),
                launch_async=lambda _rid: (_ for _ in ()).throw(AssertionError("launch_async should not be called")),
            ),
        )
        monkeypatch.setattr(
            runs_routes,
            "evaluate_and_queue_auto_continuation",
            lambda **_kwargs: (_ for _ in ()).throw(AssertionError("auto continuation should not be evaluated")),
        )

        def _override_get_db():
            yield fake_db

        app.dependency_overrides[runs_routes.get_db] = _override_get_db
        client = TestClient(app)

        response = client.post(f"/runs/{run_id}/terminate")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["run"]["status"] == "blocked"
        assert payload["result"]["status"] == "blocked"
        assert terminate_calls == [str(run_id)]
        assert fake_db.commit_calls == 1
