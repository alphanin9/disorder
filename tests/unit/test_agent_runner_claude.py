import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "agent_runner_claude_test", Path("images/ctf-agent-sandbox/agent_runner.py")
)
agent_runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_runner)


@pytest.fixture()
def sandbox_dirs(monkeypatch, tmp_path):
    run_dir = tmp_path / "run"
    chal_dir = tmp_path / "chal"
    run_dir.mkdir(parents=True, exist_ok=True)
    chal_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(agent_runner, "RUN_DIR", run_dir)
    monkeypatch.setattr(agent_runner, "CHAL_DIR", chal_dir)
    monkeypatch.setattr(agent_runner, "SPEC_PATH", run_dir / "spec.json")
    # Keep MCP detection from touching the host filesystem.
    monkeypatch.setenv("SANDBOX_GHIDRA_MCP_ENABLED", "0")
    monkeypatch.setenv("SANDBOX_IDA_ENABLED", "0")
    monkeypatch.delenv("CLAUDE_CODE_CLI_CMD", raising=False)
    return run_dir, chal_dir


def test_default_claude_command_is_headless_streaming(sandbox_dirs, monkeypatch):
    run_dir, chal_dir = sandbox_dirs
    prompt_file = run_dir / "prompt.txt"
    prompt_file.write_text("solve it", encoding="utf-8")

    command, stdin_input, source, _env = agent_runner._resolve_backend_command(
        spec={}, backend="claude_code", prompt_file=prompt_file
    )

    assert command[0] == "claude"
    assert "--print" in command
    assert command[command.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in command
    assert "--dangerously-skip-permissions" in command
    assert command[command.index("--add-dir") + 1] == str(chal_dir)
    assert source == "default-claude-command"
    assert stdin_input == "solve it"


def test_default_claude_command_includes_model_override(sandbox_dirs):
    run_dir, _ = sandbox_dirs
    prompt_file = run_dir / "prompt.txt"
    prompt_file.write_text("x", encoding="utf-8")

    command, _stdin, _source, _env = agent_runner._resolve_backend_command(
        spec={"agent_invocation": {"model": "claude-sonnet-4-6"}},
        backend="claude_code",
        prompt_file=prompt_file,
    )
    assert command[command.index("--model") + 1] == "claude-sonnet-4-6"


def test_default_claude_command_writes_mcp_config(sandbox_dirs):
    run_dir, _ = sandbox_dirs
    prompt_file = run_dir / "prompt.txt"
    prompt_file.write_text("x", encoding="utf-8")

    command, *_ = agent_runner._resolve_backend_command(
        spec={}, backend="claude_code", prompt_file=prompt_file
    )
    # flag_verify MCP is on by default, so a config file is produced and wired in.
    assert "--mcp-config" in command
    assert (run_dir / ".claude_mcp.json").exists()


def test_custom_claude_command_template(sandbox_dirs, monkeypatch):
    run_dir, _ = sandbox_dirs
    prompt_file = run_dir / "prompt.txt"
    prompt_file.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_CLI_CMD", "claude --print {prompt_file}")

    command, stdin_input, source, _env = agent_runner._resolve_backend_command(
        spec={}, backend="claude_code", prompt_file=prompt_file
    )
    assert source == "custom-claude-command"
    assert command == ["claude", "--print", str(prompt_file)]
    assert stdin_input is None


def test_claude_auth_source_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty"))
    assert agent_runner._claude_auth_source() == "env:ANTHROPIC_API_KEY"


def test_claude_auth_source_credentials_file(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    cred = config_dir / ".credentials.json"
    cred.write_text('{"claudeAiOauth": {"accessToken": "x"}}', encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    source = agent_runner._claude_auth_source()
    assert source is not None and source.startswith("filesystem:")


def test_claude_auth_source_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "nope"))
    assert agent_runner._claude_auth_source() is None


def test_claude_mcp_servers_default_has_flag_verify(monkeypatch):
    monkeypatch.setenv("SANDBOX_GHIDRA_MCP_ENABLED", "0")
    monkeypatch.setenv("SANDBOX_IDA_ENABLED", "0")
    monkeypatch.delenv("CODEX_FLAG_SUBMIT_MCP_ENABLED", raising=False)
    monkeypatch.delenv("CLAUDE_FLAG_SUBMIT_MCP_ENABLED", raising=False)
    servers = agent_runner._claude_mcp_servers()
    assert "flag_verify" in servers
    assert servers["flag_verify"]["command"]
    assert "flag_submit" not in servers


def test_write_claude_last_message_extracts_result(sandbox_dirs, monkeypatch):
    run_dir, _ = sandbox_dirs
    import json

    stream_lines = [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "thinking"}]}}),
        json.dumps({"type": "result", "subtype": "success", "result": "flag{test}"}),
    ]
    agent_runner._write_claude_last_message("\n".join(stream_lines))
    msg_path = run_dir / "claude_last_message.txt"
    assert msg_path.exists()
    assert msg_path.read_text(encoding="utf-8") == "flag{test}"


def test_write_claude_last_message_no_result_event(sandbox_dirs):
    run_dir, _ = sandbox_dirs
    import json

    stream_lines = [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {}}),
    ]
    agent_runner._write_claude_last_message("\n".join(stream_lines))
    # No result event → no file written.
    assert not (run_dir / "claude_last_message.txt").exists()


def test_write_claude_last_message_empty_result_skipped(sandbox_dirs):
    run_dir, _ = sandbox_dirs
    import json

    stream_lines = [
        json.dumps({"type": "result", "subtype": "error", "result": ""}),
        json.dumps({"type": "result", "subtype": "success", "result": "real result"}),
    ]
    # Last result event that has a non-empty result wins.
    agent_runner._write_claude_last_message("\n".join(stream_lines))
    assert (run_dir / "claude_last_message.txt").read_text(encoding="utf-8") == "real result"
