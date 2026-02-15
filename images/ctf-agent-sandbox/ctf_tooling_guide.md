CTF Sandbox Tooling Guide
=========================

General workflow:
- Start with triage on `/workspace/chal`: `ls -la`, `file`, `strings`, `sha256sum`.
- Keep all generated outputs in `/workspace/run`.
- You may install missing tools during a run when needed for solving.
- Prefer user-space installs and portable binaries (non-root): `python -m pip install --user ...`, download/extract into `/workspace/run/tools`, then prepend PATH.
- Record installed tool versions and how they were installed in `README.md`.
- Do not scan arbitrary targets; prioritize configured challenge/local endpoints.

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
- Prefer the crypto/math MCP tools for common operations (factorization, CRT, modular inverse), and use `sympy_eval`/`sage_eval` for scratch work.
- `sage_eval` may bootstrap a local conda env under `/workspace/run/.mamba` on first use (large download; document it).

Web / protocol:
- Use `curl`, `wget`, `nc`, `socat` against allowlisted endpoints only.
- Save request/response evidence snippets in `/workspace/run`.

MCP power tools:
- Flag verification: call MCP tool `verify_flag_candidate` with a candidate flag and copy the returned `flag_verification` object into `result.json`.
- Crypto/math: `factorint`, `crt`, `modinv`, `is_prime`, `sympy_eval`, `sage_eval`.
- Reverse engineering (Ghidra): use the `ghidra` MCP for headless import/decompile/analysis; it may download/setup Ghidra under `/workspace/run/tools/ghidra` on first use.
