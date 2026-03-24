# Ralph Looping Plan

Assumption: "Ralph-looping" here means a bounded same-run retry/reflection loop inside the sandbox runner, where the backend is re-invoked multiple times against the same `/workspace/run` state. The loop should not depend on control-plane child runs, `POST /runs/{id}/continue`, or continuation bundles. If "Ralph" is meant more narrowly than that, the shape below still gives the cleanest no-continuation implementation seam.

## Why this belongs in the runner

Today the system has two very different layers:

- `images/ctf-agent-sandbox/agent_runner.py` does one backend invocation, then normalizes a single final `result.json`.
- Continuation logic lives in the control plane and creates new run rows, new run directories, and optional continuation bundles.

Ralph-looping is a better fit for the first layer. The runner already owns:

- prompt rendering
- backend invocation
- contract normalization
- writable run workspace lifecycle

That means we can make repeated attempts in one container and one run ID, using the workspace itself as the loop memory.

## Recommended design

### 1. Add a dedicated runner-loop policy

Do not overload `auto_continuation_policy`. That schema is child-run oriented and includes concepts that do not map cleanly to same-run retries, especially `timeout`.

Add a new run-level policy, for example `runner_loop_policy` or `ralph_loop_policy`, with fields along these lines:

```json
{
  "enabled": true,
  "max_attempts": 3,
  "target_status": "flag_found",
  "retry_on_statuses": ["blocked"],
  "retry_on_reason_codes": ["provider_quota_or_auth", "result_validation_failed"],
  "continue_on_partial_success": true,
  "min_seconds_remaining": 120,
  "instruction_template": "Previous attempt ended with status {status} and reason {failure_reason_code}. Reuse the existing workspace, inspect prior attempt artifacts, and continue from the most promising point."
}
```

Notes:

- `target_status` should use sandbox result statuses only: `flag_found|deliverable_produced|blocked`.
- `timeout` should not be a loop status; the runner cannot "retry after timeout" inside the same container because the container would already be gone.
- Keep this separate from manual/operator continuation features. Manual continuations can stay in the product.

### 2. Implement a loop controller around `_run_external_backend()`

Refactor `agent_runner.py` so `main()` calls something like `run_backend_attempt_loop(spec)` instead of directly invoking `_run_external_backend()` once.

High-level algorithm:

1. Read `runner_loop_policy` from `spec.json`.
2. Compute a soft deadline from `budgets.max_minutes`.
3. For each attempt:
   - render a prompt with base challenge context plus loop context
   - clear the top-level contract files from the previous attempt before starting the next one
   - invoke the backend
   - normalize the produced result with existing `_ensure_contract()` logic
   - snapshot the attempt for audit
   - decide whether to stop or continue
4. Leave the final accepted attempt's `README.md` and `result.json` at `/workspace/run`.

The loop controller should be backend-agnostic. It should wrap both `codex` and `claude_code`, not create a Codex-only special case.

### 3. Keep workspace state, but snapshot each attempt

The key to making this work without continuations is to preserve the writable run workspace across attempts. The files the agent created on attempt 1 become the working set for attempt 2.

However, the contract files cannot simply be left in place, or a failed later attempt could accidentally inherit a stale `result.json`/`README.md`.

Recommended approach:

- Before attempt `N+1`, move the previous top-level contract artifacts into an attempt snapshot directory.
- Keep ordinary working files like `solve.py`, `exploit.py`, downloaded tools, notes, etc. in place.
- Require each attempt to produce fresh top-level `README.md` and `result.json`.

Use a run-local audit tree such as:

```text
/workspace/run/
  result.json
  README.md
  codex_last_message.txt
  runner_loop_state.json
  attempts/
    001/
      prompt.txt
      result.raw.json
      result.normalized.json
      README.md
      codex_last_message.txt
      deliverables_manifest.json
      decision.json
    002/
      ...
```

This gives the next attempt stable material to inspect without needing a control-plane continuation bundle.

### 4. Feed prior-attempt context through the prompt, not through run lineage

Extend the prompt renderer to include a new loop section, for example `ralph_context`.

That section should include:

- attempt number and max attempts
- target status
- previous normalized status
- previous `failure_reason_code`
- prior attempt snapshot path
- previous deliverables manifest path
- previous `codex_last_message.txt` path if present
- the machine-generated retry instruction from the policy template

Important detail: do not inline giant previous README/result contents into the prompt. Point the agent at files in `/workspace/run/attempts/<n>/...` and summarize only the small pieces needed for guidance.

### 5. Decide looping from normalized attempt results

The decision engine should operate on the normalized result payload produced by `_ensure_contract()`, plus backend exit code and remaining time.

Recommended stopping rules:

- Stop immediately on `flag_found`.
- Stop on `deliverable_produced` unless `target_status == "flag_found"` and `continue_on_partial_success` is true.
- Stop if `max_attempts` is reached.
- Stop if remaining time is below `min_seconds_remaining`.
- Stop if the current `failure_reason_code` is not selected by policy.

Recommended continue rules:

- Continue when normalized status is `blocked` and the reason code matches policy.
- Continue when normalized status is `deliverable_produced`, the target is `flag_found`, and partial-success looping is enabled.
- Continue when the backend exits nonzero but the runner synthesized a normalized blocked result with a retryable reason.

