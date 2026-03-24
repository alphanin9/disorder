from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_agent_runner_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "images"
        / "ctf-agent-sandbox"
        / "agent_runner.py"
    )
    spec = importlib.util.spec_from_file_location("agent_runner_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load agent runner module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configure_runner_paths(module, tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    chal_dir = tmp_path / "chal"
    run_dir.mkdir(parents=True)
    chal_dir.mkdir(parents=True)
    prompt_template = tmp_path / "agent_prompt.txt"
    prompt_template.write_text(
        "Challenge: {challenge_name}\nSame-run retry context:\n{runner_loop_context}\nContinuation context:\n{continuation_context}\n",
        encoding="utf-8",
    )
    tooling_guide = tmp_path / "ctf_tooling_guide.md"
    tooling_guide.write_text("guide", encoding="utf-8")

    module.RUN_DIR = run_dir
    module.CHAL_DIR = chal_dir
    module.SPEC_PATH = run_dir / "spec.json"
    module.PROMPT_TEMPLATE_PATH = prompt_template
    module.TOOLING_GUIDE_PATH = tooling_guide
    module.ATTEMPTS_DIR = run_dir / "attempts"
    module.RUNNER_LOOP_STATE_PATH = run_dir / "runner_loop_state.json"


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
    assert normalized["failure_reason_code"] == "none"
    assert normalized["flag_verification"]["method"] == "none"
    assert normalized["evidence"][0]["ref"] == "README.md"


def test_normalize_result_payload_accepts_flag_output() -> None:
    module = _load_agent_runner_module()
    spec = {"challenge_id": "abc-123", "challenge_name": "Example"}
    raw = {
        "status": "flag_found",
        "flag": "flag{demo}",
        "deliverables": [
            {
                "path": "solve.py",
                "type": "solve_script",
                "how_to_run": "python solve.py",
            }
        ],
    }

    normalized = module._normalize_result_payload(spec, raw)
    assert normalized["status"] == "flag_found"
    assert normalized["flag"] == "flag{demo}"
    assert normalized["deliverables"][0]["type"] == "solve_script"


def test_normalize_result_payload_preserves_math_deliverables_and_evidence() -> None:
    module = _load_agent_runner_module()
    spec = {"challenge_id": "abc-123", "challenge_name": "Example"}
    raw = {
        "status": "deliverable_produced",
        "deliverables": [
            {"path": "solve.sage", "type": "other", "how_to_run": "sage solve.sage"},
            {
                "path": "solve.py",
                "type": "solve_script",
                "how_to_run": "python solve.py",
            },
        ],
        "evidence": [
            {
                "kind": "command",
                "ref": "sage solve.sage",
                "summary": "Recovered private exponent.",
            },
            {
                "kind": "not-a-kind",
                "ref": "matrix.txt",
                "summary": "Intermediate matrix output.",
            },
        ],
    }

    normalized = module._normalize_result_payload(spec, raw)
    assert normalized["status"] == "deliverable_produced"
    assert normalized["deliverables"][0] == {
        "path": "solve.sage",
        "type": "other",
        "how_to_run": "sage solve.sage",
    }
    assert normalized["deliverables"][1]["type"] == "solve_script"
    assert normalized["evidence"][0]["kind"] == "command"
    assert normalized["evidence"][1]["kind"] == "file"
    assert normalized["evidence"][1]["ref"] == "matrix.txt"


def test_normalize_result_payload_strips_workspace_run_prefix_from_deliverables() -> (
    None
):
    module = _load_agent_runner_module()
    spec = {"challenge_id": "abc-123", "challenge_name": "Example"}
    raw = {
        "status": "deliverable_produced",
        "deliverables": [
            {
                "path": "/workspace/run/solve.py",
                "type": "solve_script",
                "how_to_run": "python /workspace/run/solve.py",
            }
        ],
    }

    normalized = module._normalize_result_payload(spec, raw)
    assert normalized["deliverables"][0]["path"] == "solve.py"


def test_blocked_result_includes_failure_reason_code() -> None:
    module = _load_agent_runner_module()
    payload = module._blocked_result(
        {"challenge_id": "abc", "challenge_name": "Example"},
        "quota",
        failure_reason_code="provider_quota_or_auth",
    )
    assert payload["failure_reason_code"] == "provider_quota_or_auth"


def test_codex_command_defaults_without_inline_mcp_overrides(tmp_path) -> None:
    module = _load_agent_runner_module()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("test", encoding="utf-8")

    command, stdin_input, source, invocation_env = module._resolve_backend_command(
        {"backend": "codex"},
        "codex",
        prompt_file,
    )
    assert source == "default-codex-command"
    assert stdin_input == "test"
    assert invocation_env == {}
    joined = " ".join(command)
    assert "--json" in command
    assert 'model_reasoning_effort="medium"' in joined


def test_codex_command_applies_agent_invocation_model_and_extra_args(tmp_path) -> None:
    module = _load_agent_runner_module()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("test", encoding="utf-8")

    command, stdin_input, source, invocation_env = module._resolve_backend_command(
        {
            "backend": "codex",
            "agent_invocation": {
                "model": "gpt-5.4",
                "profile": "ctf",
                "extra_args": ["--search", "full"],
                "env": {
                    "CODEX_BASE_URL": "https://api.example",
                    "OPENAI_API_KEY": "ignore-me",
                },
            },
        },
        "codex",
        prompt_file,
    )
    assert source == "default-codex-command"
    assert stdin_input == "test"
    assert "--model" in command
    assert "gpt-5.4" in command
    assert "--profile" in command
    assert "--search" in command
    assert invocation_env == {
        "CODEX_BASE_URL": "https://api.example",
    }


def test_write_managed_codex_mcp_config_includes_flag_verify_by_default(
    monkeypatch, tmp_path
) -> None:
    module = _load_agent_runner_module()
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("CODEX_FLAG_VERIFY_MCP_ENABLED", raising=False)

    module._write_managed_codex_mcp_config()
    config_path = codex_home / "config.toml"
    rendered = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.flag_verify]" in rendered
    assert 'command = "python"' in rendered
    assert (
        'args = ["/usr/local/bin/flag_verify_mcp.py", "--spec", "/workspace/run/spec.json"]'
        in rendered
    )


