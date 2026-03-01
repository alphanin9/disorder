from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from control_plane.app.orchestrator.docker_runner import DockerRunner


def _build_runner(settings: SimpleNamespace) -> DockerRunner:
    runner = DockerRunner.__new__(DockerRunner)
    runner.settings = settings
    runner._resolve_host_mount_path = lambda p: Path("/resolved/ida")
    return runner


def _build_runner_with_mounts(mounts: list[dict[str, str]]) -> DockerRunner:
    runner = DockerRunner.__new__(DockerRunner)
    runner.settings = SimpleNamespace()

    class _FakeContainers:
        def __init__(self, data: list[dict[str, str]]) -> None:
            self._data = data

        def get(self, _container_id: str):
            return SimpleNamespace(attrs={"Mounts": self._data})

    runner.client = SimpleNamespace(containers=_FakeContainers(mounts))
    return runner


def test_sandbox_ida_mount_and_env_disabled_when_host_path_unset() -> None:
    settings = SimpleNamespace(
        sandbox_ida_host_path=None,
        sandbox_ida_mount_path="/opt/ida",
        sandbox_ida_registry_host_path=None,
        sandbox_ida_accept_eula=True,
        sandbox_ida_eula_versions="90,91,92,93",
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
        sandbox_ida_registry_host_path=None,
        sandbox_ida_accept_eula=True,
        sandbox_ida_eula_versions="90,91,92,93",
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
    assert env["SANDBOX_IDA_ACCEPT_EULA"] == "1"
    assert env["SANDBOX_IDA_EULA_VERSIONS"] == "90,91,92,93"
    assert env["IDADIR"] == "/opt/ida"


def test_sandbox_ida_mount_and_env_with_registry_volume() -> None:
    settings = SimpleNamespace(
        sandbox_ida_host_path="/host/ida",
        sandbox_ida_mount_path="/opt/ida",
        sandbox_ida_registry_host_path="/host/ida-registry",
        sandbox_ida_accept_eula=True,
        sandbox_ida_eula_versions="90,91,92,93",
        sandbox_idalib_mcp_port=8745,
    )
    runner = _build_runner(settings)
    runner._resolve_host_mount_path = lambda p: (
        Path("/resolved/ida-registry")
        if "registry" in str(p)
        else Path("/resolved/ida")
    )

    volume, env = runner._sandbox_ida_mount_and_env()
    assert len(volume) == 2
    assert {v["bind"] for v in volume.values()} == {"/opt/ida", "/home/ctf/.idapro"}
    assert any(
        v["mode"] == "rw" and v["bind"] == "/home/ctf/.idapro" for v in volume.values()
    )
    assert env["SANDBOX_IDA_ENABLED"] == "1"


def test_resolve_host_mount_path_translates_windows_style_path_on_posix() -> None:
    mounts = [
        {
            "Destination": "/data/runs",
            "Source": "/run/desktop/mnt/host/g/dev/disorder-jeopardy-ctf-harness/runs",
        }
    ]
    runner = _build_runner_with_mounts(mounts)
    translated = runner._translate_windows_host_path_for_daemon(
        target_raw=r"G:\dev\ida-pro-9.2-linux",
        mounts=mounts,
    )
    assert translated is not None
    assert translated.endswith("/run/desktop/mnt/host/g/dev/ida-pro-9.2-linux")
