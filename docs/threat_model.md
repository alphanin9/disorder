# Threat Model (MVP)

## Trust boundaries
- Control plane is trusted.
- Sandbox container is untrusted workload.
- CTFd remote API is semi-trusted input source.

## Key controls
- Challenge mount is read-only (`/workspace/chal`).
- Writable output is isolated to `/workspace/run`.
- Sandbox runs as non-root (`uid=1000`).
- Docker resource limits: CPU, memory, pids.
- Endpoint policy is explicit in RunSpec (`allowed_endpoints`) for agent guidance.
- Artifacts/results/logs are immutable once archived in MinIO object keys.

## Residual MVP risks
- Network egress enforcement is advisory in prompt/spec; hard network policy enforcement is not yet implemented.
- Backend CLIs (`codex`/`claude_code`) are command-template driven and can be misconfigured.
- Local deploy via `docker compose` inherits compose file trust assumptions from challenge artifacts.

## Deferred hardening
- Kernel-level egress controls (iptables/CNI policy).
- Mandatory seccomp/apparmor profiles and dropped capabilities matrix.
- Signed artifact provenance and attestation.
- Multi-tenant authz and per-user secrets isolation.