The decision outcome for every attempt should be written to `attempts/<n>/decision.json`.

### 6. Emit loop metadata as a sidecar, not in the contract

Keep the main sandbox contract unchanged.

If we want auditability in the control plane, write an optional sidecar file like `/workspace/run/runner_loop_state.json` with:

- policy used
- total attempts
- per-attempt statuses/reason codes
- final attempt number
- whether the loop stopped due to success, policy, or time remaining

Then have `docker_runner.py` ingest that sidecar into `run_results.finalization_metadata` if present. That keeps the result contract stable while still exposing loop behavior in the UI/API later.

### 7. Treat continuations as optional operator tooling, not a prerequisite

This plan does not require removing existing continuation support.

The clean boundary is:

- Ralph-looping: automatic same-run iteration inside one sandbox/container
- continuations: operator-initiated follow-up runs, optional artifact reuse, model changes, or manual intervention after a run is already terminal

That lets us land Ralph-looping without destabilizing lineage features.

## File-level implementation plan

### Phase 1: schema and spec plumbing

Update:

- `control_plane/app/schemas/run.py`
- `control_plane/app/db/models.py`
- new Alembic migration
- `control_plane/app/services/run_service.py`
- `control_plane/app/orchestrator/docker_runner.py`

Work:

- add `runner_loop_policy` schema/model field
- persist it on run creation
- include it in the sandbox spec payload
- do not thread it through continuation-specific codepaths

Recommendation: if migration scope must stay minimal, `runner_loop_policy` can temporarily live in a generic JSON column already present on the run model, but I would prefer a first-class field because this is execution behavior, not incidental metadata.

### Phase 2: runner attempt loop

Update:

- `images/ctf-agent-sandbox/agent_runner.py`
- `images/ctf-agent-sandbox/agent_prompt.txt`

Work:

- add attempt-loop state model/helpers
- add attempt snapshot directory management
- add prompt rendering for loop context
- add loop decision logic
- preserve the final top-level contract outputs

Suggested refactor shape in `agent_runner.py`:

- `_render_ralph_context(...)`
- `_prepare_attempt(...)`
- `_snapshot_attempt_outputs(...)`
- `_decide_ralph_retry(...)`
- `_write_runner_loop_state(...)`
- `run_backend_attempt_loop(...)`

### Phase 3: docs and operator surfaces

Update:

- `README.md`
- `docs/architecture.md`
- `docs/API.md`
- frontend run form and run detail page
- CLI run command

Work:

- expose `runner_loop_policy` on run creation
- show attempt count/final loop reason in run detail
- document that same-run looping reuses the writable workspace and does not create child runs

I would not add a `runs continue` equivalent for Ralph. Manual continuations already cover that use case.

## Test plan

### Runner unit tests

Extend `tests/unit/test_agent_runner_contract.py` or add a dedicated file for loop behavior:

- retries a blocked attempt when reason code is selected
- stops on `flag_found`
- stops on `deliverable_produced` when `continue_on_partial_success` is false
- continues on `deliverable_produced` when target is `flag_found`
- snapshots prior `README.md` and `result.json` before retry
- does not treat stale top-level contract files as a fresh attempt
- writes `runner_loop_state.json` correctly

### Control-plane tests

Add or extend tests for:

- run creation persisting `runner_loop_policy`
- spec payload including `runner_loop_policy`
- optional ingestion of `runner_loop_state.json` into `finalization_metadata`

### Integration smoke

Add one sandbox smoke case that simulates:

1. first attempt writes a retryable blocked result
2. second attempt writes `deliverable_produced` or `flag_found`
3. final archived run result reflects the last attempt only
4. attempt snapshots remain available under the run directory

## Risks and mitigations

### Risk: stale contract artifacts make retries look successful

Mitigation:

- move or delete top-level `README.md`, `result.json`, and backend-specific last-message files before each retry
- snapshot them first

### Risk: prompt bloat from prior-attempt context

Mitigation:

- summarize statuses/reasons in the prompt
- point to files for full details instead of embedding them

### Risk: unbounded disk growth from attempt snapshots

Mitigation:

- snapshot only contract files, the last-message file, and declared deliverables
- avoid full workspace copies
- add caps similar to continuation deliverable staging if needed

### Risk: schema overlap with auto continuation creates operator confusion

Mitigation:

- keep `runner_loop_policy` distinct from `auto_continuation_policy`
- document that one is same-run and the other is multi-run lineage

## Recommended rollout

1. Land spec/schema plumbing first.
2. Land runner loop with a conservative default of `enabled=false`.
3. Expose it in CLI/UI after the runner logic is stable.
4. Later, consider whether current auto-continuation defaults should be replaced by Ralph-looping for common retry cases.

## Acceptance criteria

- A run can perform multiple backend attempts in one sandbox without creating child runs.
- The agent on attempt `N+1` can inspect prior attempt artifacts from the same run.
- The final top-level `result.json` and `README.md` remain contract-compliant.
- Attempt history is auditable under `/workspace/run/attempts/`.
- Existing manual continuations continue to work, but are no longer required for automatic re-tries within a run.
