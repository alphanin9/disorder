from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from control_plane.app.core.config import get_settings
from control_plane.app.db.models import RunResult
from control_plane.app.db.session import get_db
from control_plane.app.orchestrator.docker_runner import DockerRunner
from control_plane.app.schemas.run import (
    RunCreateRequest,
    RunListResponse,
    RunLogsResponse,
    RunRead,
    RunResultRead,
    RunStatusResponse,
)
from control_plane.app.services.run_service import create_run, get_run_or_none, list_runs
from control_plane.app.store import get_blob_store

router = APIRouter(prefix="/runs", tags=["runs"])
settings = get_settings()
blob_store = get_blob_store()


@lru_cache
def get_orchestrator() -> DockerRunner:
    return DockerRunner()


@router.post("", response_model=RunRead)
def start_run(request: RunCreateRequest, db: Session = Depends(get_db)) -> RunRead:
    try:
        run = create_run(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    get_orchestrator().launch_async(str(run.id))
    return RunRead.model_validate(run, from_attributes=True)


@router.get("", response_model=RunListResponse)
def get_runs(
    status: list[str] | None = Query(default=None),
    challenge_id: UUID | None = Query(default=None),
    active_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> RunListResponse:
    statuses = list(status or [])
    if active_only:
        statuses.extend(["queued", "running"])

    unique_statuses = sorted(set(statuses)) if statuses else None
    runs = list_runs(db, statuses=unique_statuses, challenge_id=challenge_id, limit=limit)
    return RunListResponse(items=[RunRead.model_validate(run, from_attributes=True) for run in runs])


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: UUID, db: Session = Depends(get_db)) -> RunStatusResponse:
    run = get_run_or_none(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    result = db.get(RunResult, run_id)
    result_schema = RunResultRead.model_validate(result, from_attributes=True) if result else None
    return RunStatusResponse(run=RunRead.model_validate(run, from_attributes=True), result=result_schema)


@router.get("/{run_id}/logs", response_model=RunLogsResponse)
def get_run_logs(
    run_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(65536, ge=1024, le=5_000_000),
    db: Session = Depends(get_db),
) -> RunLogsResponse:
    run = get_run_or_none(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    log_path = settings.runs_dir / str(run_id) / "logs" / "sandbox.log"
    if not log_path.exists():
        return RunLogsResponse(run_id=run_id, offset=offset, next_offset=offset, eof=True, logs="")

    file_size = log_path.stat().st_size
    if offset >= file_size:
        eof = run.status not in {"queued", "running"}
        return RunLogsResponse(run_id=run_id, offset=offset, next_offset=offset, eof=eof, logs="")

    with log_path.open("rb") as handle:
        handle.seek(offset)
        chunk = handle.read(limit)

    next_offset = offset + len(chunk)
    eof = next_offset >= file_size and run.status not in {"queued", "running"}
    return RunLogsResponse(
        run_id=run_id,
        offset=offset,
        next_offset=next_offset,
        eof=eof,
        logs=chunk.decode("utf-8", errors="replace"),
    )


@router.get("/{run_id}/result")
def get_run_result_payload(run_id: UUID, db: Session = Depends(get_db)) -> dict:
    run = get_run_or_none(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    result = db.get(RunResult, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run result not found")
    raw = blob_store.get_bytes(result.result_json_object_key)
    import json

    return json.loads(raw.decode("utf-8"))
