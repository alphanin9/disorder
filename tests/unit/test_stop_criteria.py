from __future__ import annotations

from pathlib import Path

from control_plane.app.stop_criteria.engine import evaluate_stop_criteria


def test_flag_found_primary(tmp_path: Path) -> None:
    result = {
        "status": "flag_found",
        "flag": "flag{abc123}",
    }
    stop_criteria = {
        "primary": {"type": "FLAG_FOUND", "config": {"regex": r"flag\{[a-z0-9]+\}"}},
        "secondary": {"type": "DELIVERABLES_READY", "config": {"required_files": ["README.md"]}},
    }

    outcome = evaluate_stop_criteria(stop_criteria, result, tmp_path)
    assert outcome.final_status == "flag_found"
    assert outcome.stop_criterion_met == "primary"


def test_deliverables_secondary(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("ok", encoding="utf-8")
    (tmp_path / "solve.py").write_text("print('ok')", encoding="utf-8")

    result = {
        "status": "deliverable_produced",
        "flag": None,
        "deliverables": [{"path": "solve.py", "type": "solve_script", "how_to_run": "python solve.py"}],
    }
    stop_criteria = {
        "primary": {"type": "FLAG_FOUND", "config": {"regex": r"flag\{.*\}"}},
        "secondary": {"type": "DELIVERABLES_READY", "config": {"required_files": ["README.md", "solve.py"]}},
    }

    outcome = evaluate_stop_criteria(stop_criteria, result, tmp_path)
    assert outcome.final_status == "deliverable_produced"
    assert outcome.stop_criterion_met == "secondary"
