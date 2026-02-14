from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from control_plane.app.db.session import get_db
from control_plane.app.schemas.integration import CTFdConfigResponse, CTFdSyncRequest
from control_plane.app.services.sync_service import get_ctfd_config, sync_ctfd_challenges

router = APIRouter(prefix="/integrations/ctfd", tags=["integrations"])


@router.post("/sync")
def sync_ctfd(request: CTFdSyncRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return sync_ctfd_challenges(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/config", response_model=CTFdConfigResponse)
def get_ctfd(db: Session = Depends(get_db)) -> CTFdConfigResponse:
    config = get_ctfd_config(db)
    if not config:
        return CTFdConfigResponse(base_url="", configured=False)
    return CTFdConfigResponse(base_url=config.get("base_url", ""), configured=True)
