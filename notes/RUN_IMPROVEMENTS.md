# Run Improvements Plan

This document proposes a scoped implementation plan for three related improvements:

1. Passing arbitrary per-run parameters into sandbox agent invocation.
2. Providing parent run deliverables to continuation runs.
3. Automatically queuing continuation runs until a desired outcome is reached or retry policy is exhausted.

The plan is grounded in the current implementation:

- Run creation and continuation live in `control_plane/app/services/run_service.py`.
- Run API shapes live in `control_plane/app/schemas/run.py`.
- Sandbox spec assembly and execution live in `control_plane/app/orchestrator/docker_runner.py`.
- Backend command construction lives in `images/ctf-agent-sandbox/agent_runner.py`.
- Continuation support already exists, but currently only carries `parent_result.json`, `parent_readme.md`, and `continuation_request.json`.

## Design goals

- Preserve the existing sandbox result contract: `result.json` and `README.md`.
- Keep DB and API schemas runner-agnostic where possible.
- Keep Docker-specific file mounting logic in `docker_runner.py`.
- Make automatic retries explicit, auditable, and bounded.
- Avoid turning per-run invocation control into arbitrary shell execution.

## Current-state gaps

### A. Arbitrary agent invocation parameters

Current runs capture `backend`, `budgets`, and `reasoning_effort`, but there is no first-class per-run field for backend-specific invocation overrides. The sandbox currently derives Codex CLI arguments from fixed logic in `agent_runner.py`, plus process-wide environment passthrough from control-plane settings.

Result: forcing a specific model such as `gpt-5.4` is possible only indirectly through global environment or custom container configuration, not as a normal run-level option.

### B. Parent deliverables in continuations

Current continuation bundles only include summary artifacts:

- `parent_result.json`
- `parent_readme.md`
- `continuation_request.json`

The actual files referenced by `result.json.deliverables[]` are not made available to the continuation run.

Result: a child run can read what the parent claimed to produce, but cannot directly inspect or reuse the solve script, exploit, binary patch, notes, or other artifacts unless the operator manually re-supplies them.

### C. Automatic continuation queueing

Continuation creation is currently operator-driven through `POST /runs/{run_id}/continue`. There is no policy engine that evaluates terminal runs and schedules the next attempt automatically.

Result: retry loops for quota failures, transient backend failures, or "keep going until FLAG_FOUND" behavior require manual intervention.

## Proposed architecture

## 1. Add a generic run-level invocation config

Introduce a new JSON field on `Run`:

- `agent_invocation: dict`

This should store backend-specific invocation overrides in a runner-agnostic envelope instead of embedding raw CLI strings in run records.

Suggested shape:

```json
{
  "model": "gpt-5.4",
  "profile": null,
  "extra_args": ["--some-flag", "value"],
  "env": {
    "CODEX_MODEL": "gpt-5.4"
  }
}
```

Recommended rules:

- `model` is the main first-class field.
- `extra_args` is optional and must be a list of strings.
- `env` is optional and must be allowlisted per backend.
- No raw shell fragments.
- No command-template override from API payloads.
- Continue to support global `CODEX_CLI_CMD` from environment for deployment-level customization, but do not expose that as a run payload.

Why this design:

- It satisfies the "arbitrary parameters" goal without making the API a shell injection surface.
- It keeps the model/backend knobs attached to the run lineage, so continuations can inherit or override them.
- It maps cleanly to future backends besides Codex.

## 2. Extend continuation bundles to include deliverables

Add a control-plane-managed deliverable bundle under the child run's continuation directory:

- `continuation/parent_result.json`
- `continuation/parent_readme.md`
- `continuation/continuation_request.json`
- `continuation/deliverables_manifest.json`
- `continuation/deliverables/<files copied from parent>`

`deliverables_manifest.json` should include at least:

- original parent run id
- original relative path
- deliverable type
- `how_to_run`
- copied bundle path
- copy status or error if unavailable

Implementation rule:

