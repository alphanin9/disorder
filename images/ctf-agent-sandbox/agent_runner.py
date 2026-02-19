#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

SPEC_PATH = Path("/workspace/run/spec.json")
RUN_DIR = Path("/workspace/run")
CHAL_DIR = Path("/workspace/chal")
PROMPT_TEMPLATE_PATH = Path("/usr/local/share/agent_prompt.txt")
TOOLING_GUIDE_PATH = Path("/usr/local/share/ctf_tooling_guide.md")
RESULT_STATUSES = {"flag_found", "deliverable_produced", "blocked"}
STOP_CRITERIA_VALUES = {"primary", "secondary", "none"}
DELIVERABLE_TYPES = {"solve_script", "exploit", "binary", "writeup", "other"}
EVIDENCE_KINDS = {"command", "file", "log", "decompiler"}
FLAG_VERIFICATION_METHODS = {"platform_submit", "local_check", "regex_only", "none"}
MANAGED_MCP_CONFIG_BEGIN = "# BEGIN DISORDER MANAGED MCP SERVERS"
MANAGED_MCP_CONFIG_END = "# END DISORDER MANAGED MCP SERVERS"


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _codex_home_path() -> Path:
    return Path(os.getenv("CODEX_HOME") or (Path.home() / ".codex"))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_result(payload: dict[str, Any]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_readme(content: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "README.md").write_text(content, encoding="utf-8")


def _copy_seed_tree(seed_dir: Path, target_root: Path, file_mode: int | None = None) -> int:
    if not seed_dir.exists() or not seed_dir.is_dir():
        return 0

    copied = 0
    for source in seed_dir.rglob("*"):
        if source.is_dir():
            continue
        rel = source.relative_to(seed_dir)
        target = target_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        copied += 1
        if file_mode is not None:
            try:
                target.chmod(file_mode)
            except OSError:
                pass
    return copied


def _seed_writable_codex_home() -> None:
    codex_home = _codex_home_path()
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_seed_dir = Path(os.getenv("CODEX_AUTH_SEED_DIR", "/workspace/run/.auth_seed/codex"))
    _copy_seed_tree(auth_seed_dir, codex_home, file_mode=0o600)

    skills_seed_dir = Path(os.getenv("CODEX_SKILLS_SEED_DIR", "/workspace/run/.skill_seed/codex/skills"))
    skills_dir = Path(os.getenv("CODEX_SKILLS_DIR") or (codex_home / "skills"))
    copied_skills = _copy_seed_tree(skills_seed_dir, skills_dir)
    if copied_skills > 0:
        print(f"[agent-runner] seeded {copied_skills} Codex skill files into {skills_dir}", flush=True)


def _blocked_result(spec: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "challenge_id": spec.get("challenge_id", ""),
        "challenge_name": spec.get("challenge_name", ""),
        "status": "blocked",
        "stop_criterion_met": "none",
        "flag_verification": {
            "method": "none",
            "verified": False,
            "details": message,
        },
        "deliverables": [],
        "repro_steps": [],
        "key_findings": [],
        "evidence": [],
        "notes": message,
    }


def _list_challenge_artifacts() -> list[str]:
    if not CHAL_DIR.exists():
        return []
    paths: list[str] = []
    for path in CHAL_DIR.rglob("*"):
        if path.is_file():
            paths.append(path.relative_to(CHAL_DIR).as_posix())
    return sorted(paths)


def _render_prompt(spec: dict[str, Any]) -> str:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    tooling_guide = (
        TOOLING_GUIDE_PATH.read_text(encoding="utf-8")
        if TOOLING_GUIDE_PATH.exists()
        else "Tooling guide unavailable."
    )
    artifact_list = _list_challenge_artifacts()
    artifacts_preview = "\n".join(f"- {artifact}" for artifact in artifact_list[:200]) or "- (none)"
    return template.format(
        challenge_name=spec.get("challenge_name", "Unknown"),
        category=spec.get("category", "unknown"),
        points=spec.get("points", 0),
        description_md=spec.get("description_md", ""),
        reasoning_effort=spec.get("reasoning_effort", "medium"),
        challenge_artifacts=artifacts_preview,
        stop_criteria=json.dumps(spec.get("stop_criteria", {}), indent=2),
        allowed_endpoints=json.dumps(spec.get("allowed_endpoints", []), indent=2),
        tooling_guide=tooling_guide,
    )


def _mock_backend(spec: dict[str, Any]) -> None:
    deliverable = RUN_DIR / "solve.py"
    deliverable.write_text(
        "#!/usr/bin/env python3\nprint('mock solve placeholder')\n",
        encoding="utf-8",
    )
    os.chmod(deliverable, 0o755)

    _write_readme(
        "# Mock Run Output\n\n"
        "This run used the mock backend.\n\n"
        "- Challenge artifacts are in `/workspace/chal`.\n"
        "- Writable output is in `/workspace/run`.\n"
    )

    _write_result(
        {
            "challenge_id": spec.get("challenge_id", ""),
            "challenge_name": spec.get("challenge_name", ""),
            "status": "deliverable_produced",
            "stop_criterion_met": "secondary",
            "flag_verification": {
                "method": "none",
                "verified": False,
                "details": "Mock backend does not attempt flag verification",
            },
            "deliverables": [
                {
                    "path": "solve.py",
                    "type": "solve_script",
                    "how_to_run": "python solve.py",
                }
            ],
            "repro_steps": [
                "Inspect challenge files in /workspace/chal",
                "Run python solve.py",
            ],
            "key_findings": ["Mock backend executed successfully"],
            "evidence": [{"kind": "file", "ref": "solve.py", "summary": "Mock solve scaffold"}],
            "notes": "This result is synthetic for harness validation",
        }
    )


def _codex_auth_source() -> str | None:
    for env_name in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        if os.getenv(env_name):
            return f"env:{env_name}"

    codex_home = _codex_home_path()
    if not codex_home.exists():
        return None

    direct_files = (
        codex_home / "auth.json",
        codex_home / "credentials.json",
        codex_home / "token.json",
    )
    for file_path in direct_files:
        try:
            if file_path.exists() and file_path.is_file() and file_path.stat().st_size > 2:
                return f"filesystem:{file_path}"
        except OSError:
            continue

    try:
        for file_path in codex_home.rglob("*.json"):
            name = file_path.name.lower()
            if any(token in name for token in ("auth", "token", "credential")) and file_path.stat().st_size > 2:
                return f"filesystem:{file_path}"
    except OSError:
        return None
    return None


def _parse_port_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return parsed


def _strip_managed_mcp_block(content: str) -> str:
    lines = content.splitlines()
    kept: list[str] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if stripped == MANAGED_MCP_CONFIG_BEGIN:
            in_block = True
            continue
        if stripped == MANAGED_MCP_CONFIG_END:
            in_block = False
            continue
        if not in_block:
            kept.append(line)

    while kept and kept[-1] == "":
        kept.pop()
    if not kept:
        return ""
    return "\n".join(kept) + "\n"


def _managed_mcp_config_block(ida_url: str | None) -> str:
    lines: list[str] = []
    if _env_truthy("CODEX_FLAG_VERIFY_MCP_ENABLED", default=True):
        server_command = os.getenv("CODEX_FLAG_VERIFY_MCP_COMMAND", "python")
        mcp_script = os.getenv("CODEX_FLAG_VERIFY_MCP_SCRIPT", "/usr/local/bin/flag_verify_mcp.py")
        mcp_args = [mcp_script, "--spec", SPEC_PATH.as_posix()]
        lines.extend(
            [
                "[mcp_servers.flag_verify]",
                f"command = {json.dumps(server_command)}",
                f"args = {json.dumps(mcp_args)}",
                "",
            ]
        )

    if ida_url:
        lines.extend(
            [
                "[mcp_servers.ida_pro]",
                f"url = {json.dumps(ida_url)}",
                "",
            ]
        )

    if not lines:
        return ""
    block = [MANAGED_MCP_CONFIG_BEGIN, ""]
    block.extend(lines)
    block.append(MANAGED_MCP_CONFIG_END)
    return "\n".join(block) + "\n"


def _write_managed_codex_mcp_config(ida_url: str | None = None) -> None:
    codex_home = _codex_home_path()
    codex_home.mkdir(parents=True, exist_ok=True)
    config_path = codex_home / "config.toml"

    existing = ""
    if config_path.exists():
        existing = config_path.read_text(encoding="utf-8")

    cleaned = _strip_managed_mcp_block(existing)
    managed = _managed_mcp_config_block(ida_url)
    if managed:
        if cleaned and not cleaned.endswith("\n\n"):
            cleaned = cleaned + "\n"
        rendered = cleaned + managed
    else:
        rendered = cleaned

    if rendered:
        config_path.write_text(rendered, encoding="utf-8")
        print(f"[agent-runner] updated Codex MCP config at {config_path}", flush=True)
        return

    if config_path.exists():
        config_path.unlink()
        print(f"[agent-runner] removed empty Codex config at {config_path}", flush=True)


def _idalib_mcp_url(port: int) -> str:
    return os.getenv("SANDBOX_IDALIB_MCP_URL", f"http://127.0.0.1:{port}/mcp")


def _wait_for_port_listen(host: str, port: int, timeout_seconds: float, process: subprocess.Popen[str]) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _stop_background_process(process: subprocess.Popen[str] | None, name: str) -> None:
    if process is None or process.poll() is not None:
        return
    print(f"[agent-runner] stopping {name}", flush=True)
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _accept_ida_eula(ida_install_path: str) -> bool:
    if not _env_truthy("SANDBOX_IDA_ACCEPT_EULA", default=True):
        print("[agent-runner] IDA EULA acceptance disabled by SANDBOX_IDA_ACCEPT_EULA=0", flush=True)
        return True

    os.environ["IDADIR"] = ida_install_path
    try:
        import idapro  # noqa: F401
        import ida_registry  # type: ignore
    except Exception as exc:
        print(f"[agent-runner] IDA EULA acceptance failed: idapro/ida_registry unavailable ({exc})", flush=True)
        return False

    raw_versions = os.getenv("SANDBOX_IDA_EULA_VERSIONS", "90,91,92")
    versions = [token.strip() for token in raw_versions.split(",") if token.strip()]
    if not versions:
        versions = ["90", "91", "92"]

    for version in versions:
        key = f"EULA {version}"
        try:
            ida_registry.reg_write_int(key, 1)
        except Exception as exc:
            print(f"[agent-runner] IDA EULA acceptance failed writing '{key}': {exc}", flush=True)
            return False

    print(f"[agent-runner] IDA EULA accepted for versions: {', '.join(versions)}", flush=True)
    return True


def _start_idalib_mcp_if_available() -> tuple[subprocess.Popen[str] | None, str | None]:
    if not _env_truthy("SANDBOX_IDA_ENABLED", default=False):
        print("[agent-runner] IDA MCP disabled: SANDBOX_IDA_ENABLED is false", flush=True)
        return None, None

    ida_install_path = os.getenv("SANDBOX_IDA_INSTALL_PATH", "").strip() or os.getenv("IDADIR", "").strip()
    if not ida_install_path:
        print("[agent-runner] IDA MCP disabled: SANDBOX_IDA_INSTALL_PATH is not set", flush=True)
        return None, None

    if not Path(ida_install_path).exists():
        print(f"[agent-runner] IDA MCP disabled: installation path does not exist: {ida_install_path}", flush=True)
        return None, None

    if not _accept_ida_eula(ida_install_path):
        print("[agent-runner] IDA MCP disabled: unable to accept IDA EULA", flush=True)
        return None, None

    command_template = os.getenv("SANDBOX_IDALIB_MCP_COMMAND", "uv run idalib-mcp")
    command = shlex.split(command_template)
    if not command:
        print("[agent-runner] IDA MCP disabled: SANDBOX_IDALIB_MCP_COMMAND is empty", flush=True)
        return None, None

    if shutil.which(command[0]) is None:
        print(f"[agent-runner] IDA MCP disabled: command not found: {command[0]}", flush=True)
        return None, None

    port = _parse_port_env("SANDBOX_IDALIB_MCP_PORT", 8745)
    timeout_seconds = float(os.getenv("SANDBOX_IDALIB_MCP_STARTUP_TIMEOUT", "15"))
    if timeout_seconds <= 0:
        timeout_seconds = 15.0

    process_env = os.environ.copy()
    for env_name in (
        "IDADIR",
        "IDA_PATH",
        "IDA_DIR",
        "IDA_INSTALL_PATH",
        "IDA_INSTALL_DIR",
        "IDALIB_IDA_PATH",
        "IDALIB_IDA_DIR",
    ):
        process_env.setdefault(env_name, ida_install_path)

    print(f"[agent-runner] starting idalib MCP: {' '.join(command)}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=RUN_DIR,
        env=process_env,
    )
    if not _wait_for_port_listen("127.0.0.1", port, timeout_seconds=timeout_seconds, process=process):
        print("[agent-runner] IDA MCP failed to become ready; disabling for this run", flush=True)
        _stop_background_process(process, "idalib-mcp")
        return None, None

    url = _idalib_mcp_url(port)
    print(f"[agent-runner] IDA MCP enabled at {url}", flush=True)
    return process, url


def _resolve_backend_command(
    backend: str,
    prompt_file: Path,
) -> tuple[list[str], str | None, str]:
    reasoning_effort = "medium"
    if SPEC_PATH.exists():
        try:
            spec_payload = _read_json(SPEC_PATH)
            raw_effort = spec_payload.get("reasoning_effort")
            if not isinstance(raw_effort, str):
                budgets = spec_payload.get("budgets")
                if isinstance(budgets, dict):
                    raw_effort = budgets.get("reasoning_effort")
            if isinstance(raw_effort, str) and raw_effort.lower() in {"low", "medium", "high", "xhigh"}:
                reasoning_effort = raw_effort.lower()
        except Exception:
            reasoning_effort = "medium"

    if backend == "codex":
        command_template = os.getenv("CODEX_CLI_CMD")
        if command_template:
            formatted = command_template.format(
                prompt_file=str(prompt_file),
                run_dir=str(RUN_DIR),
                chal_dir=str(CHAL_DIR),
                reasoning_effort=reasoning_effort,
            )
            return shlex.split(formatted), None, "custom-codex-command"
        command = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "--cd",
            str(RUN_DIR),
            "--output-last-message",
            str(RUN_DIR / "codex_last_message.txt"),
            "-c",
            f"model_reasoning_effort={json.dumps(reasoning_effort)}",
        ]
        command.append("-")
        return command, prompt_file.read_text(encoding="utf-8"), "default-codex-command"

    command_template = os.getenv("CLAUDE_CODE_CLI_CMD")
    if not command_template:
        return [], None, ""
    formatted = command_template.format(prompt_file=str(prompt_file), run_dir=str(RUN_DIR), chal_dir=str(CHAL_DIR))
    return shlex.split(formatted), None, "custom-claude-command"


