#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
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

        # Codex CLI uses JSON-RPC over newline-delimited UTF-8 JSON on stdio.
        if stripped.startswith((b"{", b"[")):
            _wire_format = WIRE_FORMAT_JSONL
            return json.loads(stripped.decode("utf-8"))

        # Backward-compatible support for Content-Length framing.
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


def _extract_flag_regex(spec: dict[str, Any]) -> tuple[str | None, str | None]:
    stop_criteria = spec.get("stop_criteria")
    if not isinstance(stop_criteria, dict):
        return None, None

    for key in ("primary", "secondary"):
        criterion = stop_criteria.get(key)
        if not isinstance(criterion, dict):
            continue
        if str(criterion.get("type")) != "FLAG_FOUND":
            continue
        config = criterion.get("config")
        if not isinstance(config, dict):
            continue
        regex = config.get("regex")
        if isinstance(regex, str) and regex.strip():
            return regex, key

    return None, None


def _verify_flag(spec: dict[str, Any], flag: str) -> dict[str, Any]:
    regex, source = _extract_flag_regex(spec)
    if regex is None:
        return {
            "method": "none",
            "verified": False,
            "details": "No FLAG_FOUND regex configured in run stop criteria.",
        }

    try:
        matched = bool(re.search(regex, flag))
    except re.error as exc:
        return {
            "method": "none",
            "verified": False,
            "details": f"FLAG_FOUND regex is invalid: {exc}",
        }

    details = (
        f"Regex local-check {'matched' if matched else 'did not match'} "
        f"{source or 'configured'} FLAG_FOUND pattern."
    )
    return {
        "method": "local_check",
        "verified": matched,
        "details": details,
    }


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
            "serverInfo": {"name": "ctf-flag-verify", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        },
    )


def _handle_tools_list(request_id: Any) -> dict[str, Any]:
    return _json_rpc_result(
        request_id,
        {
            "tools": [
                {
                    "name": "verify_flag_candidate",
                    "description": (
                        "Validate a candidate flag against the run FLAG_FOUND regex and return "
                        "a result.json-compatible flag_verification object."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "flag": {
                                "type": "string",
                                "description": "Candidate flag value to evaluate.",
                            }
                        },
                        "required": ["flag"],
                        "additionalProperties": False,
                    },
                }
            ]
        },
    )


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

    if tool_name != "verify_flag_candidate":
        return _json_rpc_result(
            request_id,
            {"isError": True, "content": [{"type": "text", "text": f"Unknown tool '{tool_name}'"}]},
        )

    flag_value = str(arguments.get("flag") or "").strip()
    if not flag_value:
        return _json_rpc_result(
            request_id,
            {
                "isError": True,
                "content": [{"type": "text", "text": "Missing required argument: flag"}],
            },
        )

    verification = _verify_flag(spec, flag_value)
    return _json_rpc_result(
        request_id,
        {
            "content": [{"type": "text", "text": json.dumps(verification)}],
            "structuredContent": verification,
        },
    )


def serve(spec_path: Path) -> int:
    if not spec_path.exists():
        print(f"spec.json not found at {spec_path}", file=sys.stderr)
        return 2

    spec = json.loads(spec_path.read_text(encoding="utf-8"))

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
    parser = argparse.ArgumentParser(description="MCP server for candidate flag verification")
    parser.add_argument("--spec", default="/workspace/run/spec.json", help="Path to run spec.json")
    args = parser.parse_args()
    return serve(Path(args.spec))


if __name__ == "__main__":
    raise SystemExit(main())
