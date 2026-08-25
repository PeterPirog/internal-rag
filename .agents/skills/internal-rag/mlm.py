#!/usr/bin/env python3
"""mlm.py — primary CLI entrypoint for MCP Light Memory (mcp-light-memory).

Thin shim that forwards all arguments to the core `irag.py` module, which is
the canonical implementation (the module filename is retained for backward
compatibility with existing installs and stored data).

Usage:
  python mlm.py <command> [args...]      # primary alias
  python irag.py <command> [args...]     # legacy alias (still supported)

Exit codes and stdout/stderr are identical to `irag.py`.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_IRAG = _HERE / "irag.py"


def main() -> int:
    if not _IRAG.exists():
        sys.stderr.write(f"mlm: core module not found at {_IRAG}\n")
        return 2
    # Exec the core module with the same argv (minus the script name).
    # We use os.execv-style replacement so stdout/stderr/exit codes are
    # identical to running irag.py directly.
    argv = [str(_IRAG)] + sys.argv[1:]
    if os.name == "nt":
        # On Windows, os.execv does not preserve the parent's stdout encoding
        # reliably; use subprocess to forward and propagate the exit code.
        import subprocess
        p = subprocess.run([sys.executable] + argv)
        return p.returncode
    os.execv(sys.executable, [sys.executable] + argv)
    return 0  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())