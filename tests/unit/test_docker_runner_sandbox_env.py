from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from control_plane.app.orchestrator.docker_runner import DockerRunner


def _build_runner(settings: SimpleNamespace) -> DockerRunner:
    runner = DockerRunner.__new__(DockerRunner)
    runner.settings = settings
    return runner


def test_sandbox_environment_sets_flag_submit_mcp_and_control_plane_url() -> None:
    settings = SimpleNamespace(
        sandbox_env_passthrough="",
        app_port=8000,
        sandbox_control_plane_url="http://control-plane:8000/",
        sandbox_flag_submit_mcp_enabled=True,
    )
    runner = _build_runner(settings)

    env = runner._sandbox_environment()
    assert env["DISORDER_CONTROL_PLANE_URL"] == "http://control-plane:8000"
    assert env["CODEX_FLAG_SUBMIT_MCP_ENABLED"] == "1"


def test_sandbox_environment_defaults_control_plane_host_docker_internal() -> None:
    settings = SimpleNamespace(
        sandbox_env_passthrough="",
        app_port=8123,
        sandbox_control_plane_url=None,
        sandbox_flag_submit_mcp_enabled=False,
    )
    runner = _build_runner(settings)

    env = runner._sandbox_environment()
    assert env["DISORDER_CONTROL_PLANE_URL"] == "http://host.docker.internal:8123"
    assert env["CODEX_FLAG_SUBMIT_MCP_ENABLED"] == "0"


def test_sandbox_environment_auto_enables_flag_submit_for_ctfd_integrated_ctf() -> None:
    settings = SimpleNamespace(
        sandbox_env_passthrough="",
        app_port=8000,
        sandbox_control_plane_url=None,
        sandbox_flag_submit_mcp_enabled=False,
    )
    runner = _build_runner(settings)
    runner._ctf_has_ctfd_integration = lambda _db, _ctf_id: True

    challenge = SimpleNamespace(id=uuid4(), ctf_id=uuid4())
    env = runner._sandbox_environment(db=object(), challenge=challenge)
    assert env["CODEX_FLAG_SUBMIT_MCP_ENABLED"] == "1"
