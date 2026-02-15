from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.db.models import ChallengeManifest, Run
from control_plane.app.schemas.run import RunCreateRequest


def build_default_stop_criteria(challenge: ChallengeManifest) -> dict:
    regex = challenge.flag_regex or (challenge.ctf.default_flag_regex if challenge.ctf else None) or r"flag\{.*?\}"
    return {
        "primary": {"type": "FLAG_FOUND", "config": {"regex": regex}},
        "secondary": {
            "type": "DELIVERABLES_READY",
            "config": {"required_files": ["README.md"]},
        },
    }


def merge_stop_criteria(defaults: dict, overrides: dict | None) -> dict:
    if not overrides:
        return defaults
    merged = {**defaults}
    for key in ("primary", "secondary"):
        if key in overrides:
            merged[key] = {
                "type": overrides[key].get("type", defaults.get(key, {}).get("type")),
                "config": {
                    **defaults.get(key, {}).get("config", {}),
                    **overrides[key].get("config", {}),
                },
            }
    return merged


def create_run(db: Session, request: RunCreateRequest) -> Run:
    challenge = db.get(ChallengeManifest, request.challenge_id)
    if challenge is None:
        raise ValueError("Challenge not found")

    stop_criteria = merge_stop_criteria(build_default_stop_criteria(challenge), request.stop_criteria)

    budgets = {"max_minutes": 30, "max_commands": None}
    if request.budgets is not None:
        budgets = {
            "max_minutes": int(request.budgets.max_minutes),
            "max_commands": int(request.budgets.max_commands) if request.budgets.max_commands is not None else None,
        }

    run = Run(
        challenge_id=challenge.id,
        backend=request.backend,
        budgets=budgets,
        stop_criteria=stop_criteria,
        allowed_endpoints=challenge.remote_endpoints,
        paths={"chal_mount": "/workspace/chal", "run_mount": "/workspace/run"},
        local_deploy={"enabled": request.local_deploy_enabled, "network": None, "endpoints": []},
        status="queued",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run_or_none(db: Session, run_id: UUID) -> Run | None:
    return db.get(Run, run_id)


def list_runs(
    db: Session,
    statuses: list[str] | None = None,
    challenge_id: UUID | None = None,
    limit: int = 100,
) -> list[Run]:
    statement = select(Run).order_by(Run.started_at.desc()).limit(limit)
    if statuses:
        statement = statement.where(Run.status.in_(statuses))
    if challenge_id is not None:
        statement = statement.where(Run.challenge_id == challenge_id)
    return db.execute(statement).scalars().all()
