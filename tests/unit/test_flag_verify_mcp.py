from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "images" / "ctf-agent-sandbox" / "flag_verify_mcp.py"
    spec = importlib.util.spec_from_file_location("flag_verify_mcp_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load flag_verify_mcp module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_flag_matches_primary_regex() -> None:
    module = _load_module()
    spec = {
        "stop_criteria": {
            "primary": {"type": "FLAG_FOUND", "config": {"regex": r"^flag\{.+\}$"}},
            "secondary": {"type": "DELIVERABLES_READY", "config": {}},
        }
    }

    verification = module._verify_flag(spec, "flag{ok}")
    assert verification["method"] == "local_check"
    assert verification["verified"] is True


def test_verify_flag_without_regex_returns_none_method() -> None:
    module = _load_module()
    verification = module._verify_flag({"stop_criteria": {}}, "flag{maybe}")
    assert verification["method"] == "none"
    assert verification["verified"] is False
