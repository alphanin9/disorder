# API (MVP)

## Health
- `GET /healthz`

## Integrations
- `POST /integrations/ctfd/sync`
  - body:
    - session-cookie mode (default): `{ "base_url": "https://...", "auth_mode": "session_cookie", "session_cookie": "session=..." }`
    - api-token mode: `{ "base_url": "https://...", "auth_mode": "api_token", "api_token": "..." }`
  - `base_url` may be omitted if previously configured.
  - session cookie is treated as one-time input and is not persisted.
  - response: `{ "synced": <int>, "platform": "ctfd" }`
- `GET /integrations/ctfd/config`

## Auth
- `GET /auth/codex/status`
- `POST /auth/codex/files` (multipart form with `file` and `tag`)
- `POST /auth/codex/active-tag` with body `{ "tag": "..." }`
- `DELETE /auth/codex/files/{file_id}`
- `DELETE /auth/codex/tags/{tag}`

## Challenges
- `GET /challenges?ctf_id=<uuid>`
- `GET /challenges/{challenge_id}`
- `POST /challenges`
- `PATCH /challenges/{challenge_id}`
- `DELETE /challenges/{challenge_id}`
- `POST /challenges/artifacts/upload` (multipart form with `file`)

## CTFs
- `GET /ctfs`
- `POST /ctfs`
- `GET /ctfs/{ctf_id}`
- `PATCH /ctfs/{ctf_id}`
- `DELETE /ctfs/{ctf_id}` (also deletes associated challenges/runs)

## Runs
- `GET /runs?active_only=true&status=running&challenge_id=<uuid>&limit=100`
- `POST /runs`
  - body: `{ "challenge_id": "<uuid>", "backend": "mock|codex|claude_code", "reasoning_effort": "low|medium|high|xhigh", "budgets": { "max_minutes": 30, "max_commands": null }, "stop_criteria": {...optional...}, "local_deploy_enabled": false }`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/terminate` (force stop a queued/running run)
- `DELETE /runs/{run_id}` (completed runs only)
- `GET /runs/{run_id}/logs?offset=0&limit=65536`
- `GET /runs/{run_id}/logs/stream` (SSE live log stream)
- `GET /runs/{run_id}/result`

## Notes
- Run status values: `queued|running|flag_found|deliverable_produced|blocked|timeout`
- Result payload is the archived sandbox `result.json` contract.
