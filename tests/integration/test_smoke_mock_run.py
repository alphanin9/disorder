from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from control_plane.app.db.models import ChallengeManifest


@pytest.mark.integration
def test_smoke_mock_run() -> None:
    if os.getenv("RUN_SMOKE") != "1":
        pytest.skip("Set RUN_SMOKE=1 to run Docker-backed smoke test")

    api_url = os.getenv("CONTROL_PLANE_URL", "http://localhost:8000")
    db_url = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://ctf:ctf@localhost:5432/ctf_harness")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    challenge_id = None
    with Session() as db:
        challenge = ChallengeManifest(
            platform="ctfd",
            platform_challenge_id=f"smoke-{uuid.uuid4()}",
            name="Smoke Challenge",
            category="misc",
            points=10,
            description_md="Smoke challenge description",
            description_raw="Smoke challenge description",
            artifacts=[],
            remote_endpoints=[],
            local_deploy_hints={"compose_present": False, "notes": None},
            flag_regex=r"flag\\{.*?\\}",
            synced_at=datetime.now(timezone.utc),
        )
        db.add(challenge)
        db.commit()
        db.refresh(challenge)
        challenge_id = str(challenge.id)

    assert challenge_id is not None

    with httpx.Client(timeout=30.0) as client:
        start = client.post(
            f"{api_url}/runs",
            json={"challenge_id": challenge_id, "backend": "mock", "local_deploy_enabled": False},
        )
        start.raise_for_status()
        run = start.json()
        run_id = run["id"]

        deadline = time.time() + 180
        final_status = None
        while time.time() < deadline:
            status_resp = client.get(f"{api_url}/runs/{run_id}")
            status_resp.raise_for_status()
            payload = status_resp.json()
            final_status = payload["run"]["status"]
            if final_status in {"flag_found", "deliverable_produced", "blocked", "timeout"}:
                break
            time.sleep(1)

        assert final_status in {"flag_found", "deliverable_produced", "blocked", "timeout"}

        result_resp = client.get(f"{api_url}/runs/{run_id}/result")
        result_resp.raise_for_status()
        result_payload = result_resp.json()
        assert result_payload["challenge_name"] == "Smoke Challenge"
        assert result_payload["status"] in {"flag_found", "deliverable_produced", "blocked"}
