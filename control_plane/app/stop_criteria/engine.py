from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class StopCriteriaEvaluation:
    final_status: str
    stop_criterion_met: str
    details: str


def _evaluate_flag_found(result_data: dict, config: dict) -> bool:
    import re

    regex = config.get("regex")
    flag = result_data.get("flag")
    if not regex or not flag:
        return False
    return bool(re.search(regex, str(flag)))


def _evaluate_deliverables_ready(result_data: dict, config: dict, run_mount_dir: Path) -> bool:
    if result_data.get("status") == "blocked":
        return False
    if not result_data.get("deliverables"):
        return False

    required_files = config.get("required_files", [])
    for relative in required_files:
        candidate = run_mount_dir / relative
        if not candidate.exists():
            return False

    self_test = config.get("self_test")
    if self_test:
        completed = subprocess.run(
            self_test,
            shell=True,
            cwd=run_mount_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            return False

    return True


def evaluate_stop_criteria(stop_criteria: dict, result_data: dict, run_mount_dir: Path) -> StopCriteriaEvaluation:
    primary = stop_criteria.get("primary", {})
    secondary = stop_criteria.get("secondary", {})

    primary_type = primary.get("type")
    primary_config = primary.get("config", {})

    secondary_type = secondary.get("type")
    secondary_config = secondary.get("config", {})

    primary_met = False
    if primary_type == "FLAG_FOUND":
        primary_met = _evaluate_flag_found(result_data, primary_config)
    elif primary_type == "DELIVERABLES_READY":
        primary_met = _evaluate_deliverables_ready(result_data, primary_config, run_mount_dir)

    if primary_met:
        status = "flag_found" if primary_type == "FLAG_FOUND" else "deliverable_produced"
        return StopCriteriaEvaluation(final_status=status, stop_criterion_met="primary", details="Primary stop criterion matched")

    secondary_met = False
    if secondary_type == "FLAG_FOUND":
        secondary_met = _evaluate_flag_found(result_data, secondary_config)
    elif secondary_type == "DELIVERABLES_READY":
        secondary_met = _evaluate_deliverables_ready(result_data, secondary_config, run_mount_dir)

    if secondary_met:
        status = "flag_found" if secondary_type == "FLAG_FOUND" else "deliverable_produced"
        return StopCriteriaEvaluation(final_status=status, stop_criterion_met="secondary", details="Secondary stop criterion matched")

    fallback_status = result_data.get("status", "blocked")
    return StopCriteriaEvaluation(
        final_status=fallback_status if fallback_status in {"flag_found", "deliverable_produced", "blocked"} else "blocked",
        stop_criterion_met="none",
        details="No stop criterion matched",
    )
