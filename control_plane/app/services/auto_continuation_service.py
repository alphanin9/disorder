from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.core.config import Settings
from control_plane.app.db.models import Run, RunResult
from control_plane.app.schemas.run import AutoContinuationPolicy, RunContinueRequest
from control_plane.app.services.run_service import TERMINAL_RUN_STATUSES, create_continuation_run


def _record_auto_continuation_decision(db: Session, result: RunResult, payload: dict[str, Any]) -> None:
    existing = dict(result.finalization_metadata or {})
    existing["auto_continuation"] = payload
    result.finalization_metadata = existing
    db.commit()


def _format_auto_continuation_message(policy: AutoContinuationPolicy, run: Run, result: RunResult) -> str:
    metadata = result.finalization_metadata or {}
    template_values = {
        "parent_run_id": str(run.id),
        "parent_status": result.status,
        "failure_reason_code": str(metadata.get("failure_reason_code") or "none"),
        "target_final_status": policy.target.final_status,
        "continuation_depth": run.continuation_depth + 1,
    }
    try:
        return policy.message_template.format(**template_values).strip()
    except Exception:
        return (
            f"Previous run {run.id} ended {result.status} with "
            f"{template_values['failure_reason_code']}. Continue toward {policy.target.final_status}."
        )


def evaluate_and_queue_auto_continuation(
    db: Session,
    run: Run,
    result: RunResult,
    settings: Settings,
    blob_store: Any,
) -> Run | None:
    decision: dict[str, Any] = {
        "evaluated": True,
        "queued": False,
        "parent_run_id": str(run.id),
        "result_status": result.status,
    }

    policy_payload = run.auto_continuation_policy
    if not policy_payload:
        decision["reason"] = "policy_missing"
        _record_auto_continuation_decision(db, result, decision)
        return None

    policy = AutoContinuationPolicy.model_validate(policy_payload)
    decision["effective_policy"] = policy.model_dump(mode="json")

    if run.status not in TERMINAL_RUN_STATUSES:
        decision["reason"] = "run_not_terminal"
        _record_auto_continuation_decision(db, result, decision)
        return None

    if result.status not in TERMINAL_RUN_STATUSES:
        decision["reason"] = "result_not_terminal"
        _record_auto_continuation_decision(db, result, decision)
        return None

    if not policy.enabled:
        decision["reason"] = "policy_disabled"
        _record_auto_continuation_decision(db, result, decision)
        return None

    max_depth = min(int(policy.max_depth), int(settings.max_continuation_depth))
    decision["effective_max_depth"] = max_depth
    if run.continuation_depth >= max_depth:
        decision["reason"] = "max_depth_reached"
        _record_auto_continuation_decision(db, result, decision)
        return None

    if result.status == policy.target.final_status:
        decision["reason"] = "target_already_met"
        _record_auto_continuation_decision(db, result, decision)
        return None

    if result.status not in policy.when.statuses:
        decision["reason"] = "status_not_selected"
        _record_auto_continuation_decision(db, result, decision)
        return None

    metadata = dict(result.finalization_metadata or {})
    if policy.when.require_contract_match and not bool(metadata.get("contract_valid", False)):
        decision["reason"] = "contract_not_valid"
        _record_auto_continuation_decision(db, result, decision)
        return None

    failure_reason_code = str(metadata.get("failure_reason_code") or "none")
    decision["failure_reason_code"] = failure_reason_code
    if policy.on_blocked_reasons and failure_reason_code not in set(policy.on_blocked_reasons):
        decision["reason"] = "reason_code_not_selected"
        _record_auto_continuation_decision(db, result, decision)
        return None

    existing_child = db.execute(select(Run.id).where(Run.parent_run_id == run.id).limit(1)).scalar_one_or_none()
    if existing_child is not None:
        decision["reason"] = "child_already_exists"
        decision["existing_child_run_id"] = str(existing_child)
        _record_auto_continuation_decision(db, result, decision)
        return None

    child_request = RunContinueRequest.model_validate(
        {
            "message": _format_auto_continuation_message(policy, run, result),
            "type": policy.continuation_type,
            "reuse_parent_artifacts": True,
        }
    )
    child_run = create_continuation_run(
        db,
        parent_run_id=run.id,
        request=child_request,
        settings=settings,
        blob_store=blob_store,
        continuation_origin="auto",
        inherit_parent_agent_invocation=policy.inherit_agent_invocation,
    )
    db.refresh(result)
    decision["queued"] = True
    decision["reason"] = "queued"
    decision["child_run_id"] = str(child_run.id)
    existing = dict(result.finalization_metadata or {})
    existing["auto_continuation"] = decision
    result.finalization_metadata = existing
    db.commit()
    db.refresh(child_run)
    return child_run