- Only copy files explicitly listed in the parent validated `result.json.deliverables`.
- Prefer local run storage as source.
- Fall back to blob store if the local file is unavailable.
- Mount the continuation bundle read-only exactly like current continuation context.

Why this design:

- It preserves current mount boundaries.
- It avoids mutating parent run storage.
- It gives the agent both metadata and actual files.
- It keeps the runner ignorant of MinIO details; the control plane performs the staging.

## 3. Add a bounded auto-continuation policy

Introduce a second JSON field on `Run`:

- `auto_continuation_policy: dict | null`

This policy applies to the current run as the root of a retry chain and is inherited by child runs unless explicitly overridden.

Suggested shape:

```json
{
  "enabled": true,
  "max_depth": 5,
  "target": {
    "final_status": "flag_found"
  },
  "when": {
    "statuses": ["blocked", "timeout", "deliverable_produced"],
    "require_contract_match": false
  },
  "on_blocked_reasons": [
    "backend_exit_nonzero",
    "sandbox_output_contract_missing",
    "provider_quota_or_auth"
  ],
  "continuation_type": "strategy_change",
  "message_template": "Previous run did not reach {target_final_status}. Inspect /workspace/continuation, reuse prior deliverables where useful, and continue from the most promising point.",
  "inherit_agent_invocation": true
}
```

Two important choices:

- The retry decision should be based on normalized, structured run-finalization metadata rather than free-text parsing of `README.md`.
- The policy should be evaluated by a control-plane service after run finalization, not by Docker-specific code.

## Detailed implementation plan

## A. Per-run agent invocation parameters

### A1. Schema and persistence

Add `agent_invocation` to:

- `control_plane/app/db/models.py` as `JSONB`, default `{}`.
- the SQLAlchemy migration set.
- `RunCreateRequest`, `RunContinueRequest`, and `RunRead` in `control_plane/app/schemas/run.py`.

Recommended API behavior:

- `POST /runs` accepts `agent_invocation`.
- `POST /runs/{run_id}/continue` accepts `agent_invocation_override`.
- Continuations inherit parent `agent_invocation` unless overridden.

Validation rules:

- `model`: optional string, length-limited.
- `extra_args`: optional list of strings, count-limited.
- `env`: optional dict of string-to-string, key allowlisted.
- Reject unknown top-level keys initially unless there is a strong need for a looser contract.

### A2. Service-layer inheritance

Update `create_run()` and `create_continuation_run()` in `run_service.py`:

- Root run stores its explicit `agent_invocation`.
- Child run starts from parent `agent_invocation`.
- Apply `agent_invocation_override` as a shallow merge or explicit replace.

Recommendation:

- Use shallow-merge for `env`.
- Use replace semantics for `extra_args`.
- Use scalar override semantics for `model`.

### A3. Spec payload

Update `DockerRunner._build_spec_payload()` to include:

```json
"agent_invocation": run.agent_invocation
```

This keeps the sandbox backend logic simple and auditable.

### A4. Sandbox backend adapter

Extend `_resolve_backend_command()` in `images/ctf-agent-sandbox/agent_runner.py`:

- Read `spec["agent_invocation"]`.
- For Codex:
  - if `model` exists, add the appropriate Codex CLI config flag or env export.
  - append validated `extra_args` directly into the argument vector.
  - inject allowlisted `env` into the subprocess environment.
- For other backends, map only fields they understand.

Implementation detail:

- Keep using argument vectors, not shell concatenation.
- Log the effective sanitized invocation config at run start.
- Redact secret-like env values if any are ever permitted.

### A5. Frontend and CLI

Frontend:

- Add an optional "Agent invocation" section in the run form.
- MVP can be a single model field plus an "advanced JSON" textarea.

CLI:

- Add flags such as `--model gpt-5.4`.
- Optionally add `--agent-invocation-file`.

### A6. Tests

- Unit tests for request validation.
- Unit tests for continuation inheritance and override semantics.
- Unit tests for sandbox command construction with `model` and `extra_args`.
- API tests that verify the stored run returns the invocation config.

