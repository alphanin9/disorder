from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from control_plane.app.db.session import get_db
from control_plane.app.schemas.auth import (
    CodexAuthFileRead,
    CodexAuthSetActiveTagRequest,
    CodexAuthStatusResponse,
    CodexDeviceAuthPollResponse,
    CodexDeviceAuthStartRequest,
    CodexDeviceAuthStartResponse,
)
from control_plane.app.services.auth_service import (
    check_codex_auth_health,
    delete_codex_auth_file,
    delete_codex_auth_tag,
    get_codex_auth_status,
    poll_codex_device_auth,
    set_codex_active_tag,
    start_codex_device_auth,
    upload_codex_auth_file,
)

router = APIRouter(prefix="/auth/codex", tags=["auth"])


@router.get("/status", response_model=CodexAuthStatusResponse)
def get_status(db: Session = Depends(get_db)) -> CodexAuthStatusResponse:
    return get_codex_auth_status(db)


@router.post("/health-check", response_model=CodexAuthStatusResponse)
def run_health_check(db: Session = Depends(get_db)) -> CodexAuthStatusResponse:
    try:
        return check_codex_auth_health(db, force=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/device/start", response_model=CodexDeviceAuthStartResponse)
def start_device_auth(request: CodexDeviceAuthStartRequest, db: Session = Depends(get_db)) -> CodexDeviceAuthStartResponse:
    try:
        return start_codex_device_auth(db, tag=request.tag)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/device/{flow_id}/poll", response_model=CodexDeviceAuthPollResponse)
def poll_device_auth(flow_id: str, db: Session = Depends(get_db)) -> CodexDeviceAuthPollResponse:
    try:
        return poll_codex_device_auth(db, flow_id=flow_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/files", response_model=CodexAuthFileRead)
async def upload_file(
    file: UploadFile = File(...),
    tag: str = Form("default"),
    db: Session = Depends(get_db),
) -> CodexAuthFileRead:
    raw = await file.read()
    try:
        return upload_codex_auth_file(db, tag=tag, file_name=file.filename, raw_bytes=raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/active-tag", response_model=CodexAuthStatusResponse)
def set_active_tag(request: CodexAuthSetActiveTagRequest, db: Session = Depends(get_db)) -> CodexAuthStatusResponse:
    try:
        return set_codex_active_tag(db, request.tag)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/files/{file_id}", response_model=CodexAuthStatusResponse)
def remove_file(file_id: str, db: Session = Depends(get_db)) -> CodexAuthStatusResponse:
    try:
        return delete_codex_auth_file(db, file_id=file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/tags/{tag}", response_model=CodexAuthStatusResponse)
def remove_tag(tag: str, db: Session = Depends(get_db)) -> CodexAuthStatusResponse:
    try:
        return delete_codex_auth_tag(db, tag=tag)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
