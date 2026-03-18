CTF Sandbox Tooling Guide
=========================

General workflow:
- Start with triage on `/workspace/chal`: `ls -la`, `file`, `strings`, `sha256sum`.
- Keep all generated outputs in `/workspace/run`.
- You may install missing tools during a run when needed for solving.
- Prefer user-space installs and portable binaries (non-root): download/extract into `/workspace/run/tools`, then prepend PATH. This does not apply to Python.
- Record installed tool versions and how they were installed in `README.md`.
- Do not scan arbitrary targets; prioritize configured challenge/local endpoints.
- Depending on harness configuration, you may have CUDA support for compute that would benefit from a GPU. When enabled, the harness exposes every GPU visible to the Docker daemon. Use `nvidia-smi -L` to discover visible devices and `nvidia-smi` for utilization/memory details.

Binary / pwn:
- Use `pwn checksec <binary>` first.
- Use `objdump`, `readelf`, `strings`, `patchelf` as needed.
- To determine the memory layout of a binary (for example: to identify writable memory regions for SROP), use `/proc/{pid}/maps`.
- Prefer reproducible solve scripts with `pwntools`.
- In `pwntools`, set `context.binary`, `context.log_level`, and deterministic timeouts.
- For exploit binaries (example: VM challenges), prefer a smaller binary size.
- For cross-compiled binaries (example: Windows), a Zig bundle is provided.
- When designing ROP chains, think more.
- When designing heap exploitation plans, think more.
- For QEMU work you have the x86 and x86-64 system emulation QEMU binaries (package `qemu-system-x86`) installed. No other architectures are provided due to concerns about container image size. Keep in mind KVM cannot be used.
- You have `pahole` for dumping structure information from DWARF debug info for when precise struct info is needed.

Debugging:
- Your environment has `libdebug` and `gdb` provided.
- Use `libdebug` for Python script-driven debugging instead of directly utilizing `gdb`. You have a skill for libdebug's API reference.
- `gdb` has Pwndbg's suite of additional commands installed (example usecase: determining current heap state).
- The hierarchy of debugging tool usage is:
  - `libdebug` (this should be the default)
  - `gdb` (if `libdebug` encounters problems)

Reverse engineering:
- Use `objdump -d`, `readelf -a`, `nm`, `strings`, and scripting for automation.
- Capture function offsets and notable constants in the README.
- If IDA MCP is available, use it for decompilation and reversing-heavy workflows:
  - `idalib-mcp` default endpoint is `http://127.0.0.1:8745/mcp`.
  - Prefer extracting structured outputs (functions, xrefs, pseudocode) into `/workspace/run`.
  - When working with the IDA MCP, keep in mind that `/workspace/chal` is read-only and autoanalysis will not be able to open the artifact due to it creating files in the same directory. If the autoanalysis fails to open the file, copy the file into `/workspace/run`.
  - If IDA MCP is unavailable for this run, continue with binutils/Ghidra MCP-based reversing and document that fallback.
- A headless Ghidra instance is present and is accessible via `pyghidra-mcp-cli`. If IDA is not available or is suboptimal for the challenge (exotic architecture, decompilation fails on key functions), use Ghidra for decompilation and reversing-heavy workloads.
- If code obfuscation or anti-reverse engineering tooling techniques are suspected **verify decompiler MCP results against binutils-based reversing and document that.**
  - Examples of potential obfuscation/antidebug/anti-RE tooling:
    - Flag computations do not return correct flag
    - Binary behavior changes for no discernible reason between being run under debugger and normally
- For .NET binaries, you have access to `ilspycmd`. You can invoke it via `dotnet ilspycmd`. For NET.Core bundles, you may want to run `dotnet ilspycmd --dump-package` to extract the bundle contents for analysis.

Crypto / forensics:
- Use `pycryptodome` primitives rather than ad-hoc implementations.
- Use `z3-solver` for constraint solving where applicable.
- Validate decoded output assumptions before concluding.
- Prefer `sage` or `sage -python` for algebra, finite fields, ECC, lattices, and modular arithmetic workflows.
- Use `sympy` for symbolic simplification/factoring and equation solving.
- Use `numpy` for matrix/vector-heavy prototypes when exact arithmetic is not required.
- Save math scripts and intermediate outputs to `/workspace/run` and reference them in `result.json` evidence.
- To find AES keys in files/memory dumps when needed, use `aeskeyfind`.

Web / protocol:
- Use `curl`, `wget`, `nc`, `ncat`, `socat` against allowlisted endpoints only.
- Save request/response evidence snippets in `/workspace/run`.
