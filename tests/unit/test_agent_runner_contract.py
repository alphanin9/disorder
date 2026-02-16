from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace


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
    assert "--json" in command
    assert 'model_reasoning_effort="medium"' in joined
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


def test_codex_command_includes_additional_mcp_overrides(tmp_path) -> None:
    module = _load_agent_runner_module()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("test", encoding="utf-8")

    extra = ["-c", 'mcp_servers.ida_pro.url="http://127.0.0.1:8745/mcp"']
    command, _, _ = module._resolve_backend_command("codex", prompt_file, additional_mcp_overrides=extra)
    joined = " ".join(command)
    assert "mcp_servers.ida_pro.url" in joined


def test_start_idalib_mcp_returns_disabled_when_ida_not_enabled(monkeypatch) -> None:
    module = _load_agent_runner_module()
    monkeypatch.delenv("SANDBOX_IDA_ENABLED", raising=False)
    monkeypatch.delenv("SANDBOX_IDA_INSTALL_PATH", raising=False)
    monkeypatch.delenv("IDADIR", raising=False)

    process, overrides = module._start_idalib_mcp_if_available()
    assert process is None
    assert overrides == []


def test_accept_ida_eula_disabled_by_env(monkeypatch) -> None:
    module = _load_agent_runner_module()
    monkeypatch.setenv("SANDBOX_IDA_ACCEPT_EULA", "0")
    monkeypatch.delenv("IDADIR", raising=False)

    accepted = module._accept_ida_eula("/opt/ida")
    assert accepted is True
    assert "IDADIR" not in os.environ


def test_accept_ida_eula_writes_expected_registry_keys(monkeypatch) -> None:
    module = _load_agent_runner_module()
    calls: list[tuple[str, int]] = []
    fake_registry = SimpleNamespace(reg_write_int=lambda key, value: calls.append((key, value)))

    monkeypatch.setenv("SANDBOX_IDA_ACCEPT_EULA", "1")
    monkeypatch.setenv("SANDBOX_IDA_EULA_VERSIONS", "90,91,92")
    monkeypatch.setitem(sys.modules, "idapro", object())
    monkeypatch.setitem(sys.modules, "ida_registry", fake_registry)

    accepted = module._accept_ida_eula("/opt/ida")
    assert accepted is True
    assert os.environ.get("IDADIR") == "/opt/ida"
    assert calls == [("EULA 90", 1), ("EULA 91", 1), ("EULA 92", 1)]


def test_seed_writable_codex_home_copies_auth_seed(monkeypatch, tmp_path) -> None:
    module = _load_agent_runner_module()
    seed_dir = tmp_path / "seed"
    codex_home = tmp_path / "codex-home"
    seed_dir.mkdir(parents=True)
    (seed_dir / "auth.json").write_text('{"token":"x"}', encoding="utf-8")

    monkeypatch.setenv("CODEX_AUTH_SEED_DIR", str(seed_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    module._seed_writable_codex_home()

    copied = codex_home / "auth.json"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == '{"token":"x"}'
