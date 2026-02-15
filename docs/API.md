# API (MVP)

## Health
- `GET /healthz`

## Integrations
- `POST /integrations/ctfd/sync`
  - body: `{ "base_url": "https://...", "api_token": "..." }` (optional if already configured)
  - response: `{ "synced": <int>, "platform": "ctfd" }`
- `GET /integrations/ctfd/config`

## Challenges
- `GET /challenges`
- `GET /challenges/{challenge_id}`
- `POST /challenges/artifacts/upload` (multipart form with `file`)

## Runs
- `GET /runs?active_only=true&status=running&limit=100`
- `POST /runs`
  - body: `{ "challenge_id": "<uuid>", "backend": "mock|codex|claude_code", "stop_criteria": {...optional...}, "local_deploy_enabled": false }`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/logs?offset=0&limit=65536`
- `GET /runs/{run_id}/result`

## Notes
- Run status values: `queued|running|flag_found|deliverable_produced|blocked|timeout`
- Result payload is the archived sandbox `result.json` contract.
