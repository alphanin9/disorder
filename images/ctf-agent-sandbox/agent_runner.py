#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SPEC_PATH = Path("/workspace/run/spec.json")
RUN_DIR = Path("/workspace/run")
CHAL_DIR = Path("/workspace/chal")
PROMPT_TEMPLATE_PATH = Path("/usr/local/share/agent_prompt.txt")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_result(payload: dict[str, Any]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_readme(content: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "README.md").write_text(content, encoding="utf-8")


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


def _render_prompt(spec: dict[str, Any]) -> str:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.format(
        challenge_name=spec.get("challenge_name", "Unknown"),
        category=spec.get("category", "unknown"),
        points=spec.get("points", 0),
        description_md=spec.get("description_md", ""),
        stop_criteria=json.dumps(spec.get("stop_criteria", {}), indent=2),
        allowed_endpoints=json.dumps(spec.get("allowed_endpoints", []), indent=2),
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


def _run_external_backend(spec: dict[str, Any], backend: str, prompt: str) -> int:
    if backend == "codex":
        command_template = os.getenv("CODEX_CLI_CMD")
        backend_name = "Codex CLI"
    else:
        command_template = os.getenv("CLAUDE_CODE_CLI_CMD")
        backend_name = "Claude Code CLI"

    if not command_template:
        error = (
            f"{backend_name} command is not configured. Set "
            f"{'CODEX_CLI_CMD' if backend == 'codex' else 'CLAUDE_CODE_CLI_CMD'}"
            " to a runnable command template using {prompt_file} and {run_dir}."
        )
        _write_readme("# Blocked\n\n" + error + "\n")
        _write_result(_blocked_result(spec, error))
        return 2

    prompt_file = RUN_DIR / "agent_prompt_filled.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    formatted = command_template.format(prompt_file=str(prompt_file), run_dir=str(RUN_DIR), chal_dir=str(CHAL_DIR))
    command = shlex.split(formatted)
    if not command:
        _write_readme("# Blocked\n\nInvalid backend command.\n")
        _write_result(_blocked_result(spec, "Configured backend command is empty"))
        return 2

    if shutil.which(command[0]) is None:
        _write_readme("# Blocked\n\nConfigured backend binary not found.\n")
        _write_result(_blocked_result(spec, f"Backend binary not found: {command[0]}"))
        return 2

    print(f"[agent-runner] executing backend command: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=RUN_DIR, capture_output=True, text=True)
    if completed.stdout:
        print(completed.stdout, flush=True)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, flush=True)

    if completed.returncode != 0:
        message = f"Backend command failed with exit code {completed.returncode}"
        if not (RUN_DIR / "README.md").exists():
            _write_readme("# Blocked\n\n" + message + "\n")
        if not (RUN_DIR / "result.json").exists():
            _write_result(_blocked_result(spec, message))

    return completed.returncode


def _ensure_contract(spec: dict[str, Any]) -> int:
    result_path = RUN_DIR / "result.json"
    readme_path = RUN_DIR / "README.md"

    if not readme_path.exists():
        _write_readme("# Blocked\n\nMissing README.md from backend run.\n")

    if not result_path.exists():
        _write_result(_blocked_result(spec, "Missing result.json from backend run"))
        return 3

    try:
        json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _write_result(_blocked_result(spec, f"Invalid result.json: {exc}"))
        return 3

    return 0


def main() -> int:
    if not SPEC_PATH.exists():
        print("[agent-runner] missing spec.json", file=sys.stderr)
        return 1

    spec = _read_json(SPEC_PATH)
    backend = spec.get("backend", "mock")

    print("[agent-runner] challenge triage", flush=True)
    print(f"[agent-runner] challenge={spec.get('challenge_name')} backend={backend}", flush=True)
    print(f"[agent-runner] allowed_endpoints={spec.get('allowed_endpoints', [])}", flush=True)
    print(f"[agent-runner] stop_criteria={spec.get('stop_criteria', {})}", flush=True)

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
