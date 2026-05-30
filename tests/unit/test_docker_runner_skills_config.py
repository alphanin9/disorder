from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from control_plane.app.orchestrator.docker_runner import DockerRunner


def _build_runner(settings: SimpleNamespace) -> DockerRunner:
    runner = DockerRunner.__new__(DockerRunner)
    runner.settings = settings
    runner._resolve_host_mount_path = lambda p: Path("/resolved/skills")
    return runner


def test_sandbox_codex_skills_mount_disabled_when_host_path_unset() -> None:
    settings = SimpleNamespace(sandbox_codex_skills_host_path=None)
    runner = _build_runner(settings)

    volumes = runner._sandbox_codex_skills_volumes()
    assert volumes == {}


def test_sandbox_codex_skills_mount_enabled_when_host_path_set() -> None:
    settings = SimpleNamespace(sandbox_codex_skills_host_path="/host/codex-skills")
    runner = _build_runner(settings)

    volumes = runner._sandbox_codex_skills_volumes()
    assert len(volumes) == 1
    volume_spec = next(iter(volumes.values()))
    assert volume_spec == {"bind": "/workspace/run/.skill_seed/codex/skills", "mode": "ro"}
