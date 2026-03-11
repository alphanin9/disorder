from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from control_plane.app.orchestrator.docker_runner import DockerRunner


def test_sandbox_continuation_volume_mounts_existing_context_dir(tmp_path: Path) -> None:
    runner = DockerRunner.__new__(DockerRunner)
    runner.settings = SimpleNamespace(runs_dir=tmp_path)
    run = SimpleNamespace(
        id=uuid4(),
        paths={"continuation_mount": "/workspace/continuation"},
    )

    host_run_dir = tmp_path / "run"
    local_run_dir = tmp_path / str(run.id)
    (host_run_dir / "continuation").mkdir(parents=True)
    (local_run_dir / "continuation").mkdir(parents=True)

    volumes = runner._sandbox_continuation_volume(run=run, host_run_dir=host_run_dir)
    assert str(host_run_dir / "continuation") in volumes
    assert volumes[str(host_run_dir / "continuation")] == {"bind": "/workspace/continuation", "mode": "ro"}


def test_sandbox_continuation_volume_ignores_missing_context_dir(tmp_path: Path) -> None:
    runner = DockerRunner.__new__(DockerRunner)
    runner.settings = SimpleNamespace(runs_dir=tmp_path)
    run = SimpleNamespace(
        id=uuid4(),
        paths={"continuation_mount": "/workspace/continuation"},
    )

    host_run_dir = tmp_path / "run"
    host_run_dir.mkdir(parents=True)

    volumes = runner._sandbox_continuation_volume(run=run, host_run_dir=host_run_dir)
    assert volumes == {}


def test_sandbox_continuation_volume_allows_daemon_only_host_path_when_local_context_exists(tmp_path: Path) -> None:
    runner = DockerRunner.__new__(DockerRunner)
    runner.settings = SimpleNamespace(runs_dir=tmp_path)
    run = SimpleNamespace(
        id=uuid4(),
        paths={"continuation_mount": "/workspace/continuation"},
    )

    (tmp_path / str(run.id) / "continuation").mkdir(parents=True)
    daemon_only_host_run_dir = Path("/run/desktop/mnt/host/g/repo/runs") / str(run.id)

    volumes = runner._sandbox_continuation_volume(run=run, host_run_dir=daemon_only_host_run_dir)
    assert str(daemon_only_host_run_dir / "continuation") in volumes
    assert volumes[str(daemon_only_host_run_dir / "continuation")] == {
        "bind": "/workspace/continuation",
        "mode": "ro",
    }


def test_build_spec_payload_includes_continuation_metadata() -> None:
    runner = DockerRunner.__new__(DockerRunner)
    run = SimpleNamespace(
        id=uuid4(),
        challenge_id=uuid4(),
        backend="codex",
        agent_invocation={"model": "gpt-5.4", "extra_args": ["--search"], "env": {"CODEX_MODEL": "gpt-5.4"}},
        budgets={"reasoning_effort": "high", "max_minutes": 45},
        stop_criteria={"primary": {"type": "FLAG_FOUND", "config": {"regex": "flag\\{.*?\\}"}}},
        allowed_endpoints=[],
        paths={"chal_mount": "/workspace/chal", "run_mount": "/workspace/run", "continuation_mount": "/workspace/continuation"},
        local_deploy={"enabled": False, "network": None, "endpoints": []},
        parent_run_id=uuid4(),
        continuation_depth=2,
        continuation_input="operator hint",
        continuation_type="hint",
    )
    challenge = SimpleNamespace(
        name="Warmup",
        category="misc",
        points=50,
        description_md="Desc",
    )

    spec = runner._build_spec_payload(run=run, challenge=challenge)
    assert spec["continuation"]["is_continuation"] is True
    assert spec["continuation"]["type"] == "hint"
    assert spec["continuation"]["depth"] == 2
    assert spec["continuation"]["mount_path"] == "/workspace/continuation"
    assert spec["continuation"]["deliverables_mount_path"] == "/workspace/continuation/deliverables"
    assert spec["continuation"]["deliverables_manifest_path"] == "/workspace/continuation/deliverables_manifest.json"
    assert spec["agent_invocation"]["model"] == "gpt-5.4"


def test_build_finalization_metadata_prefers_structured_failure_reason() -> None:
    runner = DockerRunner.__new__(DockerRunner)

    metadata = runner._build_finalization_metadata(
        result_data={
            "notes": "quota issue",
            "failure_reason_code": "provider_quota_or_auth",
            "failure_reason_detail": "Codex quota exceeded",
        },
        status_code=2,
        timed_out=False,
        contract_valid=True,
        contract_failure_code="none",
        contract_failure_detail="",
        result_status_before_stop_eval="blocked",
        result_status_after_stop_eval="blocked",
    )

    assert metadata["failure_reason_code"] == "provider_quota_or_auth"
    assert metadata["failure_reason_detail"] == "Codex quota exceeded"
