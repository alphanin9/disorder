from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from control_plane.app.orchestrator.docker_runner import DockerRunner


def test_sandbox_host_passthrough_volumes_disabled_when_none_present() -> None:
    runner = DockerRunner.__new__(DockerRunner)
    run = SimpleNamespace(id=uuid4(), paths={"chal_mount": "/workspace/chal", "run_mount": "/workspace/run"})

    volumes = runner._sandbox_host_passthrough_volumes(run=run)
    assert volumes == {}


def test_sandbox_host_passthrough_volumes_mounts_read_only_entries() -> None:
    runner = DockerRunner.__new__(DockerRunner)
    runner._resolve_host_mount_path = lambda p: Path("/resolved") / p.name  # type: ignore[method-assign]
    run = SimpleNamespace(
        id=uuid4(),
        paths={
            "host_passthroughs": [
                {
                    "name": "case1",
                    "host_path": r"G:\forensics\case1",
                    "mount_path": "/workspace/chal/_host/case1",
                    "mode": "ro",
                }
            ]
        },
    )

    volumes = runner._sandbox_host_passthrough_volumes(run=run)
    assert len(volumes) == 1
    host_mount, spec = next(iter(volumes.items()))
    assert host_mount.replace("\\", "/") == "/resolved/case1"
    assert spec == {"bind": "/workspace/chal/_host/case1", "mode": "ro"}


def test_paths_for_sandbox_spec_strips_raw_host_paths() -> None:
    runner = DockerRunner.__new__(DockerRunner)
    paths = {
        "chal_mount": "/workspace/chal",
        "run_mount": "/workspace/run",
        "host_passthroughs": [
            {
                "name": "case1",
                "host_path": r"G:\forensics\case1",
                "mount_path": "/workspace/chal/_host/case1",
                "mode": "ro",
            }
        ],
    }

    sanitized = runner._paths_for_sandbox_spec(paths)
    assert sanitized["chal_mount"] == "/workspace/chal"
    assert sanitized["run_mount"] == "/workspace/run"
    assert sanitized["host_passthroughs"] == [
        {"name": "case1", "mount_path": "/workspace/chal/_host/case1", "mode": "ro"}
    ]
    assert "host_path" not in sanitized["host_passthroughs"][0]


def test_build_spec_payload_includes_sanitized_host_passthroughs() -> None:
    runner = DockerRunner.__new__(DockerRunner)
    run = SimpleNamespace(
        id=uuid4(),
        challenge_id=uuid4(),
        backend="codex",
        budgets={"reasoning_effort": "high", "max_minutes": 30},
        stop_criteria={"primary": {"type": "FLAG_FOUND", "config": {}}},
        allowed_endpoints=[],
        paths={
            "chal_mount": "/workspace/chal",
            "run_mount": "/workspace/run",
            "host_passthroughs": [
                {
                    "name": "case1",
                    "host_path": r"G:\forensics\case1",
                    "mount_path": "/workspace/chal/_host/case1",
                    "mode": "ro",
                }
            ],
        },
        local_deploy={"enabled": False, "network": None, "endpoints": []},
        parent_run_id=None,
        continuation_depth=0,
        continuation_input=None,
        continuation_type=None,
    )
    challenge = SimpleNamespace(name="Warmup", category="forensics", points=100, description_md="desc")

    spec = runner._build_spec_payload(run=run, challenge=challenge)
    assert spec["paths"]["host_passthroughs"] == [
        {"name": "case1", "mount_path": "/workspace/chal/_host/case1", "mode": "ro"}
    ]
