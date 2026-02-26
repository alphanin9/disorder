from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.core.config import Settings
from control_plane.app.db.models import ChallengeManifest, Run, RunResult
from control_plane.app.schemas.run import RunContinueRequest, RunCreateRequest

TERMINAL_RUN_STATUSES = {"flag_found", "deliverable_produced", "blocked", "timeout"}
CONTINUATION_MOUNT_PATH = "/workspace/continuation"


class RunContinuationError(ValueError):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class RunCreateError(ValueError):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def build_default_stop_criteria(challenge: ChallengeManifest) -> dict:
    regex = challenge.flag_regex or (challenge.ctf.default_flag_regex if challenge.ctf else None) or r"flag\{.*?\}"
    return {
        "primary": {"type": "FLAG_FOUND", "config": {"regex": regex}},
        "secondary": {
            "type": "DELIVERABLES_READY",
            "config": {"required_files": ["README.md"]},
        },
    }


def merge_stop_criteria(defaults: dict, overrides: dict | None) -> dict:
    if not overrides:
        return defaults
    merged = {**defaults}
    for key in ("primary", "secondary"):
        if key in overrides:
            merged[key] = {
                "type": overrides[key].get("type", defaults.get(key, {}).get("type")),
                "config": {
                    **defaults.get(key, {}).get("config", {}),
                    **overrides[key].get("config", {}),
                },
            }
    return merged


def _resolve_run_budgets(request: RunCreateRequest) -> dict:
    budgets = {"max_minutes": 30, "max_commands": None}
    if request.budgets is not None:
        budgets = {
            "max_minutes": int(request.budgets.max_minutes),
            "max_commands": int(request.budgets.max_commands) if request.budgets.max_commands is not None else None,
        }
    budgets["reasoning_effort"] = request.reasoning_effort
    return budgets


def _normalize_passthrough_mount_root(raw_root: str) -> str:
    root = (raw_root or "").strip() or "/workspace/chal/_host"
    if not root.startswith("/"):
        root = "/" + root
    return root.rstrip("/") or "/workspace/chal/_host"


