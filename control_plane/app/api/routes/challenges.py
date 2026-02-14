from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.db.models import ChallengeManifest
from control_plane.app.db.session import get_db
from control_plane.app.schemas.challenge import ChallengeListResponse, ChallengeManifestRead

router = APIRouter(prefix="/challenges", tags=["challenges"])


@router.get("", response_model=ChallengeListResponse)
def list_challenges(db: Session = Depends(get_db)) -> ChallengeListResponse:
    rows = db.execute(select(ChallengeManifest).order_by(ChallengeManifest.synced_at.desc())).scalars().all()
    return ChallengeListResponse(items=[ChallengeManifestRead.model_validate(row) for row in rows])


@router.get("/{challenge_id}", response_model=ChallengeManifestRead)
def get_challenge(challenge_id: UUID, db: Session = Depends(get_db)) -> ChallengeManifestRead:
    row = db.get(ChallengeManifest, challenge_id)
    if row is None:
        raise HTTPException(status_code=404, detail="challenge not found")
    return ChallengeManifestRead.model_validate(row)
