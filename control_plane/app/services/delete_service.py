from __future__ import annotations

import shutil
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.core.config import get_settings
from control_plane.app.db.models import CTFEvent, ChallengeManifest, Run
from control_plane.app.services.run_service import TERMINAL_RUN_STATUSES
from control_plane.app.store import get_blob_store


def _delete_run_storage(run_id: str) -> None:
    blob_store = get_blob_store()
    blob_store.delete_prefix(f"runs/{run_id}/")

    run_dir = get_settings().runs_dir / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)


def delete_run(db: Session, run: Run) -> None:
    if run.status not in TERMINAL_RUN_STATUSES:
        raise ValueError("Cannot delete active run. Wait for completion first.")
    if run.child_runs:
        raise ValueError("Cannot delete run that has continuation child runs.")

    run_id = str(run.id)
    db.delete(run)
    db.commit()
    _delete_run_storage(run_id)


def _challenge_run_ids(db: Session, challenge_id: UUID) -> list[str]:
    stmt = select(Run.id).where(Run.challenge_id == challenge_id)
    return [str(item) for item in db.execute(stmt).scalars().all()]


def _has_active_runs_for_challenge(db: Session, challenge_id: UUID) -> bool:
    stmt = select(Run.id).where(Run.challenge_id == challenge_id, Run.status.not_in(TERMINAL_RUN_STATUSES)).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def delete_challenge(db: Session, challenge: ChallengeManifest) -> None:
    if _has_active_runs_for_challenge(db, challenge.id):
        raise ValueError("Cannot delete challenge with active runs. Wait for completion first.")

    run_ids = _challenge_run_ids(db, challenge.id)

    challenge_artifact_prefix = f"artifacts/{challenge.platform}/{challenge.platform_challenge_id}/"
    challenge_artifact_keys: list[str] = []
    for artifact in challenge.artifacts or []:
        key = artifact.get("object_key") if isinstance(artifact, dict) else None
        if isinstance(key, str) and key.startswith(challenge_artifact_prefix):
            challenge_artifact_keys.append(key)

    db.delete(challenge)
    db.commit()

    blob_store = get_blob_store()
    for run_id in run_ids:
        _delete_run_storage(run_id)
    for artifact_key in challenge_artifact_keys:
        blob_store.delete_object(artifact_key)


def delete_ctf(db: Session, ctf: CTFEvent) -> None:
    stmt = select(ChallengeManifest).where(ChallengeManifest.ctf_id == ctf.id)
    challenges = list(db.execute(stmt).scalars().all())
    for challenge in challenges:
        delete_challenge(db, challenge)

    db.delete(ctf)
    db.commit()
