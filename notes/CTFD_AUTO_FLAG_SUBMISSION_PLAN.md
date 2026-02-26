# CTFd Auto Flag Submission Plan

This plan covers automatic flag submission for challenges imported from CTFd, while preserving the current sandbox contract (`result.json` + `README.md`) and keeping orchestration runner-agnostic.

## 1) Current state (important)

- The control plane already attempts CTFd submission after a run reaches `flag_found`:
  - `control_plane/app/orchestrator/docker_runner.py` (`_verify_flag_result`)
  - Uses `CTFdClient.submit_flag(challenge_id, submission)` via `/api/v1/challenges/attempt`.
- Submission currently only works when an API token is persisted in `integration_configs`.
- Session-cookie sync mode is intentionally one-time and not persisted, so auto-submit may be unavailable after sync.
- Submission outcomes are collapsed into `flag_verification` only; there is no durable attempt history.

## 2) Target outcomes

1. Automatically submit candidate flags for CTFd-synced challenges when policy allows.
2. Keep submission logic outside sandbox runtime as the source of truth.
3. Make behavior auditable (attempt logs, verdicts, timestamps, retries).
4. Handle unsupported/multipart edge cases safely (no uncontrolled spam).
5. Keep existing result schema compatible.

## 3) Design options

## Option A: Backend-owned submit-on-`flag_found` (recommended baseline)

Flow:
1. Run finishes and stop criteria resolve to `flag_found`.
2. Control plane extracts `result.flag` and submits to CTFd.
3. Control plane stores submission attempt record and updates `flag_verification` details.
4. Control plane keeps run final status behavior unchanged.

Pros:
- Centralized credentials and rate limiting.
- Deterministic, auditable, and runner-agnostic.
- Works for all backends (Codex/Claude/mock) without prompt coupling.

Cons:
- Agent cannot iteratively submit/check multiple candidates during a single run.

## Option B: Agent MCP for direct submission from sandbox

Flow:
1. Expose `submit_flag_candidate` MCP tool in sandbox.
2. Agent calls MCP during solving loop.
3. MCP submits to CTFd and returns structured verdict.
4. Agent uses verdict to continue or finalize `result.json`.

Pros:
- Enables iterative solve loops.
- Supports agent-driven strategy adaptation.

Cons:
- Higher risk of noisy/duplicate submissions.
- Requires credential flow into sandbox (larger trust surface).
- Harder to standardize behavior across models.
- Multipart/plugin-specific submission semantics are ambiguous.

## Option C: Hybrid (recommended end state)

- Keep Option A as authoritative automatic submission path.
- Add Option B later as optional capability gate for iterative workflows.
- Backend remains final source of truth for recorded submission verdicts.

## 4) Recommended implementation plan

## Phase 1 - Harden backend auto-submit (Option A)

### 4.1 Submission policy and settings
- Add explicit policy (env + optional per-CTF override):
  - `CTFD_AUTO_SUBMIT_ENABLED=true|false` (default `true`)
  - `CTFD_AUTO_SUBMIT_MAX_ATTEMPTS_PER_RUN` (default `1`)
  - `CTFD_AUTO_SUBMIT_RETRY_COUNT` (default `0`)
- Keep conservative defaults to avoid accidental spam.

### 4.2 Durable submission attempt model
- Add DB table for attempt auditability, e.g. `flag_submissions`:
  - `id`, `run_id`, `challenge_id`, `platform`, `submission_hash`, `submitted_at`
  - `request_payload_json`, `response_payload_json`
  - `verdict_normalized` (`correct|incorrect|already_solved|rate_limited|error|unknown`)
  - `http_status`, `error_message`
- Do not store plaintext flag unless explicitly configured; default to hash-only at this layer.

### 4.3 Service boundary
- Move submit logic out of `DockerRunner._verify_flag_result` into a service, e.g. `control_plane/app/services/flag_submission_service.py`.
- Orchestrator calls service only with normalized inputs and receives normalized output.
- This preserves runner-agnostic orchestration.

### 4.4 Credential behavior
- Keep API-token auth as primary path.
- If only session-cookie sync exists and no token is configured, mark submission as `unavailable` with explicit detail.
- Do not persist session cookies by default.

### 4.5 Result contract compatibility
- Keep `SandboxResult` unchanged.
- Continue mapping best-known verdict into `flag_verification`:
  - `method: "platform_submit"` when attempted
  - `verified: true|false`
  - `details: normalized verdict + short reason`
- Expose full attempt history via run API (new endpoint) rather than overloading `result.json`.

### 4.6 API/UX additions
- Add endpoint: `GET /runs/{run_id}/submissions`.
- Frontend run page: show submission timeline and final platform verdict.
- Optional manual retry endpoint (operator action): `POST /runs/{run_id}/submit-flag`.

### 4.7 Tests
- Unit tests for verdict normalization across CTFd response shapes.
- Unit tests for dedupe/rate-limit behavior.
- Integration tests for:
  - successful auto-submit
  - already solved
  - invalid token
  - no configured token
  - CTFd API error handling

## Phase 2 - Optional MCP submission tool (Option B)

### 4.8 MCP server
- Add sandbox MCP similar to `flag_verify_mcp.py`, e.g. `flag_submit_mcp.py`.
- Tool shape:
  - input: `{ flag: string }`
  - output: `{ verdict, verified, details, raw_response }`
- Enforce local guardrails:
  - per-run call cap
  - duplicate-flag suppression
  - cooldown after repeated failures

### 4.9 Credential routing for MCP
- Prefer short-lived run-scoped token injected by control plane.
- Avoid handing long-lived integration token directly to model when possible.

### 4.10 Multipart/plugin handling strategy
- Define explicit support mode in challenge metadata:
  - `submission_mode: single` (default)
  - `submission_mode: multipart` (future/plugin-specific)
- For unknown/multipart mode:
  - disable auto MCP submit
  - keep backend final submit/manual operator path
- Do not assume plugin endpoints; require explicit adapter support before enabling.

## Phase 3 - Observability and operations

- Metrics:
  - auto-submit attempts, success rate, incorrect rate, error rate, rate-limit rate.
- Structured logs with run/challenge correlation IDs.
- Admin toggles for temporary global disable during events.

## 5) Recommended order of delivery

1. Extract and harden backend submission into dedicated service.
2. Add attempt persistence + API + frontend visibility.
3. Add submission policy controls and conservative defaults.
4. Add optional MCP submission path behind feature flag.
5. Add multipart/plugin adapters only after concrete target platforms are identified.

## 6) Acceptance criteria

- CTFd-imported challenge with configured API token auto-submits on `flag_found`.
- Every submission attempt is queryable and auditable.
- No repeated duplicate submissions beyond configured limits.
- Unsupported auth/multipart cases fail safe with clear operator-visible reason.
- Existing `result.json` contract remains valid.