def test_write_managed_codex_mcp_config_can_disable_flag_verify(
    monkeypatch, tmp_path
) -> None:
    module = _load_agent_runner_module()
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_FLAG_VERIFY_MCP_ENABLED", "0")

    module._write_managed_codex_mcp_config()
    config_path = codex_home / "config.toml"
    if config_path.exists():
        assert "[mcp_servers.flag_verify]" not in config_path.read_text(
            encoding="utf-8"
        )


def test_write_managed_codex_mcp_config_can_enable_flag_submit(
    monkeypatch, tmp_path
) -> None:
    module = _load_agent_runner_module()
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_FLAG_SUBMIT_MCP_ENABLED", "1")

    module._write_managed_codex_mcp_config()
    rendered = (codex_home / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.flag_submit]" in rendered
    assert (
        'args = ["/usr/local/bin/flag_submit_mcp.py", "--spec", "/workspace/run/spec.json"]'
        in rendered
    )


def test_write_managed_codex_mcp_config_includes_ida_url(monkeypatch, tmp_path) -> None:
    module = _load_agent_runner_module()
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    module._write_managed_codex_mcp_config("http://127.0.0.1:8745/mcp")
    config_path = codex_home / "config.toml"
    rendered = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.ida_pro]" in rendered
    assert 'url = "http://127.0.0.1:8745/mcp"' in rendered


def test_start_idalib_mcp_returns_disabled_when_ida_not_enabled(monkeypatch) -> None:
    module = _load_agent_runner_module()
    monkeypatch.delenv("SANDBOX_IDA_ENABLED", raising=False)
    monkeypatch.delenv("SANDBOX_IDA_INSTALL_PATH", raising=False)
    monkeypatch.delenv("IDADIR", raising=False)

    process, url = module._start_idalib_mcp_if_available()
    assert process is None
    assert url is None