## B. Parent deliverables for continuation runs

### B1. Context bundle expansion

Extend `create_continuation_context_bundle()` in `run_service.py` to stage parent deliverables.

Add helper functions:

- `_read_parent_result_payload(...)`
- `_collect_parent_deliverable_sources(...)`
- `_copy_parent_deliverables_into_bundle(...)`

Source selection order:

1. `runs/<parent>/run/<deliverable.path>`
2. blob store object at `runs/<parent>/deliverables/<deliverable.path>`

Copy only regular files. Reject or skip:

- missing paths
- paths escaping the run directory
- directories and symlinks
- files beyond configurable size cap

Add settings:

- `MAX_CONTINUATION_DELIVERABLES`
- `MAX_CONTINUATION_DELIVERABLE_BYTES`
- `MAX_CONTINUATION_TOTAL_BYTES`

### B2. Prompt and spec improvements

Update the spec continuation block and prompt rendering so the agent sees:

- parent result/readme mount path
- explicit deliverables bundle path
- manifest path

Example additions:

```json
"continuation": {
  "deliverables_mount_path": "/workspace/continuation/deliverables",
  "deliverables_manifest_path": "/workspace/continuation/deliverables_manifest.json"
}
```

Update `_render_continuation_context()` in `agent_runner.py` to mention the new files explicitly.

### B3. Optional future extension

Phase 1 should copy only files referenced in `deliverables[]`.

Do not include:

- full prior run logs
- arbitrary run output files
- raw challenge mutations

Those can be added later if a concrete use case appears.

### B4. Tests

- Unit tests for bundle creation when parent deliverables exist locally.
- Unit tests for blob-store fallback.
- Unit tests for missing deliverables and partial copy behavior.
- Sandbox/prompt tests ensuring the new mount paths are exposed.

## C. Automatic continuation queueing

### C1. Structured run-finalization metadata

Before adding retry logic, add a structured summary of why a run ended.

Introduce a new optional JSON field on `RunResult` or `Run`:

- `finalization_metadata: dict`

Suggested fields:

```json
{
  "contract_valid": true,
  "sandbox_exit_code": 0,
  "timed_out": false,
  "result_status_before_stop_eval": "blocked",
  "result_status_after_stop_eval": "blocked",
  "failure_reason_code": "provider_quota_or_auth",
  "failure_reason_detail": "Codex CLI exited with authentication or quota error"
}
```

Reason codes should come from control-plane and sandbox normalization logic, not ad hoc string matching later.

Probable initial reason-code set:

- `none`
- `timeout`
- `sandbox_exit_nonzero`
- `sandbox_output_contract_missing`
- `result_validation_failed`
- `provider_quota_or_auth`
- `backend_binary_missing`
- `stop_criteria_not_met`

### C2. Post-run policy evaluator

Add a new control-plane service, for example:

- `control_plane/app/services/auto_continuation_service.py`

Responsibilities:

- decide whether the completed run qualifies for another attempt
- compute the next continuation request
- create the child run
- record why a child was or was not created

Entry point shape:

```python
evaluate_and_queue_auto_continuation(
    db: Session,
    run: Run,
    result: RunResult,
    settings: Settings,
    blob_store: BlobStore,
) -> Run | None
```

Recommended call site:

- after final run/result persistence in `DockerRunner.execute_run()`
- but implemented in a generic service so Kubernetes or other runners can call the same logic later

### C3. Policy semantics

Recommended first-pass policy behavior:

- Only evaluate after terminal statuses.
- Stop immediately if:
  - `run.continuation_depth >= policy.max_depth`
  - `result.status == target.final_status`
  - policy is disabled
- Queue a continuation if:
  - final status is in `policy.when.statuses`
  - and optional reason-code filters match
  - and depth is still below the limit

This cleanly supports:

- "keep trying until `flag_found`"
- "retry blocked runs caused by provider quota/auth"
- "stop after N total attempts"

