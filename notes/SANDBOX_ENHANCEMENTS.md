# Sandbox Enhancement Plan: SageMath + IDA (idalib MCP)

This plan extends `ctf-agent-sandbox` for advanced math and reverse engineering while preserving isolation, reproducibility, and the existing run contract.

## 1) Objectives and non-goals

### Objectives

- Add SageMath for algebra/number theory/crypto-heavy CTF tasks.
- Replace Ghidra integration with IDA via `idalib-mcp` (`uv run idalib-mcp`).
- Keep current run contract unchanged (`result.json` + `README.md`).
- Keep capabilities safe by default and explicitly enabled.

### Non-goals (initial phase)

- No GUI tooling inside sandbox.
- No orchestrator schema redesign.
- No Kubernetes runner changes in this phase.

---

## 2) Current-state extension points

- Sandbox base image and package install path:
  - `images/ctf-agent-sandbox/Dockerfile`
- Runtime prompt + execution behavior:
  - `images/ctf-agent-sandbox/agent_runner.py`
  - `images/ctf-agent-sandbox/agent_prompt.txt`
  - `images/ctf-agent-sandbox/ctf_tooling_guide.md`
- Sandbox env passthrough and mounts:
  - `control_plane/app/orchestrator/docker_runner.py`
  - `control_plane/app/core/config.py`

---

## 3) Design principles

1. Deterministic builds where practical.
2. Least privilege and default-disable for heavy capabilities.
3. Preserve CPU/memory/pids limits from control-plane settings.
4. Keep generated artifacts under `/workspace/run` for auditability.

---

## 4) Implementation roadmap

## Phase A - SageMath integration

### A1. Packaging and image updates

- Install SageMath in `images/ctf-agent-sandbox/Dockerfile`.
- Prefer distro package first (`sagemath`), fall back to pinned strategy only if required.

### A2. Runtime documentation for agents

- Extend `ctf_tooling_guide.md` with common Sage workflows and evidence expectations.
- Update `agent_prompt.txt` to steer agents toward Sage when appropriate.

### A3. Contract-safe usage

- Keep `agent_runner.py` schema behavior unchanged; evidence references should point to scripts/logs in `/workspace/run`.

### A4. Tests

- Extend `tests/unit/test_agent_runner_contract.py` with Sage-shaped deliverable/evidence examples (no schema change).

---

## Phase B - IDA + idalib MCP integration

### B1. Runtime topology

- Register `idalib-mcp` in the managed Codex MCP config using stdio transport:
  - `uv run idalib-mcp --unsafe --stdio-shared`
- Ensure required Python package is present in sandbox:
  - `pip install idapro`
  - install `ida-pro-mcp` from `https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip` (not PyPI)
- Process lifecycle is owned by Codex after it reads the managed stdio MCP config.

### B2. IDA dependency provisioning

- IDA binaries are not downloaded in sandbox.
- Operator provides host Linux IDA installation path through env:
  - `SANDBOX_IDA_HOST_PATH`
- Docker runner mounts it read-only into sandbox (default mount target `/opt/ida`).
- Sandbox must include `IDADIR` in the Codex MCP server environment for IDA MCP runtime.
- Sandbox runtime auto-accepts configured EULA keys before registering IDA MCP:
  - default `SANDBOX_IDA_ACCEPT_EULA=true`
  - default `SANDBOX_IDA_EULA_VERSIONS=90,91,92,93`
- Optional persistence across runs:
  - mount host path to `/home/ctf/.idapro` via `SANDBOX_IDA_REGISTRY_HOST_PATH`

### B3. Conditional enablement (fail-closed)

- If `SANDBOX_IDA_HOST_PATH` is unset/empty:
  - do not mount IDA path
  - do not register `idalib-mcp` in the managed Codex MCP config
- Runner logs should state IDA MCP is disabled/unavailable rather than failing cryptically.

### B4. MCP registration

- Keep existing local `verify_flag_candidate` MCP registration.
- Add conditional stdio MCP registration for IDA:
  - `mcp_servers.ida_pro.command="uv"`
  - `mcp_servers.ida_pro.args=["run", "idalib-mcp", "--unsafe", "--stdio-shared"]`
  - `mcp_servers.ida_pro.env` includes `IDADIR`

### B5. Agent-facing docs

- Update `ctf_tooling_guide.md` and `agent_prompt.txt` with:
  - when to use IDA MCP
  - fallback behavior when unavailable

---

## Phase C - Control-plane configuration plumbing

### C1. Settings

- Add env-driven settings in `control_plane/app/core/config.py`:
  - `SANDBOX_IDA_HOST_PATH` (optional, default empty)
  - `SANDBOX_IDA_MOUNT_PATH` (default `/opt/ida`)
  - `SANDBOX_IDA_REGISTRY_HOST_PATH` (optional, for persistent `/home/ctf/.idapro`)
  - `SANDBOX_IDA_ACCEPT_EULA` (default `true`)
  - `SANDBOX_IDA_EULA_VERSIONS` (default `90,91,92,93`)

### C2. Orchestrator behavior

- Add conditional IDA volume mount and runtime env in `docker_runner.py`.
- Keep DB/API schemas runner-agnostic and unchanged.

### C3. Compose/operator wiring

- Add env propagation in `docker-compose.yml` and `.env.example`.
- Document that host path passthrough may be needed depending on deployment topology.

---

## 5) Security and reliability checklist

- Do not fetch IDA binaries at runtime.
- Mount IDA installation read-only.
- Keep writable state under `/workspace/run` only.
- Preserve existing container resource limits/timeouts.
- If IDA is unavailable, proceed without IDA MCP and keep run contract valid.

---

## 6) Rollout strategy

1. Land config + conditional mount/env plumbing.
2. Land sandbox stdio `idalib-mcp` MCP registration.
3. Expand tests and docs.
4. Enable on selected environments by setting `SANDBOX_IDA_HOST_PATH`.

---

## 7) Suggested PR breakdown

1. PR-1: control-plane settings + Docker mount/env conditional logic.
2. PR-2: sandbox stdio `uv run idalib-mcp --unsafe --stdio-shared` Codex MCP wiring.
3. PR-3: tests + docs + operator runbook updates.

---

## 8) Acceptance criteria

- Sandbox runs still produce valid `result.json` and `README.md`.
- With `SANDBOX_IDA_HOST_PATH` configured, Codex runs can access IDA MCP at localhost.
- With `SANDBOX_IDA_HOST_PATH` unset, IDA MCP is not exposed and runs remain functional.
- Documentation clearly explains enablement, defaults, and fallback behavior.
