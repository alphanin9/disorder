from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "images" / "ctf-agent-sandbox" / "flag_verify_mcp.py"
    spec = importlib.util.spec_from_file_location("flag_verify_mcp_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load flag_verify_mcp module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_flag_matches_primary_regex() -> None:
    module = _load_module()
    spec = {
        "stop_criteria": {
            "primary": {"type": "FLAG_FOUND", "config": {"regex": r"^flag\{.+\}$"}},
            "secondary": {"type": "DELIVERABLES_READY", "config": {}},
        }
    }

    verification = module._verify_flag(spec, "flag{ok}")
    assert verification["method"] == "local_check"
    assert verification["verified"] is True


def test_verify_flag_without_regex_returns_none_method() -> None:
    module = _load_module()
    verification = module._verify_flag({"stop_criteria": {}}, "flag{maybe}")
    assert verification["method"] == "none"
    assert verification["verified"] is False


def test_stdio_jsonl_initialize_and_tool_call(tmp_path) -> None:
    module_path = Path(__file__).resolve().parents[2] / "images" / "ctf-agent-sandbox" / "flag_verify_mcp.py"
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "stop_criteria": {
                    "primary": {
                        "type": "FLAG_FOUND",
                        "config": {"regex": r"^flag\{.+\}$"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"elicitation": {"form": {}}},
                "clientInfo": {"name": "codex-mcp-client", "version": "0.104.0"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "verify_flag_candidate", "arguments": {"flag": "flag{ok}"}},
        },
    ]

    payload = b"".join(
        json.dumps(request, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        for request in requests
    )

    process = subprocess.Popen(
        [sys.executable, str(module_path), "--spec", str(spec_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate(input=payload, timeout=5)

    assert process.returncode == 0
    assert stderr == b""

    responses = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    assert len(responses) == 3
    assert responses[0]["id"] == 1
    assert responses[0]["result"]["protocolVersion"] == "2025-06-18"
    assert responses[1]["id"] == 2
    assert responses[1]["result"]["tools"][0]["name"] == "verify_flag_candidate"
    assert responses[2]["id"] == 3
    assert responses[2]["result"]["structuredContent"]["method"] == "local_check"
    assert responses[2]["result"]["structuredContent"]["verified"] is True


def test_stdio_content_length_initialize_compatibility(tmp_path) -> None:
    module_path = Path(__file__).resolve().parents[2] / "images" / "ctf-agent-sandbox" / "flag_verify_mcp.py"
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "stop_criteria": {
                    "primary": {
                        "type": "FLAG_FOUND",
                        "config": {"regex": r"^flag\{.+\}$"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18"},
    }
    raw = json.dumps(initialize_request, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw

    process = subprocess.Popen(
        [sys.executable, str(module_path), "--spec", str(spec_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate(input=payload, timeout=5)

    assert process.returncode == 0
    assert stderr == b""
    assert stdout.startswith(b"Content-Length:")

    headers, body = stdout.split(b"\r\n\r\n", 1)
    length_value = None
    for header in headers.decode("ascii").splitlines():
        if header.lower().startswith("content-length:"):
            length_value = int(header.split(":", 1)[1].strip())
            break
    assert length_value is not None
    response = json.loads(body[:length_value].decode("utf-8"))
    assert response["id"] == 1
    assert response["result"]["protocolVersion"] == "2025-06-18"
