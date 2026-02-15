from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_agent_runner_module():
    module_path = Path(__file__).resolve().parents[2] / "images" / "ctf-agent-sandbox" / "agent_runner.py"
    spec = importlib.util.spec_from_file_location("agent_runner_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load agent runner module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_result_payload_maps_non_contract_shape() -> None:
    module = _load_agent_runner_module()
    spec = {"challenge_id": "abc-123", "challenge_name": "Example"}
    raw = {
        "challenge": "Example",
        "status": "blocked_missing_artifacts",
        "flag_found": False,
        "summary": "No payload present",
        "evidence_files": ["README.md"],
    }

    normalized = module._normalize_result_payload(spec, raw)
    assert normalized["challenge_id"] == "abc-123"
    assert normalized["challenge_name"] == "Example"
    assert normalized["status"] == "blocked"
    assert normalized["flag_verification"]["method"] == "none"
    assert normalized["evidence"][0]["ref"] == "README.md"


def test_normalize_result_payload_accepts_flag_output() -> None:
    module = _load_agent_runner_module()
    spec = {"challenge_id": "abc-123", "challenge_name": "Example"}
    raw = {
        "status": "flag_found",
        "flag": "flag{demo}",
        "deliverables": [{"path": "solve.py", "type": "solve_script", "how_to_run": "python solve.py"}],
    }

    normalized = module._normalize_result_payload(spec, raw)
    assert normalized["status"] == "flag_found"
    assert normalized["flag"] == "flag{demo}"
    assert normalized["deliverables"][0]["type"] == "solve_script"


def test_codex_command_includes_flag_verify_mcp_by_default(tmp_path) -> None:
    module = _load_agent_runner_module()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("test", encoding="utf-8")

    command, stdin_input, source = module._resolve_backend_command("codex", prompt_file)
    assert source == "default-codex-command"
    assert stdin_input == "test"
    joined = " ".join(command)
    assert "mcp_servers.flag_verify.command" in joined
    assert "mcp_servers.flag_verify.args" in joined


def test_codex_command_can_disable_flag_verify_mcp(monkeypatch, tmp_path) -> None:
    module = _load_agent_runner_module()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("test", encoding="utf-8")
    monkeypatch.setenv("CODEX_FLAG_VERIFY_MCP_ENABLED", "0")

    command, _, _ = module._resolve_backend_command("codex", prompt_file)
    joined = " ".join(command)
    assert "mcp_servers.flag_verify.command" not in joined
    assert "mcp_servers.flag_verify.args" not in joined
