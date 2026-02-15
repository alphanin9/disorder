#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL_VERSION = "2024-11-05"


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        header_line = line.decode("utf-8", errors="replace").strip()
        if not header_line or ":" not in header_line:
            continue
        name, value = header_line.split(":", 1)
        headers[name.strip().lower()] = value.strip()

    length_raw = headers.get("content-length")
    if not length_raw:
        return None
    length = int(length_raw)
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(encoded)
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
            "serverInfo": {"name": "ctf-ida", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        },
    )


def _handle_tools_list(request_id: Any) -> dict[str, Any]:
    # Stub: IDA headless integration is environment-specific and depends on a mounted IDA install.
    return _json_rpc_result(
        request_id,
        {
            "tools": [
                {
                    "name": "ida_status",
                    "description": "Return whether an IDA installation is available at /opt/ida.",
                    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                }
            ]
        },
    )


def _handle_tools_call(request_id: Any, payload: dict[str, Any], ida_dir: Path) -> dict[str, Any]:
    params = payload.get("params")
    if not isinstance(params, dict):
        return _json_rpc_result(
            request_id,
            {"isError": True, "content": [{"type": "text", "text": "Invalid tools/call params"}]},
        )

    tool_name = str(params.get("name") or "")
    if tool_name != "ida_status":
        return _json_rpc_result(
            request_id,
            {"isError": True, "content": [{"type": "text", "text": f"Unknown tool '{tool_name}'"}]},
        )

    ok = ida_dir.exists()
    result = {"available": ok, "path": str(ida_dir), "notes": "Stub MCP: mount IDA to /opt/ida and extend tools."}
    return _json_rpc_result(
        request_id,
        {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result},
    )


def serve(*, ida_dir: Path) -> int:
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
                _write_message(_handle_tools_call(request_id, request, ida_dir))
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
    parser = argparse.ArgumentParser(description="Stub MCP server for IDA (optional mount)")
    parser.add_argument("--ida-dir", default="/opt/ida", help="Expected IDA install dir (default: /opt/ida)")
    parser.add_argument("--workspace", default="/workspace/run", help="Unused; reserved for future tooling outputs.")
    args = parser.parse_args()
    return serve(ida_dir=Path(args.ida_dir))


if __name__ == "__main__":
    raise SystemExit(main())

