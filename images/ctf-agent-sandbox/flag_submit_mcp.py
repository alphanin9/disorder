#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL_VERSION = "2024-11-05"
WIRE_FORMAT_JSONL = "jsonl"
WIRE_FORMAT_CONTENT_LENGTH = "content-length"
_wire_format = WIRE_FORMAT_JSONL


def _read_message() -> dict[str, Any] | None:
    global _wire_format

    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            continue

        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith((b"{", b"[")):
            _wire_format = WIRE_FORMAT_JSONL
            return json.loads(stripped.decode("utf-8"))

        if b":" in stripped:
            headers: dict[str, str] = {}

            def _capture_header(raw_line: bytes) -> None:
                header_line = raw_line.decode("utf-8", errors="replace").strip()
                if not header_line or ":" not in header_line:
                    return
                name, value = header_line.split(":", 1)
                headers[name.strip().lower()] = value.strip()

            _capture_header(line)
            while True:
                header_line = sys.stdin.buffer.readline()
                if not header_line:
                    return None
                if header_line in {b"\r\n", b"\n"}:
                    break
                _capture_header(header_line)

            length_raw = headers.get("content-length")
            if not length_raw:
                continue
            length = int(length_raw)
            body = sys.stdin.buffer.read(length)
            if not body:
                return None
            _wire_format = WIRE_FORMAT_CONTENT_LENGTH
            return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if _wire_format == WIRE_FORMAT_CONTENT_LENGTH:
        sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(encoded)
    else:
        sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()


def _json_rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


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
            "serverInfo": {"name": "ctf-flag-submit", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        },
    )


def _handle_tools_list(request_id: Any) -> dict[str, Any]:
    return _json_rpc_result(
        request_id,
        {
            "tools": [
                {
                    "name": "submit_flag_candidate",
                    "description": (
                        "Submit a candidate flag through the control-plane run proxy. "
                        "Uses backend-stored per-CTF credentials and returns a flag_verification verdict."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "flag": {
                                "type": "string",
                                "description": "Candidate flag value to submit for the current run.",
                            }
                        },
                        "required": ["flag"],
                        "additionalProperties": False,
                    },
                }
            ]
        },
    )


def _control_plane_base_url() -> str:
    base_url = str(os.getenv("DISORDER_CONTROL_PLANE_URL") or "").strip()
    if base_url:
        return base_url.rstrip("/")

    port = str(os.getenv("DISORDER_CONTROL_PLANE_PORT") or "").strip() or "8000"
    return f"http://host.docker.internal:{port}"


def _submit_flag_via_control_plane(spec: dict[str, Any], flag: str) -> dict[str, Any]:
    run_id = str(spec.get("run_id") or "").strip()
    if not run_id:
        raise RuntimeError("spec.json is missing run_id")

    base_url = _control_plane_base_url()
    url = f"{base_url}/runs/{run_id}/submit-flag"
    body = json.dumps({"flag": flag}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    bearer = str(os.getenv("DISORDER_CONTROL_PLANE_TOKEN") or "").strip()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    timeout = float(os.getenv("DISORDER_FLAG_SUBMIT_TIMEOUT_SECONDS", "15"))
    request = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_preview = ""
        try:
            body_preview = exc.read().decode("utf-8", errors="replace")[:512]
        except Exception:
            body_preview = ""
        raise RuntimeError(
            f"Control-plane flag submit failed with HTTP {exc.code}: {body_preview or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach control-plane flag submit endpoint: {exc.reason}") from exc


def _handle_tools_call(request_id: Any, payload: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params")
    if not isinstance(params, dict):
        return _json_rpc_result(
            request_id,
            {"isError": True, "content": [{"type": "text", "text": "Invalid tools/call params"}]},
        )

    tool_name = str(params.get("name") or "")
    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    if tool_name != "submit_flag_candidate":
        return _json_rpc_result(
            request_id,
            {"isError": True, "content": [{"type": "text", "text": f"Unknown tool '{tool_name}'"}]},
        )

    flag_value = str(arguments.get("flag") or "").strip()
    if not flag_value:
        return _json_rpc_result(
            request_id,
            {"isError": True, "content": [{"type": "text", "text": "Missing required argument: flag"}]},
        )

    try:
        response_payload = _submit_flag_via_control_plane(spec, flag_value)
    except Exception as exc:
        return _json_rpc_result(
            request_id,
            {
                "isError": True,
                "content": [{"type": "text", "text": str(exc)}],
            },
        )

    return _json_rpc_result(
        request_id,
        {
            "content": [{"type": "text", "text": json.dumps(response_payload)}],
            "structuredContent": response_payload,
        },
    )


def serve(spec_path: Path) -> int:
    if not spec_path.exists():
        print(f"spec.json not found at {spec_path}", file=sys.stderr)
        return 2

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    run_id = str(spec.get("run_id") or "").strip() or "unknown"
    print(
        f"[flag-submit-mcp] run_id={run_id} control_plane_base_url={_control_plane_base_url()}",
        file=sys.stderr,
        flush=True,
    )

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
                _write_message(_handle_tools_call(request_id, request, spec))
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
    parser = argparse.ArgumentParser(description="MCP server for candidate flag submission")
    parser.add_argument("--spec", default="/workspace/run/spec.json", help="Path to run spec.json")
    args = parser.parse_args()
    return serve(Path(args.spec))


if __name__ == "__main__":
    raise SystemExit(main())
