CTF Sandbox Tooling Guide
=========================

General workflow:
- Start with triage on `/workspace/chal`: `ls -la`, `file`, `strings`, `sha256sum`.
- Keep all generated outputs in `/workspace/run`.
- Do not scan arbitrary targets; only use explicitly allowed endpoints.

Binary / pwn:
- Use `pwn checksec <binary>` first.
- Use `gdb`/`gdb-multiarch`, `objdump`, `readelf`, `strings`, `patchelf` as needed.
- Prefer reproducible solve scripts with `pwntools`.
- In `pwntools`, set `context.binary`, `context.log_level`, and deterministic timeouts.

Reverse engineering:
- Use `objdump -d`, `readelf -a`, `nm`, `strings`, and scripting for automation.
- Capture function offsets and notable constants in the README.

Crypto / forensics:
- Use `pycryptodome` primitives rather than ad-hoc implementations.
- Use `z3-solver` for constraint solving where applicable.
- Validate decoded output assumptions before concluding.

Web / protocol:
- Use `curl`, `wget`, `nc`, `socat` against allowlisted endpoints only.
- Save request/response evidence snippets in `/workspace/run`.