def test_render_continuation_context_mentions_deliverable_bundle_paths() -> None:
    module = _load_agent_runner_module()
    rendered = module._render_continuation_context(
        {
            "continuation": {
                "is_continuation": True,
                "parent_run_id": "run-1",
                "type": "strategy_change",
                "depth": 2,
                "input": "keep going",
                "mount_path": "/workspace/continuation",
                "parent_result_path": "/workspace/continuation/parent_result.json",
                "parent_readme_path": "/workspace/continuation/parent_readme.md",
                "request_path": "/workspace/continuation/continuation_request.json",
                "deliverables_manifest_path": "/workspace/continuation/deliverables_manifest.json",
                "deliverables_mount_path": "/workspace/continuation/deliverables",
            }
        }
    )
    assert "/workspace/continuation/deliverables_manifest.json" in rendered
    assert "/workspace/continuation/deliverables" in rendered


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
    fake_registry = SimpleNamespace(
        reg_write_int=lambda key, value: calls.append((key, value))
    )

    monkeypatch.setenv("SANDBOX_IDA_ACCEPT_EULA", "1")
    monkeypatch.setenv("SANDBOX_IDA_EULA_VERSIONS", "90,91,92,93")
    monkeypatch.setitem(sys.modules, "idapro", object())
    monkeypatch.setitem(sys.modules, "ida_registry", fake_registry)

    accepted = module._accept_ida_eula("/opt/ida")
    assert accepted is True
    assert os.environ.get("IDADIR") == "/opt/ida"
    assert calls == [("EULA 90", 1), ("EULA 91", 1), ("EULA 92", 1), ("EULA 93", 1)]


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


def test_seed_writable_codex_home_copies_skill_seed(monkeypatch, tmp_path) -> None:
    module = _load_agent_runner_module()
    skills_seed_dir = tmp_path / "skills-seed"
    codex_home = tmp_path / "codex-home"
    (skills_seed_dir / "ctf-player").mkdir(parents=True)
    (skills_seed_dir / "ctf-player" / "SKILL.md").write_text(
        "# ctf-player", encoding="utf-8"
    )
    (skills_seed_dir / "ctf-player" / "references").mkdir(parents=True)
    (skills_seed_dir / "ctf-player" / "references" / "notes.txt").write_text(
        "hello", encoding="utf-8"
    )

    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_SKILLS_SEED_DIR", str(skills_seed_dir))
    monkeypatch.delenv("CODEX_AUTH_SEED_DIR", raising=False)
    module._seed_writable_codex_home()

    copied_skill = codex_home / "skills" / "ctf-player" / "SKILL.md"
    copied_ref = codex_home / "skills" / "ctf-player" / "references" / "notes.txt"
    assert copied_skill.exists()
    assert copied_skill.read_text(encoding="utf-8") == "# ctf-player"
    assert copied_ref.exists()
    assert copied_ref.read_text(encoding="utf-8") == "hello"


