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
- If IDA MCP is available, use it for decompilation/xref-heavy workflows:
  - `idalib-mcp` default endpoint is `http://127.0.0.1:8745/mcp`.
  - Prefer extracting structured outputs (functions, xrefs, pseudocode) into `/workspace/run`.
  - When working with the IDA MCP, keep in mind that `/workspace/chal` is read-only and autoanalysis will not be able to open the artifact due to it creating files in the same directory. If the autoanalysis fails to open the file, copy the file into `/workspace/run`.
  - If IDA MCP is unavailable for this run, continue with binutils-based reversing and document that fallback.

Crypto / forensics:
- Use `pycryptodome` primitives rather than ad-hoc implementations.
- Use `z3-solver` for constraint solving where applicable.
- Validate decoded output assumptions before concluding.
- Prefer `sage` or `sage -python` for algebra, finite fields, ECC, lattices, and modular arithmetic workflows.
- Use `sympy` for symbolic simplification/factoring and equation solving.
- Use `numpy` for matrix/vector-heavy prototypes when exact arithmetic is not required.
- Save math scripts and intermediate outputs to `/workspace/run` and reference them in `result.json` evidence.

Web / protocol:
- Use `curl`, `wget`, `nc`, `socat` against allowlisted endpoints only.
- Save request/response evidence snippets in `/workspace/run`.
