#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
