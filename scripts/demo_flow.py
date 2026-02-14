from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from control_plane.app.db.models import ChallengeManifest

FINAL_STATUSES = {"flag_found", "deliverable_produced", "blocked", "timeout"}


def _seed_demo_challenge(database_url: str) -> str:
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        challenge = ChallengeManifest(
            platform="ctfd",
            platform_challenge_id=f"demo-{uuid.uuid4()}",
            name="Demo Challenge",
            category="misc",
            points=50,
            description_md="Demo challenge seeded by `make demo`.",
            description_raw="Demo challenge seeded by `make demo`.",
            artifacts=[],
            remote_endpoints=[],
            local_deploy_hints={"compose_present": False, "notes": None},
            flag_regex=r"flag\\{.*?\\}",
            synced_at=datetime.now(timezone.utc),
        )
        db.add(challenge)
        db.commit()
        db.refresh(challenge)
        return str(challenge.id)


def _wait_for_completion(client: httpx.Client, api_url: str, run_id: str, timeout_seconds: int) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        resp = client.get(f"{api_url}/runs/{run_id}")
        resp.raise_for_status()
        payload = resp.json()
        status = payload["run"]["status"]
        if status in FINAL_STATUSES:
            return payload
        time.sleep(1)
    raise TimeoutError(f"Run {run_id} did not complete within {timeout_seconds}s")


def main() -> int:
    api_url = os.getenv("DEMO_API_URL", "http://localhost:8000").rstrip("/")
    database_url = os.getenv("DEMO_DATABASE_URL", "postgresql+psycopg://ctf:ctf@localhost:5432/ctf_harness")
    backend = os.getenv("DEMO_BACKEND", "mock")
    timeout_seconds = int(os.getenv("DEMO_TIMEOUT_SECONDS", "180"))

    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{api_url}/healthz")
        health.raise_for_status()

    challenge_id = _seed_demo_challenge(database_url)
    print(f"Seeded demo challenge: {challenge_id}")

    with httpx.Client(timeout=30.0) as client:
        start = client.post(
            f"{api_url}/runs",
            json={
                "challenge_id": challenge_id,
                "backend": backend,
                "local_deploy_enabled": False,
            },
        )
        start.raise_for_status()
        run = start.json()
        run_id = run["id"]
        print(f"Started run: {run_id} backend={backend}")

        run_state = _wait_for_completion(client=client, api_url=api_url, run_id=run_id, timeout_seconds=timeout_seconds)
        print(f"Run finished with status={run_state['run']['status']}")

        result = client.get(f"{api_url}/runs/{run_id}/result")
        result.raise_for_status()
        print(json.dumps(result.json(), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
