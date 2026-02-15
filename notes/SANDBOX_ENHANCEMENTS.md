# Sandbox Enhancement Plan: SageMath + Headless Ghidra

This plan extends the existing `ctf-agent-sandbox` to support advanced math and reverse-engineering workflows while preserving isolation and reproducibility.

## 1) Objectives and non-goals

### Objectives
- Add **SageMath** for algebra/number theory/crypto-heavy CTF tasks.
- Add **headless Ghidra** for static reverse engineering and scriptable decompilation.
- Keep current run contract (`result.json` + `README.md`) unchanged.
- Make capabilities configurable and safe-by-default where possible.

### Non-goals (initial phase)
- No full GUI tooling inside sandbox.
- No orchestrator schema redesign.
- No Kubernetes runner work in this phase.

---

## 2) Current-state extension points (from repo)

- Sandbox base image and package install path:
  - `images/ctf-agent-sandbox/Dockerfile`
- Runtime prompt + execution behavior:
  - `images/ctf-agent-sandbox/agent_runner.py`
  - `images/ctf-agent-sandbox/agent_prompt.txt`
  - `images/ctf-agent-sandbox/ctf_tooling_guide.md`
- Sandbox env passthrough and mounts:
  - `control_plane/app/orchestrator/docker_runner.py` (`_sandbox_environment`, volumes in `execute_run`)

---

## 3) Design principles

1. **Deterministic builds**: pin versions where practical; avoid ad-hoc runtime downloads.
2. **Least privilege**: default-disable heavy/risky features and require explicit enablement.
3. **Resource controls**: retain container CPU/memory/pids limits from control-plane settings.
4. **Auditable execution**: encourage scripted usage and artifact output under `/workspace/run`.

---

## 4) Implementation roadmap

## Phase A — SageMath integration

### A1. Packaging and image updates
- Update `images/ctf-agent-sandbox/Dockerfile` to install SageMath.
- Prefer distro package first (`sagemath`) for simplicity; if version gaps block CTF use-cases, move to a pinned binary/image-layer strategy.
- Verify expected binaries exist: `sage`, `python3 -c "import sageall"` (or equivalent import path depending on package).

### A2. Runtime documentation for agents
- Extend `ctf_tooling_guide.md` with:
  - common Sage snippets (finite fields, lattice ops, polynomial rings, CRT, discrete log helpers)
  - guidance for saving scripts/results under `/workspace/run`.
- Update `agent_prompt.txt` to explicitly mention when SageMath is preferred over ad-hoc pure Python implementations.

### A3. Contract-safe usage pattern
- In `agent_runner.py`, no schema changes needed; ensure guidance encourages citing Sage-generated evidence in `result.json` (`evidence` entries pointing to scripts/logs).

### A4. Tests
- Add/extend sandbox contract tests (`tests/unit/test_agent_runner_contract.py`) with mocked run outputs that include Sage-generated deliverables/evidence paths.

---

## Phase B — Headless Ghidra integration

### B1. Packaging approach
- Add Java runtime dependency (e.g., `openjdk-17-jre-headless`) and Ghidra distribution.
- Prefer one of:
  1) Build-time download with pinned version + checksum validation.
  2) Vendor archive in internal artifact source if supply-chain control is needed.
- Install under stable path (e.g., `/opt/ghidra`) and expose helper wrapper script in `/usr/local/bin/ghidra-headless`.

### B2. Headless workflow helpers
- Add reusable scripts (new folder suggested: `images/ctf-agent-sandbox/ghidra_scripts/`) for common tasks:
  - import binary and run auto-analysis
  - export decompilation for target symbols/functions
  - list strings/functions/references to JSON/text outputs
- Ensure outputs go to `/workspace/run/ghidra/*` for collection and auditing.

### B3. Prompt/tooling docs
- Update `ctf_tooling_guide.md` with canonical commands for headless analysis.
- Add examples combining `file`, `objdump`, `strings`, and Ghidra outputs.

### B4. Optional capability toggle
- Add env flag design (e.g., `SANDBOX_ENABLE_GHIDRA=1`) passed through existing passthrough mechanism (`_sandbox_environment`) so deployments can disable by default.

### B5. Tests
- Unit-level tests for command rendering/helper script invocation logic (if Python wrappers are added).
- Contract tests continue to assert valid `result.json` regardless of ghidra usage.

---

## Phase C — Control-plane and operator experience improvements

### C1. Configuration plumbing
- Add documented env vars in `control_plane/app/core/config.py` and README:
  - `SANDBOX_ENABLE_SAGEMATH`
  - `SANDBOX_ENABLE_GHIDRA`
  - optional `SANDBOX_GHIDRA_MAX_ANALYSIS_SECONDS`

### C2. Run metadata surfacing
- Optionally include enabled tool capability flags in run metadata/log preamble for observability (no breaking API changes).

### C3. Failure handling
- If a tool is disabled/unavailable, runner should produce actionable blocked notes (not cryptic command failures).

---

## 5) Security and reliability checklist

- Validate all downloaded binaries/archives via checksum/signature.
- Keep Ghidra projects and temp files inside `/workspace/run`.
- Avoid host mounts beyond existing chal/run/auth paths.
- Preserve current Docker resource limits and timeout behavior.
- Ensure no secrets are written to deliverables/logs.

---

## 6) Rollout strategy

1. **Dev image branch** with Sage only; run unit tests + smoke.
2. Add Ghidra in a second PR to isolate build/runtime regressions.
3. Enable in staging with feature flags off by default.
4. Collect run metrics (duration, success rate by category, timeout deltas).
5. Gradually enable per CTF/event profile.

---

## 7) Suggested PR breakdown

1. PR-1: Dockerfile + docs for SageMath; minimal tests.
2. PR-2: Ghidra packaging + helper scripts + docs.
3. PR-3: Config/plumbing/feature flags + observability + hardening.
4. PR-4: Optional UX updates in frontend for capability visibility.

---

## 8) Acceptance criteria

- Sandbox builds reproducibly with SageMath and (optionally) Ghidra.
- Agent can execute Sage scripts and headless Ghidra workflows without manual setup.
- `result.json` contract remains valid for all runs.
- Clear docs exist for operators and contributors.
- Feature flags allow safe disablement in constrained environments.
