# Architecture (MVP)

## Components
- `control_plane` (FastAPI): integration sync, manifests, run lifecycle, orchestration kickoff.
- `frontend` (React + Vite): operator web console for challenge selection, run start, live logs, and result viewing.
- `postgres`: source of truth for challenge manifests, run specs, run result metadata.
- `minio`: object storage for challenge artifacts, run results, logs, deliverables.
- `auth store` (in `integration_configs`): encrypted, tagged Codex auth files for browser upload + sandbox staging.
- `sandbox` container (`ctf-agent-sandbox:latest`): executes one RunSpec with backend `mock|codex|claude_code`.
  - Includes baseline CTF tooling (`pwntools`, `gdb`, `binutils`, `strace`, `socat`, `z3-solver`, etc.) and Codex CLI.
- `cli`: Typer client for sync/list/run/log/result workflows.

## Data flow
1. `POST /integrations/ctfd/sync` pulls challenges/files from CTFd.
2. Manifests are upserted into Postgres; files are uploaded to MinIO.
3. `POST /runs` stores RunSpec-like fields in `runs`, then launches Docker orchestration thread.
4. Orchestrator hydrates artifacts into `runs/<run_id>/chal`, writes `runs/<run_id>/run/spec.json`, starts sandbox.
   - Challenge artifacts are mounted read-only at `/workspace/chal`.
   - Run workspace is mounted read-write at `/workspace/run`.
   - Selected env vars and optional uploaded-tagged Codex auth mount are passed into sandbox.
   - Orchestrator stages the active auth tag from encrypted store into an ephemeral per-run directory and mounts it read-only to `/home/ctf/.codex`.
   - Default Codex command registers a local MCP server (`verify_flag_candidate`) for regex/local-check flag verification during run execution.
5. Sandbox writes `result.json` + `README.md` (+ deliverables) in `/workspace/run`.
6. Control plane validates result, evaluates stop criteria, archives outputs to MinIO, updates `run_results` + run status.
7. Frontend polls run status/log endpoints and renders auditable results for operators.

## Extensibility for Kubernetes
- Core run models (`runs`, `run_results`, RunSpec payload) are runner-agnostic.
- Orchestration boundary is isolated in `control_plane/app/orchestrator/docker_runner.py`.
- A future `k8s_runner.py` can implement the same launch/collect contract without changing DB or API schemas.
