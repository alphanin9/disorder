from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from control_plane.app.db.session import get_db
from control_plane.app.schemas.ctf import CTFCreateRequest, CTFListResponse, CTFRead, CTFUpdateRequest
from control_plane.app.schemas.integration import CTFdPerCtfConfigResponse
from control_plane.app.services.challenge_service import create_ctf, get_ctf_or_none, list_ctfs, update_ctf
from control_plane.app.services.ctfd_config_service import clear_ctfd_api_token, clear_ctfd_session_cookie, get_ctfd_config_response
from control_plane.app.services.delete_service import delete_ctf

router = APIRouter(prefix="/ctfs", tags=["ctfs"])


@router.get("", response_model=CTFListResponse)
def list_ctfs_route(db: Session = Depends(get_db)) -> CTFListResponse:
    rows = list_ctfs(db)
    return CTFListResponse(items=[CTFRead.model_validate(row, from_attributes=True) for row in rows])


@router.post("", response_model=CTFRead)
def create_ctf_route(request: CTFCreateRequest, db: Session = Depends(get_db)) -> CTFRead:
    try:
        row = create_ctf(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CTFRead.model_validate(row, from_attributes=True)


@router.get("/{ctf_id}", response_model=CTFRead)
def get_ctf_route(ctf_id: UUID, db: Session = Depends(get_db)) -> CTFRead:
    row = get_ctf_or_none(db, str(ctf_id))
    if row is None:
        raise HTTPException(status_code=404, detail="ctf not found")
    return CTFRead.model_validate(row, from_attributes=True)


@router.get("/{ctf_id}/integrations/ctfd/config", response_model=CTFdPerCtfConfigResponse)
def get_ctf_ctfd_config_route(ctf_id: UUID, db: Session = Depends(get_db)) -> CTFdPerCtfConfigResponse:
    row = get_ctf_or_none(db, str(ctf_id))
    if row is None:
        raise HTTPException(status_code=404, detail="ctf not found")
    return CTFdPerCtfConfigResponse.model_validate(get_ctfd_config_response(db, ctf_id))


@router.delete("/{ctf_id}/integrations/ctfd/session-cookie", response_model=CTFdPerCtfConfigResponse)
def clear_ctf_ctfd_session_cookie_route(ctf_id: UUID, db: Session = Depends(get_db)) -> CTFdPerCtfConfigResponse:
    row = get_ctf_or_none(db, str(ctf_id))
    if row is None:
        raise HTTPException(status_code=404, detail="ctf not found")
    return CTFdPerCtfConfigResponse.model_validate(clear_ctfd_session_cookie(db, ctf_id=ctf_id))


@router.delete("/{ctf_id}/integrations/ctfd/api-token", response_model=CTFdPerCtfConfigResponse)
def clear_ctf_ctfd_api_token_route(ctf_id: UUID, db: Session = Depends(get_db)) -> CTFdPerCtfConfigResponse:
    row = get_ctf_or_none(db, str(ctf_id))
    if row is None:
        raise HTTPException(status_code=404, detail="ctf not found")
    return CTFdPerCtfConfigResponse.model_validate(clear_ctfd_api_token(db, ctf_id=ctf_id))


@router.patch("/{ctf_id}", response_model=CTFRead)
def update_ctf_route(ctf_id: UUID, request: CTFUpdateRequest, db: Session = Depends(get_db)) -> CTFRead:
    row = get_ctf_or_none(db, str(ctf_id))
    if row is None:
        raise HTTPException(status_code=404, detail="ctf not found")
    try:
        updated = update_ctf(db, row, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CTFRead.model_validate(updated, from_attributes=True)


@router.delete("/{ctf_id}", status_code=204)
def delete_ctf_route(ctf_id: UUID, db: Session = Depends(get_db)) -> Response:
    row = get_ctf_or_none(db, str(ctf_id))
    if row is None:
        raise HTTPException(status_code=404, detail="ctf not found")
    try:
        delete_ctf(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)
