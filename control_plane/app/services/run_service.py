from __future__ import annotations

import json
from datetime import datetime, timezone
from math import ceil
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.core.config import Settings
from control_plane.app.db.models import ChallengeManifest, Run, RunResult
from control_plane.app.schemas.result_contract import SandboxResult
from control_plane.app.schemas.run import (
    AgentInvocationConfig,
    AutoContinuationPolicy,
    RunContinueRequest,
    RunCreateRequest,
    validate_agent_invocation_backend,
)

TERMINAL_RUN_STATUSES = {"flag_found", "deliverable_produced", "blocked", "timeout"}
CONTINUATION_MOUNT_PATH = "/workspace/continuation"
DELIVERABLES_DIR_NAME = "deliverables"
DELIVERABLES_MANIFEST_NAME = "deliverables_manifest.json"


class RunContinuationError(ValueError):
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


def _normalize_agent_invocation(config: AgentInvocationConfig | dict | None) -> dict:
    if config is None:
        return {}
    if isinstance(config, AgentInvocationConfig):
        payload = config.model_dump(mode="json", exclude_none=True)
    else:
        payload = AgentInvocationConfig.model_validate(config).model_dump(mode="json", exclude_none=True)
    payload.setdefault("extra_args", [])
    payload.setdefault("env", {})
    return payload


def _merge_agent_invocation(parent: dict | None, override: AgentInvocationConfig | None) -> dict:
    merged = _normalize_agent_invocation(parent)
    if override is None:
        return merged

    override_payload = _normalize_agent_invocation(override)
    if "model" in override_payload:
        merged["model"] = override_payload["model"]
    if "profile" in override_payload:
        merged["profile"] = override_payload["profile"]
    if "extra_args" in override_payload:
        merged["extra_args"] = list(override_payload["extra_args"])
    if "env" in override_payload:
        merged["env"] = {**merged.get("env", {}), **override_payload["env"]}
    return merged


def _normalize_auto_continuation_policy(policy: AutoContinuationPolicy | dict | None) -> dict | None:
    if policy is None:
        return None
    if isinstance(policy, AutoContinuationPolicy):
        return policy.model_dump(mode="json")
    return AutoContinuationPolicy.model_validate(policy).model_dump(mode="json")


def _resolve_run_budgets(request: RunCreateRequest) -> dict:
    budgets = {"max_minutes": 30, "max_commands": None}
    if request.budgets is not None:
        budgets = {
            "max_minutes": int(request.budgets.max_minutes),
            "max_commands": int(request.budgets.max_commands) if request.budgets.max_commands is not None else None,
        }
    budgets["reasoning_effort"] = request.reasoning_effort
    return budgets


