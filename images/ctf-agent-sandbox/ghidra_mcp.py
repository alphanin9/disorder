#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile
import json
import urllib.request
import zipfile
from pathlib import Path


def _which(binary: str) -> str | None:
    return shutil.which(binary)


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ctf-harness-ghidra-mcp"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        with target.open("wb") as handle:
            shutil.copyfileobj(resp, handle)


def _extract(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    name_lower = archive.name.lower()
    if name_lower.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        # Ghidra zips contain a top-level directory, return it.
        children = [p for p in dest.iterdir() if p.is_dir()]
        return children[0] if len(children) == 1 else dest
    if name_lower.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest)
        children = [p for p in dest.iterdir() if p.is_dir()]
        return children[0] if len(children) == 1 else dest
    raise ValueError(f"unsupported archive: {archive}")


def _ensure_ghidra_install(workspace: Path) -> Path:
    """
    Ensure a Ghidra install exists inside the sandbox without requiring host mounts.

    Default behavior:
    - Use GHIDRA_INSTALL_DIR if provided and exists.
    - Else download a pinned public release into /workspace/run/tools/ghidra.
    """
    env_dir = os.getenv("GHIDRA_INSTALL_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.exists():
            return p

    tools_root = workspace / "tools" / "ghidra"
    install_dir = tools_root / "ghidra_install"
    if install_dir.exists():
        return install_dir

    version = os.getenv("GHIDRA_VERSION", "11.1.2")
    url = os.getenv("GHIDRA_URL", "").strip()
    if not url:
        tag = f"Ghidra_{version}_build"
        api_url = f"https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/tags/{tag}"
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "ctf-harness-ghidra-mcp"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            assets = payload.get("assets") if isinstance(payload, dict) else None
            if isinstance(assets, list):
                candidates = []
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    name = str(asset.get("name") or "")
                    dl = str(asset.get("browser_download_url") or "")
                    if not dl or not name:
                        continue
                    if name.lower().endswith(".zip") and f"ghidra_{version}_public".lower() in name.lower():
                        candidates.append(dl)
                if not candidates:
                    for asset in assets:
                        if not isinstance(asset, dict):
                            continue
                        name = str(asset.get("name") or "")
                        dl = str(asset.get("browser_download_url") or "")
                        if name.lower().endswith(".zip") and dl:
                            candidates.append(dl)
                if candidates:
                    url = candidates[0]
        except Exception:
            url = ""

    if not url:
        # Fallback best-effort URL template; override with GHIDRA_URL if it 404s.
        url = f"https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_{version}_build/ghidra_{version}_PUBLIC.zip"

    archive = tools_root / f"ghidra_{version}.zip"
    if not archive.exists():
        _download(url, archive)

    extracted_root = _extract(archive, tools_root / "extract")
    # Normalize to a stable install path.
    if install_dir.exists():
        shutil.rmtree(install_dir, ignore_errors=True)
    extracted_root.rename(install_dir)
    return install_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Wrapper for running a Ghidra MCP server in the sandbox")
    parser.add_argument("--workspace", default="/workspace/run", help="Writable workspace root (default: /workspace/run)")
    args, unknown = parser.parse_known_args()
    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    ghidra_dir = _ensure_ghidra_install(workspace)
    os.environ["GHIDRA_INSTALL_DIR"] = str(ghidra_dir)

    if _which("java") is None:
        print("java not found in sandbox image; install openjdk-17-jre-headless", file=sys.stderr)
        return 2

    entry = _which("pyghidra-mcp")
    if entry is None:
        print("pyghidra-mcp not found in sandbox image; install pyghidra-mcp", file=sys.stderr)
        return 2

    # Delegate MCP protocol to pyghidra-mcp (stdio transport).
    os.execvp(entry, [entry, "stdio", *unknown])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