def test_runner_loop_retries_retryable_blocked_attempt_and_snapshots_state(
    monkeypatch, tmp_path
) -> None:
    module = _load_agent_runner_module()
    _configure_runner_paths(module, tmp_path)

    spec = {
        "challenge_id": "abc-123",
        "challenge_name": "Example",
        "backend": "codex",
        "budgets": {"max_minutes": 10},
        "runner_loop_policy": {
            "enabled": True,
            "max_attempts": 3,
            "target_status": "flag_found",
            "retry_on_statuses": ["blocked"],
            "retry_on_reason_codes": ["provider_quota_or_auth"],
            "continue_on_partial_success": True,
            "min_seconds_remaining": 0,
        },
    }

    prompt_contexts: list[str] = []

    def _fake_render_prompt(_spec, *, runner_loop_context=None):
        prompt_contexts.append(runner_loop_context or "")
        return f"prompt-{len(prompt_contexts)}"

    responses = [
        {
            "exit_code": 2,
            "readme": "# Attempt 1\n\nBlocked.\n",
            "result": {
                "status": "blocked",
                "failure_reason_code": "provider_quota_or_auth",
                "failure_reason_detail": "quota",
                "notes": "quota",
            },
            "last_message": "attempt-1",
        },
        {
            "exit_code": 0,
            "readme": "# Attempt 2\n\nSolved.\n",
            "result": {
                "status": "flag_found",
                "flag": "flag{demo}",
                "flag_verification": {
                    "method": "none",
                    "verified": False,
                    "details": "candidate",
                },
                "deliverables": [{"path": "solve.py", "type": "solve_script"}],
                "notes": "done",
            },
            "last_message": "attempt-2",
        },
    ]

    def _fake_run_backend_attempt(_spec, backend, prompt):
        response = responses.pop(0)
        module._write_readme(response["readme"])
        module._write_result(response["result"])
        (module.RUN_DIR / "codex_last_message.txt").write_text(
            response["last_message"], encoding="utf-8"
        )
        (module.RUN_DIR / "solve.py").write_text("print('ok')\n", encoding="utf-8")
        assert backend == "codex"
        assert prompt.startswith("prompt-")
        return int(response["exit_code"])

    monkeypatch.setattr(module, "_render_prompt", _fake_render_prompt)
    monkeypatch.setattr(module, "_run_backend_attempt", _fake_run_backend_attempt)

    exit_code = module.run_backend_attempt_loop(spec, backend="codex")

    assert exit_code == 0
    assert len(prompt_contexts) == 2
    assert "Previous attempt snapshot" in prompt_contexts[1]
    assert "provider_quota_or_auth" in prompt_contexts[1]

    first_attempt_dir = module.RUN_DIR / "attempts" / "001"
    assert (first_attempt_dir / "result.normalized.json").exists()
    assert (first_attempt_dir / "README.md").exists()
    assert (first_attempt_dir / "codex_last_message.txt").exists()
    assert (
        json.loads((first_attempt_dir / "decision.json").read_text(encoding="utf-8"))[
            "action"
        ]
        == "continue"
    )

    final_result = json.loads(
        (module.RUN_DIR / "result.json").read_text(encoding="utf-8")
    )
    assert final_result["status"] == "flag_found"

    loop_state = json.loads(module.RUNNER_LOOP_STATE_PATH.read_text(encoding="utf-8"))
    assert loop_state["total_attempts"] == 2
    assert loop_state["final_attempt_number"] == 2
    assert loop_state["stopped_because"] == "target_status_reached"
    assert loop_state["attempts"][0]["decision"] == "continue"
    assert loop_state["attempts"][1]["decision"] == "stop"


def test_runner_loop_clears_stale_contract_files_before_retry(
    monkeypatch, tmp_path
) -> None:
    module = _load_agent_runner_module()
    _configure_runner_paths(module, tmp_path)

    spec = {
        "challenge_id": "abc-123",
        "challenge_name": "Example",
        "backend": "codex",
        "budgets": {"max_minutes": 10},
        "runner_loop_policy": {
            "enabled": True,
            "max_attempts": 2,
            "target_status": "flag_found",
            "retry_on_statuses": ["blocked"],
            "retry_on_reason_codes": ["provider_quota_or_auth"],
            "continue_on_partial_success": True,
            "min_seconds_remaining": 0,
        },
    }

    attempt_counter = {"value": 0}

    def _fake_render_prompt(_spec, *, runner_loop_context=None):
        return str(runner_loop_context or "prompt")

    def _fake_run_backend_attempt(_spec, backend, prompt):
        attempt_counter["value"] += 1
        assert backend == "codex"
        assert prompt
        if attempt_counter["value"] == 1:
            module._write_readme("# Attempt 1\n")
            module._write_result(
                {
                    "status": "blocked",
                    "failure_reason_code": "provider_quota_or_auth",
                    "notes": "retry me",
                }
            )
        else:
            module._write_readme("# Attempt 2\n")
        return 0

    monkeypatch.setattr(module, "_render_prompt", _fake_render_prompt)
    monkeypatch.setattr(module, "_run_backend_attempt", _fake_run_backend_attempt)

    module.run_backend_attempt_loop(spec, backend="codex")

    final_result = json.loads(
        (module.RUN_DIR / "result.json").read_text(encoding="utf-8")
    )
    assert final_result["status"] == "blocked"
    assert final_result["failure_reason_code"] == "sandbox_output_contract_missing"

    first_attempt = json.loads(
        (module.RUN_DIR / "attempts" / "001" / "result.normalized.json").read_text(
            encoding="utf-8"
        )
    )
    assert first_attempt["failure_reason_code"] == "provider_quota_or_auth"