def create_run(db: Session, request: RunCreateRequest) -> Run:
    challenge = db.get(ChallengeManifest, request.challenge_id)
    if challenge is None:
        raise ValueError("Challenge not found")

    validate_agent_invocation_backend(request.backend, request.agent_invocation)
    stop_criteria = merge_stop_criteria(build_default_stop_criteria(challenge), request.stop_criteria)
    run = Run(
        challenge_id=challenge.id,
        parent_run_id=None,
        continuation_depth=0,
        continuation_input=None,
        continuation_type=None,
        continuation_origin="operator",
        backend=request.backend,
        budgets=_resolve_run_budgets(request),
        stop_criteria=stop_criteria,
        agent_invocation=_normalize_agent_invocation(request.agent_invocation),
        auto_continuation_policy=_normalize_auto_continuation_policy(request.auto_continuation_policy),
        allowed_endpoints=challenge.remote_endpoints,
        paths={"chal_mount": "/workspace/chal", "run_mount": "/workspace/run"},
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


def _parent_result_fallback(parent_run: Run) -> dict[str, Any]:
    return {
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


def _read_parent_result_payload(parent_run: Run, parent_result: RunResult | None, settings: Settings, blob_store: Any) -> dict[str, Any]:
    local_result = settings.runs_dir / str(parent_run.id) / "run" / "result.json"
    if local_result.exists() and local_result.is_file():
        try:
            return json.loads(local_result.read_text(encoding="utf-8"))
        except Exception:
            return _parent_result_fallback(parent_run)

    if parent_result is not None:
        try:
            return json.loads(blob_store.get_bytes(parent_result.result_json_object_key).decode("utf-8"))
        except Exception:
            pass

    return _parent_result_fallback(parent_run)


def _read_parent_readme(parent_run: Run, settings: Settings) -> str:
    readme_path = settings.runs_dir / str(parent_run.id) / "run" / "README.md"
    if readme_path.exists() and readme_path.is_file():
        return readme_path.read_text(encoding="utf-8")
    return "# Parent README Missing\n\nParent README.md is not available in local run storage.\n"


def _safe_relative_deliverable_path(raw_path: str) -> PurePosixPath | None:
    candidate = PurePosixPath(str(raw_path).replace("\\", "/"))
    if candidate.is_absolute():
        return None
    if not candidate.parts:
        return None
    if any(part in {"", ".", ".."} for part in candidate.parts):
        return None
    return candidate


def _copy_parent_deliverables_into_bundle(
    *,
    parent_run: Run,
    parent_result_payload: dict[str, Any],
    context_dir: Path,
    settings: Settings,
    blob_store: Any,
) -> dict[str, Any]:
    deliverables_root = context_dir / DELIVERABLES_DIR_NAME
    deliverables_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "parent_run_id": str(parent_run.id),
        "items": [],
    }

    try:
        validated_result = SandboxResult.model_validate(parent_result_payload)
    except Exception as exc:
        manifest["error"] = f"Unable to validate parent result payload: {exc}"
        return manifest

    total_bytes = 0
    max_items = int(getattr(settings, "max_continuation_deliverables", 16))
    max_item_bytes = int(getattr(settings, "max_continuation_deliverable_bytes", 5 * 1024 * 1024))
    max_total_bytes = int(getattr(settings, "max_continuation_total_bytes", 20 * 1024 * 1024))

    for index, deliverable in enumerate(validated_result.deliverables):
        copied_bundle_path = None
        status = "skipped"
        source = None
        error = None

        if index >= max_items:
            error = f"deliverable limit exceeded (max={max_items})"
        else:
            relative_path = _safe_relative_deliverable_path(deliverable.path)
            if relative_path is None:
                error = "deliverable path is not a safe relative file path"
            else:
                local_source = settings.runs_dir / str(parent_run.id) / "run" / Path(*relative_path.parts)
                target_path = deliverables_root / Path(*relative_path.parts)
                data: bytes | None = None

                if local_source.exists():
                    try:
                        resolved_local = local_source.resolve(strict=True)
                        parent_run_dir = (settings.runs_dir / str(parent_run.id) / "run").resolve(strict=True)
                        if parent_run_dir not in resolved_local.parents and resolved_local != parent_run_dir:
                            error = "deliverable path escapes parent run directory"
                        elif local_source.is_symlink():
                            error = "deliverable symlinks are not supported"
                        elif not resolved_local.is_file():
                            error = "deliverable is not a regular file"
                        else:
                            data = resolved_local.read_bytes()
                            source = "local"
                    except Exception as exc:
                        error = str(exc)

                if data is None and error is None:
                    object_key = f"runs/{parent_run.id}/deliverables/{relative_path.as_posix()}"
                    try:
                        data = blob_store.get_bytes(object_key)
                        source = "blob"
                    except Exception:
                        error = f"deliverable unavailable in local run storage or blob store ({relative_path.as_posix()})"

                if data is not None:
                    size = len(data)
                    if size > max_item_bytes:
                        error = f"deliverable exceeds per-file size cap ({max_item_bytes} bytes)"
                    elif total_bytes + size > max_total_bytes:
                        error = f"continuation bundle would exceed total size cap ({max_total_bytes} bytes)"
                    else:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        target_path.write_bytes(data)
                        copied_bundle_path = f"{DELIVERABLES_DIR_NAME}/{relative_path.as_posix()}"
                        total_bytes += size
                        status = "copied"

        manifest["items"].append(
            {
                "original_path": deliverable.path,
                "type": deliverable.type,
                "how_to_run": deliverable.how_to_run,
                "bundle_path": copied_bundle_path,
                "source": source,
                "status": status,
                "error": error,
            }
        )

    manifest["copied_count"] = sum(1 for item in manifest["items"] if item["status"] == "copied")
    manifest["total_bytes"] = total_bytes
    return manifest


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
    parent_result_payload = _read_parent_result_payload(
        parent_run=parent_run,
        parent_result=parent_result,
        settings=settings,
        blob_store=blob_store,
    )

    (context_dir / "parent_result.json").write_text(
        json.dumps(parent_result_payload, indent=2),
        encoding="utf-8",
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
        "origin": child_run.continuation_origin,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (context_dir / "continuation_request.json").write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
    deliverables_manifest = _copy_parent_deliverables_into_bundle(
        parent_run=parent_run,
        parent_result_payload=parent_result_payload,
        context_dir=context_dir,
        settings=settings,
        blob_store=blob_store,
    )
    (context_dir / DELIVERABLES_MANIFEST_NAME).write_text(
        json.dumps(deliverables_manifest, indent=2),
        encoding="utf-8",
    )
    return context_dir


def create_continuation_run(
    db: Session,
    *,
    parent_run_id: UUID,
    request: RunContinueRequest,
    settings: Settings,
    blob_store: Any,
    continuation_origin: str = "operator",
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

    try:
        merged_agent_invocation = _merge_agent_invocation(parent_run.agent_invocation, request.agent_invocation_override)
        validate_agent_invocation_backend(parent_run.backend, AgentInvocationConfig.model_validate(merged_agent_invocation))
    except ValueError as exc:
        raise RunContinuationError(str(exc), status_code=422) from exc

    if "auto_continuation_policy_override" in request.model_fields_set:
        effective_policy = _normalize_auto_continuation_policy(request.auto_continuation_policy_override)
    else:
        effective_policy = _normalize_auto_continuation_policy(parent_run.auto_continuation_policy)

    local_deploy_enabled = bool((parent_run.local_deploy or {}).get("enabled", False))
    child_paths = {"chal_mount": "/workspace/chal", "run_mount": "/workspace/run"}
    if request.reuse_parent_artifacts:
        child_paths["continuation_mount"] = CONTINUATION_MOUNT_PATH

    child_run = Run(
        challenge_id=challenge.id,
        parent_run_id=parent_run.id,
        continuation_depth=parent_run.continuation_depth + 1,
        continuation_input=message,
        continuation_type=request.type,
        continuation_origin=continuation_origin,
        backend=parent_run.backend,
        budgets=_resolve_continuation_budgets(parent_run, request.time_limit_seconds),
        stop_criteria=merge_stop_criteria(dict(parent_run.stop_criteria or {}), request.stop_criteria_override),
        agent_invocation=merged_agent_invocation,
        auto_continuation_policy=effective_policy,
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
