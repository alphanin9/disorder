from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from control_plane.app.db.session import get_db
from control_plane.app.schemas.challenge import (
    ChallengeArtifactRead,
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
from control_plane.app.services.delete_service import delete_challenge
from control_plane.app.store import get_blob_store
from control_plane.app.store.minio import artifact_object_key, sha256_bytes

router = APIRouter(prefix="/challenges", tags=["challenges"])


def _to_read_model(row) -> ChallengeManifestRead:
    payload = ChallengeManifestRead.model_validate(row, from_attributes=True).model_dump()
    payload["ctf_name"] = row.ctf.name if getattr(row, "ctf", None) else None
    return ChallengeManifestRead(**payload)


def _sanitize_artifact_name(raw_name: str | None) -> str:
    name = (raw_name or "artifact.bin").replace("\\", "/")
    safe_name = Path(name).name.strip()
    return safe_name or "artifact.bin"


@router.get("", response_model=ChallengeListResponse)
def list_challenges(
    ctf_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ChallengeListResponse:
    rows = list_challenges_service(db, ctf_id=str(ctf_id) if ctf_id else None)
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


@router.delete("/{challenge_id}", status_code=204)
def delete_challenge_route(challenge_id: UUID, db: Session = Depends(get_db)) -> Response:
    row = get_challenge_or_none(db, str(challenge_id))
    if row is None:
        raise HTTPException(status_code=404, detail="challenge not found")
    try:
        delete_challenge(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/artifacts/upload", response_model=ChallengeArtifactRead)
async def upload_artifact_route(file: UploadFile = File(...)) -> ChallengeArtifactRead:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty artifact upload is not allowed")

    safe_name = _sanitize_artifact_name(file.filename)
    sha_hex = sha256_bytes(raw)
    object_key = artifact_object_key(
        platform="manual",
        challenge_id="uploads",
        file_name=safe_name,
        sha256_hex=sha_hex,
    )

    blob_store = get_blob_store()
    if not blob_store.object_exists(object_key):
        blob_store.put_bytes(
            object_key=object_key,
            data=raw,
            content_type=file.content_type or "application/octet-stream",
        )

    return ChallengeArtifactRead(
        name=safe_name,
        sha256=sha_hex,
        size_bytes=len(raw),
        object_key=object_key,
    )
