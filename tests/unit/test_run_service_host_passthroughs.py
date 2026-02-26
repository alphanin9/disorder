from __future__ import annotations

from types import SimpleNamespace

import pytest

from control_plane.app.schemas.run import RunCreateRequest
from control_plane.app.services.run_service import RunCreateError, _clone_host_passthroughs, _resolve_host_passthroughs_for_run


def _request(host_passthroughs: list[dict]) -> RunCreateRequest:
    return RunCreateRequest.model_validate(
        {
            "challenge_id": "11111111-1111-1111-1111-111111111111",
            "backend": "codex",
            "local_deploy_enabled": False,
            "host_passthroughs": host_passthroughs,
        }
    )


def test_resolve_host_passthroughs_for_run_normalizes_names_and_mount_paths() -> None:
    settings = SimpleNamespace(
        sandbox_host_passthrough_enabled=True,
        sandbox_host_passthrough_mount_root="/workspace/chal/_host",
        sandbox_host_passthrough_max_dirs=4,
    )
    request = _request(
        [
            {"host_path": r"G:\Forensics Cases\Case 1", "name": "Case 1"},
            {"host_path": r"G:\Forensics Cases\Case 1", "name": "Case 1"},
            {"host_path": "/mnt/data/disk image"},
        ]
    )

    resolved = _resolve_host_passthroughs_for_run(request, settings)
    assert [item["name"] for item in resolved] == ["case-1", "case-1-2", "disk-image"]
    assert all(item["mode"] == "ro" for item in resolved)
    assert all(item["mount_path"].startswith("/workspace/chal/_host/") for item in resolved)


def test_resolve_host_passthroughs_for_run_rejects_when_disabled() -> None:
    settings = SimpleNamespace(
        sandbox_host_passthrough_enabled=False,
        sandbox_host_passthrough_mount_root="/workspace/chal/_host",
        sandbox_host_passthrough_max_dirs=4,
    )
    request = _request([{"host_path": r"G:\case"}])

    with pytest.raises(RunCreateError, match="disabled") as exc_info:
        _resolve_host_passthroughs_for_run(request, settings)
    assert exc_info.value.status_code == 403


def test_resolve_host_passthroughs_for_run_rejects_when_exceeding_max_dirs() -> None:
    settings = SimpleNamespace(
        sandbox_host_passthrough_enabled=True,
        sandbox_host_passthrough_mount_root="/workspace/chal/_host",
        sandbox_host_passthrough_max_dirs=1,
    )
    request = _request([{"host_path": "/a"}, {"host_path": "/b"}])

    with pytest.raises(RunCreateError, match="max=1") as exc_info:
        _resolve_host_passthroughs_for_run(request, settings)
    assert exc_info.value.status_code == 422


def test_clone_host_passthroughs_filters_invalid_entries() -> None:
    cloned = _clone_host_passthroughs(
        {
            "host_passthroughs": [
                {"name": "ok", "host_path": "/a", "mount_path": "/workspace/chal/_host/ok", "mode": "ro"},
                {"name": "missing-host", "mount_path": "/workspace/chal/_host/x"},
                "not-an-object",
            ]
        }
    )
    assert cloned == [{"name": "ok", "host_path": "/a", "mount_path": "/workspace/chal/_host/ok", "mode": "ro"}]

