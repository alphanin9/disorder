from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from control_plane.app.db.session import get_db
from control_plane.app.schemas.auth import (
    ClaudeAuthSetActiveTagRequest,
    ClaudeAuthStatusResponse,
    ClaudeOAuthCompleteRequest,
    ClaudeOAuthCompleteResponse,
    ClaudeOAuthStartRequest,
    ClaudeOAuthStartResponse,
)
from control_plane.app.services.claude_auth_service import (
    check_claude_auth_health,
    complete_claude_oauth,
    delete_claude_auth_file,
    delete_claude_auth_tag,
    get_claude_auth_status,
    set_claude_active_tag,
    start_claude_oauth,
)

router = APIRouter(prefix="/auth/claude", tags=["auth"])


@router.get("/status", response_model=ClaudeAuthStatusResponse)
def get_status(db: Session = Depends(get_db)) -> ClaudeAuthStatusResponse:
    return get_claude_auth_status(db)


@router.post("/health-check", response_model=ClaudeAuthStatusResponse)
def run_health_check(db: Session = Depends(get_db)) -> ClaudeAuthStatusResponse:
    try:
        return check_claude_auth_health(db, force=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/oauth/start", response_model=ClaudeOAuthStartResponse)
def start_oauth(
    request: ClaudeOAuthStartRequest, db: Session = Depends(get_db)
) -> ClaudeOAuthStartResponse:
    try:
        return start_claude_oauth(db, tag=request.tag)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/oauth/{flow_id}/complete", response_model=ClaudeOAuthCompleteResponse)
def complete_oauth(
    flow_id: str,
    request: ClaudeOAuthCompleteRequest,
    db: Session = Depends(get_db),
) -> ClaudeOAuthCompleteResponse:
    try:
        return complete_claude_oauth(db, flow_id=flow_id, code=request.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/active-tag", response_model=ClaudeAuthStatusResponse)
def set_active_tag(
    request: ClaudeAuthSetActiveTagRequest, db: Session = Depends(get_db)
) -> ClaudeAuthStatusResponse:
    try:
        return set_claude_active_tag(db, request.tag)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/files/{file_id}", response_model=ClaudeAuthStatusResponse)
def remove_file(file_id: str, db: Session = Depends(get_db)) -> ClaudeAuthStatusResponse:
    try:
        return delete_claude_auth_file(db, file_id=file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/tags/{tag}", response_model=ClaudeAuthStatusResponse)
def remove_tag(tag: str, db: Session = Depends(get_db)) -> ClaudeAuthStatusResponse:
    try:
        return delete_claude_auth_tag(db, tag=tag)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
