# Run Continuation Plan: Resume an Agent Run with User Input

This plan describes how to continue work after a run has already finished, while allowing operators to inject arbitrary guidance (hints, corrections, deliverable feedback, etc.) in a controlled way.

## 1) Goals and constraints

### Goals
- Let operators create a **follow-up run** from a completed run.
- Preserve complete lineage: original run -> continuation run(s).
- Support arbitrary user-provided continuation input (free text + optional structured fields).
- Keep the sandbox result contract unchanged (`result.json` + `README.md`).
- Keep orchestrator internals runner-agnostic; continuation is a control-plane concern.

### Constraints
- Challenge files remain read-only under `/workspace/chal`.
- Writable outputs remain under `/workspace/run`.
- Continuation must not mutate historical run artifacts in-place.
- Security defaults remain conservative (no hidden capability escalation).

---

## 2) UX and product behavior

### Operator flow
1. Operator opens a completed run in the frontend.
2. Operator clicks **Continue run**.
3. Operator enters continuation input:
   - freeform instructions (required)
   - optional intent tag (`hint`, `deliverable_fix`, `strategy_change`, `other`)
   - optional override for stop criteria/time budget
4. System creates a new run linked to parent run.
5. New run starts with:
   - challenge mounted as usual
   - optional parent context package mounted read-only
   - continuation instruction appended to the new run prompt context

### CLI flow
- New command: `disorder runs continue <parent_run_id> --message "..." [options]`
- Returns new run id and streams logs like normal `run` workflows.

---

## 3) Data model and API design

## 3.1 Data model additions
Add lineage and continuation metadata at the run model level:
- `parent_run_id: UUID | null` (self-referential FK)
- `continuation_depth: int` (derived/denormalized for querying)
- `continuation_input: text | null` (operator-provided message)
- `continuation_type: enum | null` (`hint`, `deliverable_fix`, `strategy_change`, `other`)

Notes:
- Preserve existing run schemas; these fields are additive.
- Never overwrite parent run metadata/artifacts.

## 3.2 API additions
Add endpoint under run routes:
- `POST /runs/{run_id}/continue`

Request body (proposed):
- `message: string` (required)
- `type: string` (optional enum)
- `time_limit_seconds: int` (optional override)
- `stop_criteria_override: object` (optional, validated)
- `reuse_parent_artifacts: bool` (default true)

Response:
- Standard run response for newly created child run, including `parent_run_id`.

Validation:
- Parent run must be terminal (`completed`, `failed`, `timed_out`, etc.).
- Reject continuation from non-terminal runs.
- Enforce message length limits and safe logging behavior.

---

## 4) Continuation context packaging strategy

## 4.1 Minimal viable approach
For the child run, create a continuation context directory under run state (control-plane managed), containing:
- `parent_result.json` (copy of parent result)
- `parent_readme.md` (copy of parent summary)
- `continuation_request.json` (message/type/timestamp/operator)

Mount this bundle read-only into sandbox (e.g., `/workspace/chal/.continuation` or separate read-only mount path).

## 4.2 Prompt injection contract
Update sandbox runtime prompt composition so child runs get explicit context:
- “This run is a continuation of run `<id>`.”
- “Operator input: `<message>`.”
- “Use parent artifacts as reference; do not assume correctness without verification.”

Keep final output contract exactly the same for child runs.

## 4.3 Future-safe extension
Later phases can include richer carryover (selected files, transcripts, structured evidence pointers), but phase 1 should only include parent summary + explicit operator input.

---

## 5) Backend orchestration impact

- Orchestrator remains runner-agnostic.
- Docker runner only receives an additional optional read-only mount for continuation context.
- Env/settings wiring for feature flags should live in config:
  - `ENABLE_RUN_CONTINUATION` (default true or staged false)
  - `MAX_CONTINUATION_MESSAGE_CHARS`
  - `MAX_CONTINUATION_DEPTH`

Guardrails:
- Prevent unbounded continuation chains (`MAX_CONTINUATION_DEPTH`).
- Make continuation mount explicit and auditable in logs.

---

## 6) Frontend and CLI changes

## Frontend
- Add “Continue run” action on terminal runs.
- Modal/form for continuation message and options.
- Display lineage breadcrumb on run detail page:
  - parent link
  - child runs list

## CLI
- Add `runs continue` command.
- Optional flags:
  - `--type`
  - `--time-limit-seconds`
  - `--stop-criteria-file`
  - `--no-reuse-parent-artifacts`

---

## 7) Security and trust boundaries

- Treat continuation input as untrusted user content.
- Sanitize/redact in logs where needed.
- Do not execute continuation input directly as shell code.
- Keep parent artifact mount read-only.
- Preserve existing challenge and run mount boundaries.

---

## 8) Testing plan

## Unit tests (control plane)
- Continuation request validation (terminal vs non-terminal parent).
- Child run creation with correct lineage metadata.
- Depth limit enforcement.
- Context package creation correctness.

## Integration tests
- `POST /runs/{id}/continue` creates runnable child.
- Child run receives continuation context and still validates contract outputs.
- Parent artifacts are not mutated.

## Frontend tests
- Continue button visibility only for terminal runs.
- Modal validation and API payload correctness.
- Lineage rendering on run details.

## CLI tests
- Command argument parsing and request payload shape.
- Happy path output includes new run id.

---

## 9) Rollout plan

1. **Phase 1 (backend API + lineage fields + minimal context mount)**
   - Add DB fields + migration.
   - Add continuation endpoint and orchestration plumbing.
   - Feature-flagged if needed.
2. **Phase 2 (frontend + CLI)**
   - Add operator and automation entrypoints.
3. **Phase 3 (hardening)**
   - Add depth/size limits, better observability, and docs.

---

## 10) Acceptance criteria

- Operators can continue a completed run with arbitrary input.
- Child runs are clearly linked to parent runs.
- Sandbox output contract remains unchanged and valid.
- Continuation context is read-only and auditable.
- Frontend + CLI both support continuation flows.