def _slugify_passthrough_name(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.").lower()
    return slug[:64] if slug else ""


def _default_passthrough_name_from_host_path(host_path: str, index: int) -> str:
    normalized = host_path.replace("\\", "/").rstrip("/")
    candidate = Path(normalized).name or normalized.split("/")[-1] or f"mount-{index}"
    slug = _slugify_passthrough_name(candidate)
    return slug or f"mount-{index}"


def _clone_host_passthroughs(paths: dict | None) -> list[dict]:
    raw = (paths or {}).get("host_passthroughs")
    if not isinstance(raw, list):
        return []
    cloned: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        host_path = str(entry.get("host_path") or "").strip()
        mount_path = str(entry.get("mount_path") or "").strip()
        if not host_path or not mount_path:
            continue
        cloned.append(
            {
                "name": str(entry.get("name") or "").strip() or _default_passthrough_name_from_host_path(host_path, len(cloned) + 1),
                "host_path": host_path,
                "mount_path": mount_path,
                "mode": "ro",
            }
        )
    return cloned


def _resolve_host_passthroughs_for_run(request: RunCreateRequest, settings: Settings) -> list[dict]:
    requested = list(request.host_passthroughs or [])
    if not requested:
        return []
    if not settings.sandbox_host_passthrough_enabled:
        raise RunCreateError("Host directory passthrough is disabled", status_code=403)

    max_dirs = int(getattr(settings, "sandbox_host_passthrough_max_dirs", 4) or 4)
    if max_dirs <= 0:
        max_dirs = 1
    if len(requested) > max_dirs:
        raise RunCreateError(f"Too many host passthrough directories (max={max_dirs})", status_code=422)

    mount_root = _normalize_passthrough_mount_root(getattr(settings, "sandbox_host_passthrough_mount_root", "/workspace/chal/_host"))
    used_names: set[str] = set()
    normalized: list[dict] = []
    for index, entry in enumerate(requested, start=1):
        host_path = entry.host_path.strip()
        base_name = _slugify_passthrough_name(entry.name or "") or _default_passthrough_name_from_host_path(host_path, index)
        name = base_name
        suffix = 2
        while name in used_names:
            name = f"{base_name}-{suffix}"
            suffix += 1
        used_names.add(name)
        normalized.append(
            {
                "name": name,
                "host_path": host_path,
                "mount_path": f"{mount_root}/{name}",
                "mode": "ro",
            }
        )
    return normalized


def create_run(db: Session, request: RunCreateRequest, *, settings: Settings) -> Run:
    challenge = db.get(ChallengeManifest, request.challenge_id)
    if challenge is None:
        raise RunCreateError("Challenge not found", status_code=404)

    stop_criteria = merge_stop_criteria(build_default_stop_criteria(challenge), request.stop_criteria)
    paths = {"chal_mount": "/workspace/chal", "run_mount": "/workspace/run"}
    host_passthroughs = _resolve_host_passthroughs_for_run(request, settings)
    if host_passthroughs:
        paths["host_passthroughs"] = host_passthroughs
    run = Run(
        challenge_id=challenge.id,
        parent_run_id=None,
        continuation_depth=0,
        continuation_input=None,
        continuation_type=None,
        backend=request.backend,
        budgets=_resolve_run_budgets(request),
        stop_criteria=stop_criteria,
        allowed_endpoints=challenge.remote_endpoints,
        paths=paths,
        local_deploy={"enabled": request.local_deploy_enabled, "network": None, "endpoints": []},
        status="queued",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _resolve_continuation_budgets(parent_run: Run, time_limit_seconds: int | None) -> dict:
    budgets = dict(parent_run.budgets or {})
    if time_limit_seconds is not None:
        budgets["max_minutes"] = max(1, ceil(time_limit_seconds / 60))
    if "max_minutes" not in budgets:
        budgets["max_minutes"] = 30
    budgets.setdefault("max_commands", None)
    budgets.setdefault("reasoning_effort", "medium")
    return budgets


def _read_parent_result_bytes(parent_run: Run, parent_result: RunResult | None, settings: Settings, blob_store: Any) -> bytes:
    if parent_result is not None:
        try:
            return blob_store.get_bytes(parent_result.result_json_object_key)
        except Exception:
            pass

    local_result = settings.runs_dir / str(parent_run.id) / "run" / "result.json"
    if local_result.exists() and local_result.is_file():
        return local_result.read_bytes()

    fallback = {
        "challenge_id": str(parent_run.challenge_id),
        "challenge_name": "",
        "status": "blocked",
        "stop_criterion_met": "none",
        "flag_verification": {"method": "none", "verified": False, "details": "Parent result unavailable"},
        "deliverables": [],
        "repro_steps": [],
        "key_findings": [],
        "evidence": [],
        "notes": "Parent result unavailable",
    }
    return json.dumps(fallback, indent=2).encode("utf-8")


def _read_parent_readme(parent_run: Run, settings: Settings) -> str:
    readme_path = settings.runs_dir / str(parent_run.id) / "run" / "README.md"
    if readme_path.exists() and readme_path.is_file():
        return readme_path.read_text(encoding="utf-8")
    return "# Parent README Missing\n\nParent README.md is not available in local run storage.\n"


def create_continuation_context_bundle(
    *,
    parent_run: Run,
    parent_result: RunResult | None,
    child_run: Run,
    request: RunContinueRequest,
    settings: Settings,
    blob_store: Any,
) -> Path:
    context_dir = settings.runs_dir / str(child_run.id) / "continuation"
    context_dir.mkdir(parents=True, exist_ok=True)

    (context_dir / "parent_result.json").write_bytes(
        _read_parent_result_bytes(parent_run=parent_run, parent_result=parent_result, settings=settings, blob_store=blob_store)
    )
    (context_dir / "parent_readme.md").write_text(
        _read_parent_readme(parent_run=parent_run, settings=settings),
        encoding="utf-8",
    )

    request_payload = {
        "parent_run_id": str(parent_run.id),
        "child_run_id": str(child_run.id),
        "message": request.message,
        "type": request.type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (context_dir / "continuation_request.json").write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
    return context_dir


def create_continuation_run(
    db: Session,
    *,
    parent_run_id: UUID,
    request: RunContinueRequest,
    settings: Settings,
    blob_store: Any,
) -> Run:
    if not settings.enable_run_continuation:
        raise RunContinuationError("Run continuation is disabled", status_code=403)

    parent_run = db.get(Run, parent_run_id)
    if parent_run is None:
        raise RunContinuationError("Parent run not found", status_code=404)

    if parent_run.status not in TERMINAL_RUN_STATUSES:
        raise RunContinuationError("Parent run must be in terminal status", status_code=409)

    if parent_run.continuation_depth >= settings.max_continuation_depth:
        raise RunContinuationError(
            f"Continuation depth limit exceeded (max={settings.max_continuation_depth})",
            status_code=409,
        )

    message = request.message.strip()
    if len(message) > settings.max_continuation_message_chars:
        raise RunContinuationError(
            f"Continuation message exceeds max length ({settings.max_continuation_message_chars})",
            status_code=422,
        )

    challenge = db.get(ChallengeManifest, parent_run.challenge_id)
    if challenge is None:
        raise RunContinuationError("Challenge not found for parent run", status_code=404)

    local_deploy_enabled = bool((parent_run.local_deploy or {}).get("enabled", False))
    child_paths = {"chal_mount": "/workspace/chal", "run_mount": "/workspace/run"}
    parent_host_passthroughs = _clone_host_passthroughs(parent_run.paths or {})
    if parent_host_passthroughs:
        child_paths["host_passthroughs"] = parent_host_passthroughs
    if request.reuse_parent_artifacts:
        child_paths["continuation_mount"] = CONTINUATION_MOUNT_PATH

    child_run = Run(
        challenge_id=challenge.id,
        parent_run_id=parent_run.id,
        continuation_depth=parent_run.continuation_depth + 1,
        continuation_input=message,
        continuation_type=request.type,
        backend=parent_run.backend,
        budgets=_resolve_continuation_budgets(parent_run, request.time_limit_seconds),
        stop_criteria=merge_stop_criteria(dict(parent_run.stop_criteria or {}), request.stop_criteria_override),
        allowed_endpoints=challenge.remote_endpoints,
        paths=child_paths,
        local_deploy={"enabled": local_deploy_enabled, "network": None, "endpoints": []},
        status="queued",
        started_at=datetime.now(timezone.utc),
    )
    db.add(child_run)
    try:
        if request.reuse_parent_artifacts:
            db.flush()
            parent_result = db.get(RunResult, parent_run.id)
            create_continuation_context_bundle(
                parent_run=parent_run,
                parent_result=parent_result,
                child_run=child_run,
                request=request,
                settings=settings,
                blob_store=blob_store,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(child_run)
    return child_run


def get_run_or_none(db: Session, run_id: UUID) -> Run | None:
    return db.get(Run, run_id)


def list_runs(
    db: Session,
    statuses: list[str] | None = None,
    challenge_id: UUID | None = None,
    limit: int = 100,
) -> list[Run]:
    statement = select(Run).order_by(Run.started_at.desc()).limit(limit)
    if statuses:
        statement = statement.where(Run.status.in_(statuses))
    if challenge_id is not None:
        statement = statement.where(Run.challenge_id == challenge_id)
    return db.execute(statement).scalars().all()


def list_child_runs(db: Session, parent_run_id: UUID) -> list[Run]:
    statement = select(Run).where(Run.parent_run_id == parent_run_id).order_by(Run.started_at.desc())
    return db.execute(statement).scalars().all()
