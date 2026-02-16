# Disorder Jeopardy CTF Harness (MVP)

Docker-first Python monorepo for running Jeopardy-style CTF agent runs in isolated sandboxes.

## Stack
- Python 3.11+
- FastAPI + Pydantic v2
- Postgres + SQLAlchemy 2.0 + Alembic
- MinIO (S3-compatible) via boto3
- Typer CLI
- Docker SDK for Python orchestration

## Repo layout
- `control_plane/` FastAPI control plane, DB models/migrations, CTFd adapter, orchestrator
- `cli/` Typer CLI (`python -m cli ...`)
- `frontend/` React + Vite operator console
- `images/ctf-agent-sandbox/` sandbox image + `agent_runner.py`
- `docs/` architecture, threat model, API
- `tests/` unit + integration smoke

## Quickstart
1. Start infra + control plane:
   - `docker compose up -d --build`
   - Frontend is available at `http://localhost:3000`
2. Optional CTFd sync:
   - `python -m cli configure --ctfd-url https://ctfd.example --token <token>`
   - `python -m cli sync`
3. List challenges:
   - `python -m cli list`
4. Start run:
   - `python -m cli run --challenge-id <uuid> --backend mock`
5. Inspect outputs:
   - `python -m cli logs <run_id>`
   - `python -m cli result <run_id>`
6. One-command demo flow (seed + run + print result):
   - `make demo`

## Environment notes
- Control plane stores run directories under `./runs/` by default.
- In Docker mode, set `DOCKER_BIND_RUNS_DIR` if `${PWD}/runs` does not resolve correctly on your host.
- Local deploy (`docker compose` inside challenge artifacts) requires Docker CLI availability in control-plane runtime.
- For Codex backend runs, provide auth using either:
  - `OPENAI_API_KEY` (or `CODEX_API_KEY`) in control plane environment, or
  - upload tagged auth files from the web UI (`CTFs` page) or API (`/auth/codex/*`).
- Uploaded auth files are mounted read-only as seed material and copied into writable `CODEX_HOME` at sandbox startup.
- Sandbox env passthrough is controlled by `SANDBOX_ENV_PASSTHROUGH`.
- Optional: set `CODEX_AUTH_ENCRYPTION_KEY` (Fernet key) for explicit auth-secret encryption key control.
- Codex runs include a local MCP tool `verify_flag_candidate` by default (toggle with `CODEX_FLAG_VERIFY_MCP_ENABLED=0` in `SANDBOX_ENV_PASSTHROUGH`/env).
- Optional IDA MCP support for reverse engineering:
  - Set `SANDBOX_IDA_HOST_PATH` to a Linux IDA installation path visible to the Docker daemon.
  - Optionally set `SANDBOX_IDA_MOUNT_PATH` (default `/opt/ida`) and `SANDBOX_IDALIB_MCP_PORT` (default `8745`).
  - Optional persistence for accepted EULA/registry state: set `SANDBOX_IDA_REGISTRY_HOST_PATH` to mount `/home/ctf/.idapro` read-write.
  - EULA acceptance is handled automatically when IDA is enabled (`SANDBOX_IDA_ACCEPT_EULA=true` by default); version keys are configurable via `SANDBOX_IDA_EULA_VERSIONS`.
  - Sandbox image installs `ida-pro-mcp` from `https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip` plus `idapro`.
  - When enabled, sandbox exports `IDADIR` to the mounted IDA path.
  - If `SANDBOX_IDA_HOST_PATH` is empty, IDA MCP is not exposed to the sandbox agent.
  - When enabled, sandbox startup launches `uv run idalib-mcp` and registers it with Codex MCP as an HTTP server.
- Default Codex invocation uses `codex exec --json` so live logs can stream JSONL events; set `CODEX_JSONL_LIVE_LOG_ONLY=0` to also stream Codex stderr live.
- Optional Discord notifications for `flag_found` runs:
  - `DISCORD_WEBHOOK_URL`
  - `DISCORD_NOTIFY_ON_FLAG=true|false`
  - `DISCORD_NOTIFY_INCLUDE_FLAG=true|false`

## Tests
- Unit tests: `python -m pytest -q tests/unit`
- Integration smoke (requires running stack):
  - `RUN_SMOKE=1 python -m pytest -q tests/integration/test_smoke_mock_run.py`
- Frontend unit tests:
  - `npm --prefix frontend run test:run`
- Frontend e2e smoke (requires running stack):
  - `npm --prefix frontend run test:e2e`
