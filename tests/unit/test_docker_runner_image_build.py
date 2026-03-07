from __future__ import annotations

from types import SimpleNamespace

from docker.errors import ImageNotFound

from control_plane.app.orchestrator.docker_runner import DockerRunner


class _FakeImages:
    def __init__(self, *, image_exists: bool) -> None:
        self.image_exists = image_exists
        self.build_calls: list[dict[str, object]] = []

    def get(self, _name: str) -> object:
        if self.image_exists:
            return object()
        raise ImageNotFound("missing")

    def build(self, **kwargs: object) -> None:
        self.build_calls.append(kwargs)


def _build_runner(settings: SimpleNamespace, images: _FakeImages) -> DockerRunner:
    runner = DockerRunner.__new__(DockerRunner)
    runner.settings = settings
    runner.client = SimpleNamespace(images=images)
    return runner


def test_ensure_sandbox_image_builds_selected_target(monkeypatch, tmp_path) -> None:
    images = _FakeImages(image_exists=False)
    settings = SimpleNamespace(
        sandbox_image="ctf-agent-sandbox-ci:latest",
        sandbox_build_target="ci",
    )
    runner = _build_runner(settings, images)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "images" / "ctf-agent-sandbox").mkdir(parents=True)

    runner._ensure_sandbox_image()

    assert images.build_calls == [
        {
            "path": "images\\ctf-agent-sandbox",
            "tag": "ctf-agent-sandbox-ci:latest",
            "rm": True,
            "target": "ci",
        }
    ]


def test_ensure_sandbox_image_omits_target_when_unset(monkeypatch, tmp_path) -> None:
    images = _FakeImages(image_exists=False)
    settings = SimpleNamespace(
        sandbox_image="ctf-agent-sandbox:latest",
        sandbox_build_target="",
    )
    runner = _build_runner(settings, images)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "images" / "ctf-agent-sandbox").mkdir(parents=True)

    runner._ensure_sandbox_image()

    assert images.build_calls == [
        {
            "path": "images\\ctf-agent-sandbox",
            "tag": "ctf-agent-sandbox:latest",
            "rm": True,
        }
    ]
