# AGENTS.md

Guidance for agents working in this repository.

## Repository purpose
`disorder` is an agentic harness for Jeopardy-style CTF automation:
- **Control plane** (`control_plane/`): FastAPI API, orchestration, persistence, integration sync.
- **Sandbox image** (`images/ctf-agent-sandbox/`): Docker image + runtime entrypoint that executes one run.
- **Frontend** (`frontend/`): React/Vite operator console.
- **CLI** (`cli/`): Typer client for sync/list/run/log workflows.

## Architecture quick map
- Start from `docs/architecture.md` and `docs/API.md`.
- Main backend entrypoint: `control_plane/app/main.py`.
- API routing: `control_plane/app/api/router.py` and `control_plane/app/api/routes/*.py`.
- Run orchestration boundary: `control_plane/app/orchestrator/docker_runner.py`.
- Sandbox runner contract: `images/ctf-agent-sandbox/agent_runner.py` writes `/workspace/run/result.json` and `/workspace/run/README.md`.
- Result schema/validation: `control_plane/app/schemas/result_contract.py`.

## High-impact implementation rules
1. **Preserve sandbox result contract.**
   - Any backend/tool changes must still produce contract-compliant `result.json` and `README.md`.
2. **Keep orchestrator runner-agnostic.**
   - Docker-specific logic belongs in `docker_runner.py`; keep DB/API schemas generic.
3. **Respect mount and trust boundaries.**
   - Challenge artifacts mounted read-only at `/workspace/chal`.
   - Writable state/output only under `/workspace/run`.
4. **Prefer configuration via settings/env.**
   - New toggles should flow through `control_plane/app/core/config.py` and env vars.
5. **Security-first defaults.**
   - Disable risky capabilities by default; require explicit opt-in and document the risk.

## Working conventions
- Python: 3.11+, type hints, Pydantic v2 models, SQLAlchemy 2 style.
- Frontend: TypeScript + React Query; generated API types live in `frontend/src/api/`.
- Keep changes scoped/minimal; avoid broad refactors unless requested.
- Update docs when changing API behavior, run spec fields, or sandbox tooling.
- Add tests for behavioral changes in:
  - `tests/unit/` for control-plane/sandbox logic
  - `frontend/src/features/**/*.test.tsx` for UI behavior

## Validation commands (typical)
- Backend unit tests: `python -m pytest -q tests/unit`
- Full Python tests: `pytest -q`
- Frontend tests: `npm --prefix frontend run test:run`
- Frontend build: `npm --prefix frontend run build`

## Tooling-extension pointers
When adding new challenge-solving tools (e.g., SageMath, Ghidra):
- Sandbox packages/image: `images/ctf-agent-sandbox/Dockerfile`
- Runtime tool wiring/prompts: `images/ctf-agent-sandbox/agent_runner.py`, `agent_prompt.txt`, `ctf_tooling_guide.md`
- Environment passthrough controls: `control_plane/app/orchestrator/docker_runner.py` (`_sandbox_environment`)
- Optional stop criteria / evidence schema: `control_plane/app/schemas/result_contract.py`, `control_plane/app/stop_criteria/engine.py`

