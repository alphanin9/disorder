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
RUN_FINAL_STATUSES = {"flag_found", "deliverable_produced", "blocked", "timeout"}


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


def _csv_values(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _build_agent_invocation_payload(
    *,
    model: str | None,
    profile: str | None,
    agent_args: list[str],
    agent_env: list[str],
    invocation_file: Path | None,
) -> dict[str, Any] | None:
    payload = _load_json_file(invocation_file) if invocation_file is not None else {}
    if model:
        payload["model"] = model
    if profile:
        payload["profile"] = profile
    if agent_args:
        payload["extra_args"] = list(agent_args)
    if agent_env:
        env_payload = dict(payload.get("env") or {})
        for entry in agent_env:
            if "=" not in entry:
                raise typer.BadParameter(f"--agent-env must be KEY=VALUE, got: {entry}")
            key, value = entry.split("=", 1)
            key = key.strip()
            if not key:
                raise typer.BadParameter(f"--agent-env must include a non-empty key: {entry}")
            env_payload[key] = value
        payload["env"] = env_payload
    return payload or None


def _build_auto_continuation_policy_payload(
    *,
    target_status: str | None,
    max_depth: int | None,
    statuses: str | None,
    reason_codes: list[str],
    message_template: str | None,
    policy_file: Path | None,
    disable: bool,
) -> dict[str, Any] | None:
    payload = _load_json_file(policy_file) if policy_file is not None else {}
    if disable:
        payload["enabled"] = False
    if target_status is not None:
        if target_status not in RUN_FINAL_STATUSES:
            allowed = ", ".join(sorted(RUN_FINAL_STATUSES))
            raise typer.BadParameter(f"--auto-continue-until must be one of: {allowed}")
        payload.setdefault("target", {})
        payload["target"]["final_status"] = target_status
    if max_depth is not None:
        payload["max_depth"] = max_depth
    parsed_statuses = _csv_values(statuses)
    if parsed_statuses:
        for entry in parsed_statuses:
            if entry not in RUN_FINAL_STATUSES:
                allowed = ", ".join(sorted(RUN_FINAL_STATUSES))
                raise typer.BadParameter(f"--auto-continue-on entries must be one of: {allowed}")
        payload.setdefault("when", {})
        payload["when"]["statuses"] = parsed_statuses
    if reason_codes:
        payload["on_blocked_reasons"] = reason_codes
    if message_template:
        payload["message_template"] = message_template
    return payload or None


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
    model: str | None = typer.Option(None, "--model", help="Backend model override"),
    profile: str | None = typer.Option(None, "--profile", help="Backend profile override"),
    agent_arg: list[str] = typer.Option([], "--agent-arg", help="Extra backend argument; repeat for multiple values"),
    agent_env: list[str] = typer.Option([], "--agent-env", help="Backend env override in KEY=VALUE form"),
    agent_invocation_file: Path | None = typer.Option(None, "--agent-invocation-file", help="JSON file for agent invocation"),
    auto_continue_until: str | None = typer.Option(None, "--auto-continue-until", help="Terminal target status"),
    auto_continue_max_depth: int | None = typer.Option(None, "--auto-continue-max-depth", min=1, max=20),
    auto_continue_on: str | None = typer.Option(None, "--auto-continue-on", help="Comma-separated statuses to retry"),
    auto_continue_reason: list[str] = typer.Option([], "--auto-continue-reason", help="Failure reason code filter; repeatable"),
    auto_continue_message_template: str | None = typer.Option(None, "--auto-continue-message-template"),
    auto_continuation_policy_file: Path | None = typer.Option(None, "--auto-continuation-policy-file", help="JSON file for auto continuation policy"),
    disable_auto_continue: bool = typer.Option(False, "--disable-auto-continue", help="Explicitly disable auto continuation for this run"),
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
    agent_invocation_payload = _build_agent_invocation_payload(
        model=model,
        profile=profile,
        agent_args=agent_arg,
        agent_env=agent_env,
        invocation_file=agent_invocation_file,
    )
    if agent_invocation_payload is not None:
        payload["agent_invocation"] = agent_invocation_payload
    auto_policy_payload = _build_auto_continuation_policy_payload(
        target_status=auto_continue_until,
        max_depth=auto_continue_max_depth,
        statuses=auto_continue_on,
        reason_codes=auto_continue_reason,
        message_template=auto_continue_message_template,
        policy_file=auto_continuation_policy_file,
        disable=disable_auto_continue,
    )
    if auto_policy_payload is not None:
        payload["auto_continuation_policy"] = auto_policy_payload
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
    model: str | None = typer.Option(None, "--model", help="Backend model override for the child run"),
    profile: str | None = typer.Option(None, "--profile", help="Backend profile override for the child run"),
    agent_arg: list[str] = typer.Option([], "--agent-arg", help="Extra backend argument; repeat for multiple values"),
    agent_env: list[str] = typer.Option([], "--agent-env", help="Backend env override in KEY=VALUE form"),
    agent_invocation_file: Path | None = typer.Option(None, "--agent-invocation-file", help="JSON file for agent invocation override"),
    auto_continue_until: str | None = typer.Option(None, "--auto-continue-until", help="Terminal target status"),
    auto_continue_max_depth: int | None = typer.Option(None, "--auto-continue-max-depth", min=1, max=20),
    auto_continue_on: str | None = typer.Option(None, "--auto-continue-on", help="Comma-separated statuses to retry"),
    auto_continue_reason: list[str] = typer.Option([], "--auto-continue-reason", help="Failure reason code filter; repeatable"),
    auto_continue_message_template: str | None = typer.Option(None, "--auto-continue-message-template"),
    auto_continuation_policy_file: Path | None = typer.Option(None, "--auto-continuation-policy-file", help="JSON file for auto continuation policy override"),
    disable_auto_continue: bool = typer.Option(False, "--disable-auto-continue", help="Disable inherited auto continuation on the child run"),
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
    agent_invocation_payload = _build_agent_invocation_payload(
        model=model,
        profile=profile,
        agent_args=agent_arg,
        agent_env=agent_env,
        invocation_file=agent_invocation_file,
    )
    if agent_invocation_payload is not None:
        payload["agent_invocation_override"] = agent_invocation_payload
    auto_policy_payload = _build_auto_continuation_policy_payload(
        target_status=auto_continue_until,
        max_depth=auto_continue_max_depth,
        statuses=auto_continue_on,
        reason_codes=auto_continue_reason,
        message_template=auto_continue_message_template,
        policy_file=auto_continuation_policy_file,
        disable=disable_auto_continue,
    )
    if auto_policy_payload is not None:
        payload["auto_continuation_policy_override"] = auto_policy_payload

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