def _run_external_backend(spec: dict[str, Any], backend: str, prompt: str) -> int:
    idalib_process: subprocess.Popen[str] | None = None
    ida_mcp_url: str | None = None
    if backend == "codex":
        auth_source = _codex_auth_source()
        if auth_source is None:
            message = (
                "Codex authentication is missing. Provide OPENAI_API_KEY (or CODEX_API_KEY), "
                "or upload tagged Codex auth files via the control-plane auth API/UI."
            )
            _write_readme("# Blocked\n\n" + message + "\n")
            _write_result(_blocked_result(spec, message))
            return 2
        idalib_process, ida_mcp_url = _start_idalib_mcp_if_available()
        _write_managed_codex_mcp_config(ida_url=ida_mcp_url)

    if backend == "codex":
        backend_name = "Codex CLI"
    else:
        backend_name = "Claude Code CLI"

    prompt_file = RUN_DIR / "agent_prompt_filled.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    command, stdin_input, command_source = _resolve_backend_command(
        backend=backend,
        prompt_file=prompt_file,
    )
    if not command:
        error = (
            f"{backend_name} command is not configured. Set "
            f"{'CODEX_CLI_CMD' if backend == 'codex' else 'CLAUDE_CODE_CLI_CMD'} "
            "to a runnable command template using {prompt_file} and {run_dir}."
        )
        _write_readme("# Blocked\n\n" + error + "\n")
        _write_result(_blocked_result(spec, error))
        _stop_background_process(idalib_process, "idalib-mcp")
        return 2

    if shutil.which(command[0]) is None:
        _write_readme("# Blocked\n\nConfigured backend binary not found.\n")
        _write_result(_blocked_result(spec, f"Backend binary not found: {command[0]}"))
        _stop_background_process(idalib_process, "idalib-mcp")
        return 2

    print(
        f"[agent-runner] executing backend command ({command_source}): {' '.join(command)}",
        flush=True,
    )
    try:
        process = subprocess.Popen(
            command,
            cwd=RUN_DIR,
            stdin=subprocess.PIPE if stdin_input is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        stream_stderr_live = not (backend == "codex" and _env_truthy("CODEX_JSONL_LIVE_LOG_ONLY", default=True))

        def _pump(stream, sink, printer, live: bool) -> None:
            if stream is None:
                return
            try:
                for line in iter(stream.readline, ""):
                    sink.append(line)
                    if live:
                        print(line, end="", file=printer, flush=True)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        stdout_thread = threading.Thread(target=_pump, args=(process.stdout, stdout_chunks, sys.stdout, True), daemon=True)
        stderr_thread = threading.Thread(
            target=_pump,
            args=(process.stderr, stderr_chunks, sys.stderr, stream_stderr_live),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        if stdin_input is not None and process.stdin is not None:
            process.stdin.write(stdin_input)
            process.stdin.close()

        returncode = process.wait()
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        stdout_text = "".join(stdout_chunks)
        stderr_text = "".join(stderr_chunks)

        if returncode != 0:
            if stderr_text and not stream_stderr_live:
                print("[agent-runner] codex stderr tail:", file=sys.stderr, flush=True)
                print(stderr_text[-8192:], file=sys.stderr, flush=True)
            message = _backend_failure_message(
                backend=backend,
                returncode=returncode,
                stdout=stdout_text,
                stderr=stderr_text,
            )
            if not (RUN_DIR / "README.md").exists():
                _write_readme("# Blocked\n\n" + message + "\n")
            if not (RUN_DIR / "result.json").exists():
                _write_result(_blocked_result(spec, message))

        return returncode
    finally:
        _stop_background_process(idalib_process, "idalib-mcp")


def _backend_failure_message(backend: str, returncode: int, stdout: str, stderr: str) -> str:
    output = f"{stdout}\n{stderr}".lower()
    if backend == "codex":
        if any(token in output for token in ("401", "unauthorized", "invalid api key", "authentication failed")):
            return (
                "Codex authentication failed. Set OPENAI_API_KEY (or CODEX_API_KEY), "
                "or verify uploaded tagged Codex auth files are valid for this run."
            )
        if "429" in output or "rate limit" in output:
            return "Codex request failed due to rate limiting. Retry later or use different credentials."

    return f"Backend command failed with exit code {returncode}"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _normalize_result_payload(spec: dict[str, Any], raw_result: Any) -> dict[str, Any]:
    if not isinstance(raw_result, dict):
        return _blocked_result(spec, "result.json did not contain an object")

    challenge_id = str(raw_result.get("challenge_id") or spec.get("challenge_id") or "")
    challenge_name = str(raw_result.get("challenge_name") or spec.get("challenge_name") or "")

    raw_status = str(raw_result.get("status") or "").strip().lower()
    if raw_status in RESULT_STATUSES:
        status = raw_status
    elif raw_result.get("flag_found") is True or (raw_result.get("flag") and "flag" in raw_status):
        status = "flag_found"
    elif "deliverable" in raw_status or isinstance(raw_result.get("deliverables"), list):
        status = "deliverable_produced"
    else:
        status = "blocked"

    raw_stop = str(raw_result.get("stop_criterion_met") or "").strip().lower()
    if raw_stop in STOP_CRITERIA_VALUES:
        stop_criterion_met = raw_stop
    elif status == "flag_found":
        stop_criterion_met = "primary"
    elif status == "deliverable_produced":
        stop_criterion_met = "secondary"
    else:
        stop_criterion_met = "none"

    flag = raw_result.get("flag")
    if status != "flag_found":
        flag = None
    elif flag is not None:
        flag = str(flag)

    raw_fv = raw_result.get("flag_verification") if isinstance(raw_result.get("flag_verification"), dict) else {}
    method = str(raw_fv.get("method") or "").strip().lower()
    if method not in FLAG_VERIFICATION_METHODS:
        method = "regex_only" if status == "flag_found" else "none"
    verified = bool(raw_fv.get("verified", False))
    details = str(raw_fv.get("details") or raw_result.get("summary") or raw_result.get("notes") or "").strip()
    if not details:
        if status == "flag_found":
            details = "Flag reported by backend but not yet verified."
        elif status == "blocked":
            details = "Backend did not provide a valid completion result."
        else:
            details = "No verification details provided."

    deliverables: list[dict[str, str]] = []
    raw_deliverables = raw_result.get("deliverables")
    if isinstance(raw_deliverables, list):
        for entry in raw_deliverables:
            if isinstance(entry, str):
                deliverables.append({"path": entry, "type": "other", "how_to_run": "See README.md"})
                continue
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "").strip()
            if not path:
                continue
            dtype = str(entry.get("type") or "other").strip().lower()
            if dtype not in DELIVERABLE_TYPES:
                dtype = "other"
            how_to_run = str(entry.get("how_to_run") or "See README.md").strip()
            deliverables.append({"path": path, "type": dtype, "how_to_run": how_to_run})

    evidence: list[dict[str, str]] = []
    raw_evidence = raw_result.get("evidence")
    if isinstance(raw_evidence, list):
        for entry in raw_evidence:
            if not isinstance(entry, dict):
                continue
            kind = str(entry.get("kind") or "file").strip().lower()
            if kind not in EVIDENCE_KINDS:
                kind = "file"
            ref = str(entry.get("ref") or "").strip()
            if not ref:
                continue
            summary = str(entry.get("summary") or "").strip() or "No summary provided."
            evidence.append({"kind": kind, "ref": ref, "summary": summary})
    elif isinstance(raw_result.get("evidence_files"), list):
        for entry in raw_result.get("evidence_files", []):
            ref = str(entry).strip()
            if ref:
                evidence.append({"kind": "file", "ref": ref, "summary": "Referenced by backend output."})

    return {
        "challenge_id": challenge_id,
        "challenge_name": challenge_name,
        "status": status,
        "stop_criterion_met": stop_criterion_met,
        "flag": flag,
        "flag_verification": {
            "method": method,
            "verified": verified,
            "details": details,
        },
        "deliverables": deliverables,
        "repro_steps": _string_list(raw_result.get("repro_steps")),
        "key_findings": _string_list(raw_result.get("key_findings")),
        "evidence": evidence,
        "notes": str(raw_result.get("notes") or raw_result.get("summary") or "").strip(),
    }


def _ensure_contract(spec: dict[str, Any]) -> int:
    result_path = RUN_DIR / "result.json"
    readme_path = RUN_DIR / "README.md"

    if not readme_path.exists():
        _write_readme("# Blocked\n\nMissing README.md from backend run.\n")

    if not result_path.exists():
        _write_result(_blocked_result(spec, "Missing result.json from backend run"))
        return 3

    try:
        parsed = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _write_result(_blocked_result(spec, f"Invalid result.json: {exc}"))
        return 3

    normalized = _normalize_result_payload(spec, parsed)
    _write_result(normalized)

    return 0


def main() -> int:
    if not SPEC_PATH.exists():
        print("[agent-runner] missing spec.json", file=sys.stderr)
        return 1

    _seed_writable_codex_home()
    spec = _read_json(SPEC_PATH)
    backend = spec.get("backend", "mock")
    artifact_list = _list_challenge_artifacts()

    print("[agent-runner] challenge triage", flush=True)
    print(f"[agent-runner] challenge={spec.get('challenge_name')} backend={backend}", flush=True)
    print(f"[agent-runner] allowed_endpoints={spec.get('allowed_endpoints', [])}", flush=True)
    print(f"[agent-runner] stop_criteria={spec.get('stop_criteria', {})}", flush=True)
    print(f"[agent-runner] challenge_artifact_count={len(artifact_list)}", flush=True)
    if artifact_list:
        print(f"[agent-runner] challenge_artifacts_preview={artifact_list[:20]}", flush=True)

    prompt = _render_prompt(spec)

    if backend == "mock":
        _mock_backend(spec)
        return _ensure_contract(spec)

    if backend in {"codex", "claude_code"}:
        exit_code = _run_external_backend(spec, backend=backend, prompt=prompt)
        contract_code = _ensure_contract(spec)
        return exit_code if exit_code != 0 else contract_code

    message = f"Unsupported backend: {backend}"
    _write_readme("# Blocked\n\n" + message + "\n")
    _write_result(_blocked_result(spec, message))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
