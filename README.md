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

## Tests
- Unit tests: `python -m pytest -q tests/unit`
- Integration smoke (requires running stack):
  - `RUN_SMOKE=1 python -m pytest -q tests/integration/test_smoke_mock_run.py`
- Frontend unit tests:
  - `npm --prefix frontend run test:run`
- Frontend e2e smoke (requires running stack):
  - `npm --prefix frontend run test:e2e`
