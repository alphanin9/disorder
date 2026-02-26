from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "images" / "ctf-agent-sandbox" / "flag_submit_mcp.py"
    spec = importlib.util.spec_from_file_location("flag_submit_mcp_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load flag_submit_mcp module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_submit_flag_via_control_plane_posts_run_scoped_request(monkeypatch) -> None:
    module = _load_module()
    seen: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "run_id": "11111111-1111-1111-1111-111111111111",
                    "challenge_id": "22222222-2222-2222-2222-222222222222",
                    "flag_verification": {"method": "platform_submit", "verified": True, "details": "ok"},
                }
            ).encode("utf-8")

    def _fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["body"] = request.data.decode("utf-8")
        seen["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setenv("DISORDER_CONTROL_PLANE_URL", "http://control-plane:8000")
    monkeypatch.setattr(module.urllib.request, "urlopen", _fake_urlopen)

    payload = module._submit_flag_via_control_plane({"run_id": "abc-run"}, "flag{demo}")
    assert seen["url"] == "http://control-plane:8000/runs/abc-run/submit-flag"
    assert json.loads(str(seen["body"])) == {"flag": "flag{demo}"}
    assert seen["timeout"] == 15.0
    headers = {str(k).lower(): str(v) for k, v in dict(seen["headers"]).items()}
    assert headers["content-type"] == "application/json"
    assert payload["flag_verification"]["method"] == "platform_submit"


def test_submit_flag_via_control_plane_uses_host_docker_internal_fallback(monkeypatch) -> None:
    module = _load_module()
    seen: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"flag_verification":{"method":"none","verified":false,"details":"ok"}}'

    def _fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.delenv("DISORDER_CONTROL_PLANE_URL", raising=False)
    monkeypatch.delenv("DISORDER_CONTROL_PLANE_PORT", raising=False)
    monkeypatch.setattr(module.urllib.request, "urlopen", _fake_urlopen)

    module._submit_flag_via_control_plane({"run_id": "abc-run"}, "flag{demo}")
    assert seen["url"] == "http://host.docker.internal:8000/runs/abc-run/submit-flag"


def test_tools_call_returns_error_when_control_plane_submit_fails(monkeypatch) -> None:
    module = _load_module()

    def _raise_submit(_spec, _flag):
        raise RuntimeError("submit failed")

    monkeypatch.setattr(module, "_submit_flag_via_control_plane", _raise_submit)

    response = module._handle_tools_call(
        7,
        {"params": {"name": "submit_flag_candidate", "arguments": {"flag": "flag{x}"}}},
        {"run_id": "abc"},
    )
    assert response["id"] == 7
    result = response["result"]
    assert result["isError"] is True
    assert "submit failed" in result["content"][0]["text"]


def test_tools_call_returns_structured_content_on_success(monkeypatch) -> None:
    module = _load_module()
    expected = {
        "run_id": "abc",
        "challenge_id": "def",
        "flag_verification": {"method": "platform_submit", "verified": False, "details": "incorrect"},
    }
    monkeypatch.setattr(module, "_submit_flag_via_control_plane", lambda _spec, _flag: expected)

    response = module._handle_tools_call(
        8,
        {"params": {"name": "submit_flag_candidate", "arguments": {"flag": "flag{bad}"}}},
        {"run_id": "abc"},
    )
    assert response["id"] == 8
    result = response["result"]
    assert result["structuredContent"] == expected
    assert json.loads(result["content"][0]["text"]) == expected
