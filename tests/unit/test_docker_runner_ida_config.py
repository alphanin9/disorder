from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from control_plane.app.orchestrator.docker_runner import DockerRunner


def _build_runner(settings: SimpleNamespace) -> DockerRunner:
    runner = DockerRunner.__new__(DockerRunner)
    runner.settings = settings
    runner._resolve_host_mount_path = lambda p: Path("/resolved/ida")
    return runner


def test_sandbox_ida_mount_and_env_disabled_when_host_path_unset() -> None:
    settings = SimpleNamespace(
        sandbox_ida_host_path=None,
        sandbox_ida_mount_path="/opt/ida",
        sandbox_idalib_mcp_port=8745,
    )
    runner = _build_runner(settings)

    volume, env = runner._sandbox_ida_mount_and_env()
    assert volume == {}
    assert env["SANDBOX_IDA_ENABLED"] == "0"


def test_sandbox_ida_mount_and_env_enabled_when_host_path_set() -> None:
    settings = SimpleNamespace(
        sandbox_ida_host_path="/host/ida",
        sandbox_ida_mount_path="/opt/ida",
        sandbox_idalib_mcp_port=8745,
    )
    runner = _build_runner(settings)

    volume, env = runner._sandbox_ida_mount_and_env()
    assert len(volume) == 1
    volume_spec = next(iter(volume.values()))
    assert volume_spec == {"bind": "/opt/ida", "mode": "ro"}
    assert env["SANDBOX_IDA_ENABLED"] == "1"
    assert env["SANDBOX_IDA_INSTALL_PATH"] == "/opt/ida"
    assert env["SANDBOX_IDALIB_MCP_PORT"] == "8745"
    assert env["IDADIR"] == "/opt/ida"
