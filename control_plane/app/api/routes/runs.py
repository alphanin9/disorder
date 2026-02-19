from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from control_plane.app.core.config import get_settings
from control_plane.app.db.models import ChallengeManifest, RunResult
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
from control_plane.app.services.delete_service import delete_run
from control_plane.app.services.run_service import create_run, get_run_or_none, list_runs
from control_plane.app.store import get_blob_store
from control_plane.app.store.minio import run_result_object_keys

router = APIRouter(prefix="/runs", tags=["runs"])
settings = get_settings()
blob_store = get_blob_store()


@lru_cache
def get_orchestrator() -> DockerRunner:
    return DockerRunner()


def _write_terminated_result_if_missing(run_id: UUID, challenge: ChallengeManifest, reason: str) -> tuple[Path, Path]:
    run_dir = settings.runs_dir / str(run_id)
    run_mount_dir = run_dir / "run"
    log_dir = run_dir / "logs"
    run_mount_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    result_path = run_mount_dir / "result.json"
    if not result_path.exists():
        payload = {
            "challenge_id": str(challenge.id),
            "challenge_name": challenge.name,
            "status": "blocked",
            "stop_criterion_met": "none",
            "flag_verification": {"method": "none", "verified": False, "details": reason},
            "deliverables": [],
            "repro_steps": [],
            "key_findings": [],
            "evidence": [],
            "notes": reason,
        }
        result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    readme_path = run_mount_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text("# Run Terminated\n\nThis run was force-terminated by operator.\n", encoding="utf-8")

    log_path = log_dir / "sandbox.log"
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")
    return result_path, log_path


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


@router.get("/{run_id}/logs/stream")
async def stream_run_logs(run_id: UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    run = get_run_or_none(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    async def event_stream():
        offset = 0
        while True:
            log_path = settings.runs_dir / str(run_id) / "logs" / "sandbox.log"
            logs_text = ""
            next_offset = offset
            file_size = 0
            if log_path.exists():
                file_size = log_path.stat().st_size
                if offset < file_size:
                    with log_path.open("rb") as handle:
                        handle.seek(offset)
                        chunk = handle.read(65536)
                    next_offset = offset + len(chunk)
                    logs_text = chunk.decode("utf-8", errors="replace")

            db.expire_all()
            current = get_run_or_none(db, run_id)
            is_active = bool(current and current.status in {"queued", "running"})
            eof = not is_active and next_offset >= file_size

            payload = {
                "run_id": str(run_id),
                "offset": offset,
                "next_offset": next_offset,
                "eof": eof,
                "logs": logs_text,
            }
            if logs_text or eof:
                yield f"data: {json.dumps(payload)}\n\n"
            else:
                yield ": keepalive\n\n"

            offset = next_offset
            if eof:
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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


@router.delete("/{run_id}", status_code=204)
def delete_run_route(run_id: UUID, db: Session = Depends(get_db)) -> Response:
    run = get_run_or_none(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    try:
        delete_run(db, run)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/{run_id}/terminate", response_model=RunStatusResponse)
def terminate_run_route(run_id: UUID, db: Session = Depends(get_db)) -> RunStatusResponse:
    run = get_run_or_none(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    get_orchestrator().terminate_run(str(run_id))

    if run.status in {"queued", "running"}:
        challenge = db.get(ChallengeManifest, run.challenge_id)
        if challenge is None:
            raise HTTPException(status_code=404, detail="challenge not found")

        reason = "Run force-terminated by operator"
        run.status = "blocked"
        run.error_message = reason
        run.finished_at = datetime.now(timezone.utc)

        result_path, log_path = _write_terminated_result_if_missing(run.id, challenge, reason)
        result_key, logs_key = run_result_object_keys(str(run.id))
        blob_store.put_file(result_key, result_path)
        blob_store.put_file(logs_key, log_path)

        result_row = db.get(RunResult, run.id)
        if result_row is None:
            result_row = RunResult(
                run_id=run.id,
                status="blocked",
                result_json_object_key=result_key,
                logs_object_key=logs_key,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
            db.add(result_row)
        else:
            result_row.status = "blocked"
            result_row.result_json_object_key = result_key
            result_row.logs_object_key = logs_key
            result_row.finished_at = run.finished_at

        db.commit()
        db.refresh(run)

    result = db.get(RunResult, run_id)
    result_schema = RunResultRead.model_validate(result, from_attributes=True) if result else None
    return RunStatusResponse(run=RunRead.model_validate(run, from_attributes=True), result=result_schema)
