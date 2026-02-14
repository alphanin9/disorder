from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from control_plane.app.db.session import get_db
from control_plane.app.schemas.challenge import (
    ChallengeCreateRequest,
    ChallengeListResponse,
    ChallengeManifestRead,
    ChallengeUpdateRequest,
)
from control_plane.app.services.challenge_service import (
    create_challenge,
    get_challenge_or_none,
    list_challenges as list_challenges_service,
    update_challenge,
)

router = APIRouter(prefix="/challenges", tags=["challenges"])


def _to_read_model(row) -> ChallengeManifestRead:
    payload = ChallengeManifestRead.model_validate(row, from_attributes=True).model_dump()
    payload["ctf_name"] = row.ctf.name if getattr(row, "ctf", None) else None
    return ChallengeManifestRead(**payload)


@router.get("", response_model=ChallengeListResponse)
def list_challenges(db: Session = Depends(get_db)) -> ChallengeListResponse:
    rows = list_challenges_service(db)
    return ChallengeListResponse(items=[_to_read_model(row) for row in rows])


@router.get("/{challenge_id}", response_model=ChallengeManifestRead)
def get_challenge(challenge_id: UUID, db: Session = Depends(get_db)) -> ChallengeManifestRead:
    row = get_challenge_or_none(db, str(challenge_id))
    if row is None:
        raise HTTPException(status_code=404, detail="challenge not found")
    return _to_read_model(row)


@router.post("", response_model=ChallengeManifestRead)
def create_challenge_route(request: ChallengeCreateRequest, db: Session = Depends(get_db)) -> ChallengeManifestRead:
    try:
        row = create_challenge(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_read_model(row)


@router.patch("/{challenge_id}", response_model=ChallengeManifestRead)
def update_challenge_route(challenge_id: UUID, request: ChallengeUpdateRequest, db: Session = Depends(get_db)) -> ChallengeManifestRead:
    row = get_challenge_or_none(db, str(challenge_id))
    if row is None:
        raise HTTPException(status_code=404, detail="challenge not found")
    try:
        updated = update_challenge(db, row, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_read_model(updated)
