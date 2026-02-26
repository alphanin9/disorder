from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import typer

app = typer.Typer(help="CTF harness CLI")
runs_app = typer.Typer(help="Run workflows")
app.add_typer(runs_app, name="runs")
CONFIG_PATH = Path.home() / ".ctf-harness" / "config.json"
FINAL_STATUSES = {"flag_found", "deliverable_produced", "blocked", "timeout"}
CONTINUATION_TYPES = {"hint", "deliverable_fix", "strategy_change", "other"}


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _api_request(method: str, url: str, path: str, payload: dict | None = None) -> dict:
    response = httpx.request(method, f"{url.rstrip('/')}{path}", json=payload, timeout=120.0)
    if response.status_code >= 400:
        raise typer.BadParameter(f"API error {response.status_code}: {response.text}")
    if response.text:
        return response.json()
    return {}


def _resolve_api_url(api_url: str | None) -> str:
    config = _load_config()
    return api_url or config.get("api_url") or "http://localhost:8000"


def _stream_logs_until_complete(resolved_api: str, run_id: str, poll_seconds: float) -> str:
    offset = 0
    while True:
        logs = _api_request("GET", resolved_api, f"/runs/{run_id}/logs?offset={offset}&limit=65536")
        chunk = logs.get("logs", "")
        if chunk:
            typer.echo(chunk, nl=False)
        offset = int(logs.get("next_offset", offset))

        run_status = _api_request("GET", resolved_api, f"/runs/{run_id}")
        status = run_status["run"]["status"]
        if status in FINAL_STATUSES and logs.get("eof"):
            typer.echo(f"\nRun completed with status={status}")
            return status

        time.sleep(poll_seconds)


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise typer.BadParameter(f"File not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"JSON root must be an object in {path}")
    return payload


@app.command("configure")
def configure(
    ctfd_url: str = typer.Option(..., "--ctfd-url", help="CTFd base URL"),
    token: str = typer.Option(..., "--token", help="CTFd API token"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="Control plane URL"),
) -> None:
    config = _load_config()
    config.update({"ctfd_url": ctfd_url, "token": token, "api_url": api_url})
    _save_config(config)
    typer.echo(f"Saved config to {CONFIG_PATH}")


@app.command("sync")
def sync(
    ctfd_url: str | None = typer.Option(None, "--ctfd-url", help="CTFd base URL"),
    token: str | None = typer.Option(None, "--token", help="CTFd API token"),
    api_url: str | None = typer.Option(None, "--api-url", help="Control plane URL"),
) -> None:
    config = _load_config()
    resolved_api = _resolve_api_url(api_url)
    payload = {
        "base_url": ctfd_url or config.get("ctfd_url"),
        "api_token": token or config.get("token"),
    }
    data = _api_request("POST", resolved_api, "/integrations/ctfd/sync", payload)
    typer.echo(json.dumps(data, indent=2))


@app.command("list")
def list_challenges(api_url: str | None = typer.Option(None, "--api-url", help="Control plane URL")) -> None:
    resolved_api = _resolve_api_url(api_url)
    data = _api_request("GET", resolved_api, "/challenges")
    for item in data.get("items", []):
        typer.echo(f"{item['id']} | {item['name']} | {item['category']} | {item['points']}")


@app.command("show")
def show_challenge(challenge_id: str, api_url: str | None = typer.Option(None, "--api-url", help="Control plane URL")) -> None:
    resolved_api = _resolve_api_url(api_url)
    data = _api_request("GET", resolved_api, f"/challenges/{challenge_id}")
    typer.echo(json.dumps(data, indent=2))


@app.command("run")
def run_challenge(
    challenge_id: str = typer.Option(..., "--challenge-id", help="Challenge UUID from /challenges"),
    backend: str = typer.Option("mock", "--backend", help="mock|codex|claude_code"),
    local_deploy: bool = typer.Option(False, "--local-deploy", help="Enable local docker compose deploy if present"),
    host_dirs: list[str] | None = typer.Option(
        None,
        "--host-dir",
        help="Host directory passthrough (repeatable, mounted read-only under /workspace/chal/_host/*; server must enable feature)",
    ),
    api_url: str | None = typer.Option(None, "--api-url", help="Control plane URL"),
    stream_logs: bool = typer.Option(True, "--stream-logs/--no-stream-logs", help="Stream logs until run completes"),
    poll_seconds: float = typer.Option(1.0, "--poll-seconds", min=0.2, max=10.0),
) -> None:
    resolved_api = _resolve_api_url(api_url)
    payload = {
        "challenge_id": challenge_id,
        "backend": backend,
        "local_deploy_enabled": local_deploy,
    }
    if host_dirs:
        payload["host_passthroughs"] = [{"host_path": host_dir} for host_dir in host_dirs if host_dir.strip()]
    run = _api_request("POST", resolved_api, "/runs", payload)
    run_id = run["id"]
    typer.echo(f"Started run {run_id} with backend={backend}")

    if not stream_logs:
        return

    _stream_logs_until_complete(resolved_api=resolved_api, run_id=run_id, poll_seconds=poll_seconds)

    result_payload = _api_request("GET", resolved_api, f"/runs/{run_id}/result")
    typer.echo(json.dumps(result_payload, indent=2))


@runs_app.command("continue")
def continue_existing_run(
    parent_run_id: str = typer.Argument(..., help="Parent run UUID"),
    message: str = typer.Option(..., "--message", help="Operator continuation guidance"),
    continuation_type: str | None = typer.Option(None, "--type", help="hint|deliverable_fix|strategy_change|other"),
    time_limit_seconds: int | None = typer.Option(None, "--time-limit-seconds", min=60, max=24 * 60 * 60),
    stop_criteria_file: Path | None = typer.Option(None, "--stop-criteria-file", help="JSON file with stop criteria override object"),
    reuse_parent_artifacts: bool = typer.Option(True, "--reuse-parent-artifacts/--no-reuse-parent-artifacts"),
    api_url: str | None = typer.Option(None, "--api-url", help="Control plane URL"),
    stream_logs: bool = typer.Option(True, "--stream-logs/--no-stream-logs", help="Stream logs until run completes"),
    poll_seconds: float = typer.Option(1.0, "--poll-seconds", min=0.2, max=10.0),
) -> None:
    if continuation_type is not None and continuation_type not in CONTINUATION_TYPES:
        allowed = ", ".join(sorted(CONTINUATION_TYPES))
        raise typer.BadParameter(f"--type must be one of: {allowed}")

    resolved_api = _resolve_api_url(api_url)
    payload: dict[str, Any] = {
        "message": message,
        "reuse_parent_artifacts": reuse_parent_artifacts,
    }
    if continuation_type is not None:
        payload["type"] = continuation_type
    if time_limit_seconds is not None:
        payload["time_limit_seconds"] = time_limit_seconds
    if stop_criteria_file is not None:
        payload["stop_criteria_override"] = _load_json_file(stop_criteria_file)

    run = _api_request("POST", resolved_api, f"/runs/{parent_run_id}/continue", payload)
    run_id = run["id"]
    typer.echo(f"Started continuation run {run_id} (parent={parent_run_id})")

    if not stream_logs:
        return

    _stream_logs_until_complete(resolved_api=resolved_api, run_id=run_id, poll_seconds=poll_seconds)
    result_payload = _api_request("GET", resolved_api, f"/runs/{run_id}/result")
    typer.echo(json.dumps(result_payload, indent=2))


@app.command("logs")
def logs(
    run_id: str,
    api_url: str | None = typer.Option(None, "--api-url", help="Control plane URL"),
    follow: bool = typer.Option(True, "--follow/--no-follow"),
    poll_seconds: float = typer.Option(1.0, "--poll-seconds", min=0.2, max=10.0),
) -> None:
    resolved_api = _resolve_api_url(api_url)
    offset = 0
    while True:
        payload = _api_request("GET", resolved_api, f"/runs/{run_id}/logs?offset={offset}&limit=65536")
        if payload.get("logs"):
            typer.echo(payload["logs"], nl=False)
        offset = int(payload.get("next_offset", offset))

        if not follow:
            break

        run_status = _api_request("GET", resolved_api, f"/runs/{run_id}")
        status = run_status["run"]["status"]
        if status in FINAL_STATUSES and payload.get("eof"):
            break
        time.sleep(poll_seconds)


@app.command("result")
def result(run_id: str, api_url: str | None = typer.Option(None, "--api-url", help="Control plane URL")) -> None:
    resolved_api = _resolve_api_url(api_url)
    payload = _api_request("GET", resolved_api, f"/runs/{run_id}/result")
    typer.echo(json.dumps(payload, indent=2))


@app.command("health")
def health(api_url: str | None = typer.Option(None, "--api-url", help="Control plane URL")) -> None:
    resolved_api = _resolve_api_url(api_url)
    response = httpx.get(f"{resolved_api.rstrip('/')}/healthz", timeout=10.0)
    response.raise_for_status()
    typer.echo(response.text)


if __name__ == "__main__":
    app()
