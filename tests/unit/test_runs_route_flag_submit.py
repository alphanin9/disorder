from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.app.api.routes import runs as runs_routes


class _FakeDB:
    def __init__(self, challenge) -> None:
        self._challenge = challenge
        self.commit_calls = 0
        self.rollback_calls = 0

    def get(self, model, _key):
        if model is runs_routes.ChallengeManifest:
            return self._challenge
        return None

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


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