### C4. Continuation message generation

The auto-created child needs a deterministic continuation message. Do not rely on operators to write one.

Suggested template variables:

- `{parent_run_id}`
- `{parent_status}`
- `{failure_reason_code}`
- `{target_final_status}`
- `{continuation_depth}`

Example generated message:

> Previous run ended `blocked` with `provider_quota_or_auth`. Reuse any existing continuation deliverables, verify what was already attempted, and continue toward `flag_found`.

Use `continuation_type="strategy_change"` by default for auto-generated retries.

### C5. Lineage and loop semantics

Recommendation:

- Auto-created children should always point to the immediate parent run, not the root run.
- Depth remains the existing `continuation_depth`.
- The policy object is copied forward to children unless disabled by override.

This preserves the existing lineage model and makes the chain auditable step by step.

### C6. API and UX

Add `auto_continuation_policy` to:

- `RunCreateRequest`
- `RunContinueRequest` as `auto_continuation_policy_override`
- `RunRead`

Frontend:

- Add a toggle such as "Auto-continue until target is met".
- Show effective policy and current depth on run detail.
- Show whether the next continuation was queued automatically and why.

CLI:

- Add `--auto-continue-until flag_found`
- Add `--auto-continue-max-depth 5`
- Add `--auto-continue-on blocked,timeout`

### C7. Guardrails

- Enforce hard maximum depth in settings even if API requests a larger value.
- Prevent duplicate queueing for the same completed run.
- Store audit metadata for auto-created children, for example `continuation_origin: operator|auto`.
- Consider a small backoff or queue delay only if needed later; phase 1 can enqueue immediately.

### C8. Tests

- Unit tests for policy evaluation across statuses and reason codes.
- Unit tests ensuring no child is created when target status is already met.
- Unit tests ensuring depth limit stops the chain.
- Integration tests for a run that auto-spawns one child.
- Integration tests for a run that stops once `flag_found` is reached.

## Suggested rollout order

### Phase 1: per-run invocation config

Land `agent_invocation` first. It is the smallest self-contained improvement and makes later auto-continuations more useful because children can preserve the exact requested model and backend knobs.

### Phase 2: deliverable carry-forward

Land continuation deliverable staging next. This materially improves child-run effectiveness without changing the execution model.

### Phase 3: structured finalization metadata

Add reason codes and finalization metadata before auto-queueing. This is the prerequisite that keeps retry logic deterministic.

### Phase 4: auto-continuation service

Add the policy evaluator and automatic child creation after run finalization.

### Phase 5: frontend and CLI polish

Expose the new controls once backend semantics are stable.

## Recommended file touchpoints

Backend:

- `control_plane/app/db/models.py`
- migration files
- `control_plane/app/schemas/run.py`
- `control_plane/app/services/run_service.py`
- `control_plane/app/services/auto_continuation_service.py` (new)
- `control_plane/app/orchestrator/docker_runner.py`
- `control_plane/app/core/config.py`

Sandbox:

- `images/ctf-agent-sandbox/agent_runner.py`
- optionally `images/ctf-agent-sandbox/agent_prompt.txt`

Frontend:

- `frontend/src/features/runs/RunPage.tsx`
- generated API types in `frontend/src/api/`

CLI:

- `cli/main.py`

Tests:

- `tests/unit/test_run_continuation_service.py`
- `tests/unit/test_docker_runner_continuation.py`
- new unit tests for invocation config and auto-continuation policy
- frontend tests under `frontend/src/features/runs/`

## Acceptance criteria

- Operators can set a per-run model such as `gpt-5.4` without changing deployment-global configuration.
- Continuation runs receive the parent's declared deliverable files read-only under the continuation mount.
- Automatic continuation can retry until `flag_found`, a blocked terminal condition, or max depth.
- Retry decisions are based on structured finalization metadata, not brittle text parsing.
- All run lineage remains auditable through existing parent/child relationships.
