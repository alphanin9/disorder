#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL_VERSION = "2024-11-05"


def _read_message() -> dict[str, Any] | None:
    # MCP stdio transport uses JSON-RPC messages serialized as one JSON per line.
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        return json.loads(text)


def _write_message(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _json_rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_response_text(*, text: str, structured: dict[str, Any] | None = None, is_error: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {"isError": is_error, "content": [{"type": "text", "text": text}]}
    if structured is not None:
        payload["structuredContent"] = structured
    return payload


def _safe_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s.startswith("0x"):
            return int(s, 16)
        return int(s, 10)
    raise ValueError("Expected integer")


def _which(binary: str) -> str | None:
    from shutil import which

    return which(binary)


class ExecResult:
    __slots__ = ("ok", "stdout", "stderr", "returncode")

    def __init__(self, *, ok: bool, stdout: str, stderr: str, returncode: int) -> None:
        self.ok = ok
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _run_subprocess(
    argv: list[str],
    *,
    input_text: str | None = None,
    cwd: Path | None = None,
    timeout_s: int = 30,
    env: dict[str, str] | None = None,
) -> ExecResult:
    try:
        proc = subprocess.run(
            argv,
            input=input_text,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=timeout_s,
            capture_output=True,
            env=env,
        )
        return ExecResult(ok=proc.returncode == 0, stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = (exc.stderr or "") + f"\nTimed out after {timeout_s}s"
        return ExecResult(ok=False, stdout=out, stderr=err, returncode=124)
    except Exception as exc:
        return ExecResult(ok=False, stdout="", stderr=str(exc), returncode=1)


def _sympy_eval(code: str, *, cwd: Path) -> ExecResult:
    prelude = "import sympy as sp\nfrom sympy import *\n"
    payload = prelude + "\n" + code.strip() + "\n"
    return _run_subprocess(["python", "-"], input_text=payload, cwd=cwd, timeout_s=30)


def _micromamba_root(workspace: Path) -> Path:
    return workspace / ".mamba"


def _ensure_sage_env(workspace: Path) -> tuple[bool, str]:
    if _which("sage") is not None:
        return True, "sage binary present"

    mamba = _which("micromamba")
    if mamba is None:
        return False, "micromamba is not installed in the sandbox image"

    root = _micromamba_root(workspace)
    env_prefix = root / "envs" / "sage"
    if (env_prefix / "bin" / "sage").exists():
        return True, f"sage env available at {env_prefix}"

    root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MAMBA_ROOT_PREFIX"] = str(root)
    env["MAMBA_NO_BANNER"] = "1"

    # Create a local conda env under /workspace/run. This is large; do it only on-demand.
    proc = _run_subprocess(
        [
            mamba,
            "create",
            "-y",
            "-p",
            str(env_prefix),
            "-c",
            "conda-forge",
            "sagemath",
        ],
        cwd=workspace,
        timeout_s=1800,
        env=env,
    )
    if not proc.ok:
        return False, f"failed to create sagemath env: {proc.stderr[-4000:]}"
    return True, f"created sagemath env at {env_prefix}"


def _sage_eval(code: str, *, workspace: Path) -> ExecResult:
    ok, details = _ensure_sage_env(workspace)
    if not ok:
        return ExecResult(ok=False, stdout="", stderr=details, returncode=1)

    if _which("sage") is not None:
        # Use system-installed sage if present.
        return _run_subprocess(["sage", "-python", "-"], input_text=code + "\n", cwd=workspace, timeout_s=60)

    root = _micromamba_root(workspace)
    env_prefix = root / "envs" / "sage"
    sage_bin = env_prefix / "bin" / "sage"
    if not sage_bin.exists():
        return ExecResult(ok=False, stdout="", stderr="sagemath env missing after ensure", returncode=1)
    return _run_subprocess([str(sage_bin), "-python", "-"], input_text=code + "\n", cwd=workspace, timeout_s=60)


def _factorint(n: int) -> dict[str, Any]:
    import sympy as sp

    factors = sp.factorint(n)
    return {str(k): int(v) for k, v in factors.items()}


def _crt(moduli: list[int], residues: list[int]) -> dict[str, Any]:
    import sympy as sp

    if len(moduli) != len(residues):
        raise ValueError("moduli and residues must have the same length")
    result = sp.ntheory.modular.crt(moduli, residues)
    if result is None:
        return {"ok": False, "x": None, "modulus": None}
    x, m = result
    return {"ok": True, "x": int(x), "modulus": int(m)}


def _modinv(a: int, m: int) -> int:
    import sympy as sp

    return int(sp.mod_inverse(a, m))


def _is_prime(n: int) -> bool:
    import sympy as sp

    return bool(sp.isprime(n))


def _handle_initialize(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params")
    protocol = DEFAULT_PROTOCOL_VERSION
    if isinstance(params, dict):
        incoming = params.get("protocolVersion")
        if isinstance(incoming, str) and incoming.strip():
            protocol = incoming

    return _json_rpc_result(
        request_id,
        {
            "protocolVersion": protocol,
            "serverInfo": {"name": "ctf-crypto-math", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        },
    )


def _handle_tools_list(request_id: Any) -> dict[str, Any]:
    return _json_rpc_result(
        request_id,
        {
            "tools": [
                {
                    "name": "sympy_eval",
                    "description": "Run a short Python snippet with sympy imported (stdout/stderr captured).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"code": {"type": "string"}},
                        "required": ["code"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "sage_eval",
                    "description": "Run a short snippet in a Sage environment (may download/create a local conda env on first use).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"code": {"type": "string"}},
                        "required": ["code"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "factorint",
                    "description": "Factor an integer using sympy.factorint.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"n": {"type": ["string", "integer"]}},
                        "required": ["n"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "crt",
                    "description": "Solve Chinese Remainder Theorem for moduli/residues arrays (sympy.ntheory.modular.crt).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "moduli": {"type": "array", "items": {"type": ["string", "integer"]}},
                            "residues": {"type": "array", "items": {"type": ["string", "integer"]}},
                        },
                        "required": ["moduli", "residues"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "modinv",
                    "description": "Compute modular inverse a^-1 mod m.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"a": {"type": ["string", "integer"]}, "m": {"type": ["string", "integer"]}},
                        "required": ["a", "m"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "is_prime",
                    "description": "Probable prime test using sympy.isprime.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"n": {"type": ["string", "integer"]}},
                        "required": ["n"],
                        "additionalProperties": False,
                    },
                },
            ]
        },
    )


def _handle_tools_call(request_id: Any, payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    params = payload.get("params")
    if not isinstance(params, dict):
        return _json_rpc_result(request_id, _tool_response_text(text="Invalid tools/call params", is_error=True))

    tool_name = str(params.get("name") or "")
    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    try:
        if tool_name == "sympy_eval":
            code = str(arguments.get("code") or "")
            result = _sympy_eval(code, cwd=workspace)
            structured = {"ok": result.ok, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
            return _json_rpc_result(request_id, _tool_response_text(text=json.dumps(structured), structured=structured, is_error=not result.ok))

        if tool_name == "sage_eval":
            code = str(arguments.get("code") or "")
            result = _sage_eval(code, workspace=workspace)
            structured = {"ok": result.ok, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
            return _json_rpc_result(request_id, _tool_response_text(text=json.dumps(structured), structured=structured, is_error=not result.ok))

        if tool_name == "factorint":
            n = _safe_int(arguments.get("n"))
            factors = _factorint(n)
            return _json_rpc_result(request_id, _tool_response_text(text=json.dumps(factors), structured=factors))

        if tool_name == "crt":
            moduli_raw = arguments.get("moduli")
            residues_raw = arguments.get("residues")
            if not isinstance(moduli_raw, list) or not isinstance(residues_raw, list):
                raise ValueError("moduli/residues must be arrays")
            moduli = [_safe_int(item) for item in moduli_raw]
            residues = [_safe_int(item) for item in residues_raw]
            result = _crt(moduli, residues)
            return _json_rpc_result(request_id, _tool_response_text(text=json.dumps(result), structured=result, is_error=not bool(result.get("ok"))))

        if tool_name == "modinv":
            a = _safe_int(arguments.get("a"))
            m = _safe_int(arguments.get("m"))
            inv = _modinv(a, m)
            result = {"inv": inv}
            return _json_rpc_result(request_id, _tool_response_text(text=json.dumps(result), structured=result))

        if tool_name == "is_prime":
            n = _safe_int(arguments.get("n"))
            result = {"is_prime": _is_prime(n)}
            return _json_rpc_result(request_id, _tool_response_text(text=json.dumps(result), structured=result))

        return _json_rpc_result(request_id, _tool_response_text(text=f"Unknown tool '{tool_name}'", is_error=True))
    except Exception as exc:
        return _json_rpc_result(request_id, _tool_response_text(text=str(exc), is_error=True))


def serve(*, workspace: Path) -> int:
    workspace.mkdir(parents=True, exist_ok=True)
    while True:
        request = _read_message()
        if request is None:
            return 0

        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            if request_id is not None:
                _write_message(_json_rpc_error(request_id, -32600, "Invalid request"))
            continue

        if method == "initialize":
            if request_id is not None:
                _write_message(_handle_initialize(request_id, request))
            continue

        if method == "notifications/initialized":
            continue

        if method == "ping":
            if request_id is not None:
                _write_message(_json_rpc_result(request_id, {}))
            continue

        if method == "tools/list":
            if request_id is not None:
                _write_message(_handle_tools_list(request_id))
            continue

        if method == "tools/call":
            if request_id is not None:
                _write_message(_handle_tools_call(request_id, request, workspace))
            continue

        if method == "shutdown":
            if request_id is not None:
                _write_message(_json_rpc_result(request_id, {}))
            continue

        if method == "exit":
            return 0

        if request_id is not None:
            _write_message(_json_rpc_error(request_id, -32601, f"Method not found: {method}"))


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP server for crypto/math helper tools (sympy/sage)")
    parser.add_argument("--workspace", default="/workspace/run", help="Writable workspace root (default: /workspace/run)")
    args = parser.parse_args()
    return serve(workspace=Path(args.workspace))


if __name__ == "__main__":
    raise SystemExit(main())
