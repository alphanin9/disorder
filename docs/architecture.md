# Architecture (MVP)

## Components
- `control_plane` (FastAPI): integration sync, manifests, run lifecycle, orchestration kickoff.
- `frontend` (React + Vite): operator web console for challenge selection, run start, live logs, and result viewing.
- `postgres`: source of truth for challenge manifests, run specs, run result metadata.
- `minio`: object storage for challenge artifacts, run results, logs, deliverables.
- `auth store` (in `integration_configs`): encrypted, tagged Codex auth files for browser upload + sandbox staging.
- `sandbox` container (`ctf-agent-sandbox:latest` by default, configurable build target): executes one RunSpec with backend `mock|codex|claude_code`.
  - Includes baseline CTF tooling (`pwntools`, `gdb`, `binutils`, `strace`, `socat`, `z3-solver`, `SageMath`, `SymPy`, `NumPy`, etc.) and Codex CLI.
  - CI smoke jobs may instead use the minimal `ci` target, which keeps the sandbox contract and mock backend path without the full tooling bundle.
- `cli`: Typer client for sync/list/run/log/result workflows.

## Data flow
1. `POST /integrations/ctfd/sync` pulls challenges/files from CTFd.
2. Manifests are upserted into Postgres; files are uploaded to MinIO.
3. `POST /runs` stores RunSpec-like fields in `runs`, then launches Docker orchestration thread.
   - `POST /runs/{run_id}/continue` creates a child run linked to the terminal parent run and stores operator continuation input plus optional invocation/policy overrides.
4. Orchestrator hydrates artifacts into `runs/<run_id>/chal`, writes `runs/<run_id>/run/spec.json`, starts sandbox.
   - Challenge artifacts are mounted read-only at `/workspace/chal`.
   - Run workspace is mounted read-write at `/workspace/run`.
   - For continuation runs with artifact reuse enabled, control plane writes a read-only continuation bundle at `runs/<child_run_id>/continuation`:
     - `parent_result.json`
     - `parent_readme.md`
     - `continuation_request.json`
     - `deliverables_manifest.json`
     - `deliverables/<declared parent deliverables>`
   - Docker runner mounts that bundle read-only into the sandbox (`/workspace/continuation` by default).
   - Selected env vars and optional uploaded-tagged Codex auth mount are passed into sandbox.
   - Orchestrator stages the active auth tag from encrypted store into an ephemeral per-run directory and mounts it read-only as seed material; sandbox startup copies it into writable `CODEX_HOME`.
   - If `SANDBOX_CODEX_SKILLS_HOST_PATH` is configured, orchestrator mounts that directory read-only into the run and sandbox startup copies all seeded skill files into writable `CODEX_HOME/skills`.
   - Default Codex command registers a local MCP server (`verify_flag_candidate`) for regex/local-check flag verification during run execution.
   - If `SANDBOX_IDA_HOST_PATH` is configured, orchestrator mounts IDA read-only, exports `IDADIR`, optionally mounts `/home/ctf/.idapro` for persistent registry state, and sandbox startup auto-accepts configured EULA keys before launching `uv run idalib-mcp` and registering it as an HTTP MCP server for Codex.
5. Sandbox writes `result.json` + `README.md` (+ deliverables) in `/workspace/run`.
6. Control plane validates result, evaluates stop criteria, archives outputs to MinIO, updates `run_results` + run status.
   - `run_results.finalization_metadata` captures normalized completion metadata (`contract_valid`, sandbox exit code, normalized failure reason code, timeout flag, stop-eval status transition).
   - Auto-continuation policy evaluation runs after terminal result persistence; matching runs queue a child continuation linked to the immediate parent.
7. Frontend polls run status/log endpoints and renders auditable results for operators.
   - Run detail includes lineage view (parent run + child runs), effective auto-continuation policy, and continuation creation workflow.

## Extensibility for Kubernetes
- Core run models (`runs`, `run_results`, RunSpec payload) are runner-agnostic.
- Orchestration boundary is isolated in `control_plane/app/orchestrator/docker_runner.py`.
- A future `k8s_runner.py` can implement the same launch/collect contract without changing DB or API schemas.
