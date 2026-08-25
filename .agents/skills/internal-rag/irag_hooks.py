#!/usr/bin/env python3
"""Git hook installer for INTERNAL_RAG.

Installs optional Git hooks that call `irag.py`:
  - post-commit:    lightweight checkpoint after each commit (metadata only)
  - post-checkout:  mark checkpoint as STALE so context triggers recovery
  - pre-push:       run `guard` and warn (never block) if stale

Hooks are installed into `.git/hooks/` and are local-only (never tracked).
They are short shell/Python shims that call the project's irag.py.

Usage:
  python .agents/skills/internal-rag/irag_hooks.py install
  python .agents/skills/internal-rag/irag_hooks.py uninstall
  python .agents/skills/internal-rag/irag_hooks.py status

Safe by design: hooks never block git operations. Failures are swallowed.
"""
from __future__ import annotations
import os
import stat
import subprocess
import sys
from pathlib import Path

HOOKS = {
    "post-commit": '''#!/bin/sh
# INTERNAL_RAG auto-checkpoint (post-commit). Local-only, never blocks.
IRAG="$(git rev-parse --show-toplevel 2>/dev/null)/.agents/skills/internal-rag/mlm.py"
if [ -z "$IRAG" ] || [ ! -f "$IRAG" ]; then exit 0; fi
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
"$PY" "$IRAG" checkpoint --reason "git-post-commit" --json >/dev/null 2>&1
exit 0
''',
    "post-checkout": '''#!/bin/sh
# INTERNAL_RAG: invalidate checkpoint fingerprint after checkout/branch switch.
IRAG="$(git rev-parse --show-toplevel 2>/dev/null)/.agents/skills/internal-rag/mlm.py"
if [ -z "$IRAG" ] || [ ! -f "$IRAG" ]; then exit 0; fi
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
FP="$ROOT/INTERNAL_RAG/.fpcache.json"
[ -f "$FP" ] && rm -f "$FP" 2>/dev/null
exit 0
''',
    "pre-push": '''#!/bin/sh
# INTERNAL_RAG: warn (never block) if checkpoint is stale before push.
IRAG="$(git rev-parse --show-toplevel 2>/dev/null)/.agents/skills/internal-rag/mlm.py"
if [ -z "$IRAG" ] || [ ! -f "$IRAG" ]; then exit 0; fi
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
"$PY" "$IRAG" guard >/dev/null 2>&1 || echo "[MCP_LIGHT_MEMORY] checkpoint stale before push; run 'mlm.py checkpoint'." 2>&1
exit 0
''',
}

MARKER = "# INTERNAL_RAG managed hook"


def git_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        return Path(out).resolve()
    except Exception:
        return Path.cwd().resolve()


def hooks_dir(root: Path) -> Path:
    out = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "--git-path", "hooks"], text=True
    ).strip()
    p = Path(out)
    if not p.is_absolute():
        p = root / p
    return p.resolve()


def install() -> int:
    root = git_root()
    hd = hooks_dir(root)
    hd.mkdir(parents=True, exist_ok=True)
    for name, body in HOOKS.items():
        p = hd / name
        if p.exists():
            existing = p.read_text(encoding="utf-8", errors="replace")
            if MARKER not in existing:
                # Append our block to existing hook
                with p.open("a", encoding="utf-8") as f:
                    f.write("\n" + MARKER + "\n" + body)
            else:
                # Replace managed block
                before = existing.split(MARKER, 1)[0].rstrip()
                p.write_text(before + "\n" + MARKER + "\n" + body, encoding="utf-8")
        else:
            p.write_text(MARKER + "\n" + body, encoding="utf-8")
        if os.name != "nt":
            p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"Installed hook: {p.relative_to(root) if str(p).startswith(str(root)) else p}")
    print("Hooks installed (local-only, never block git operations).")
    return 0


def uninstall() -> int:
    root = git_root()
    hd = hooks_dir(root)
    for name in HOOKS:
        p = hd / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if MARKER not in text:
            continue
        before = text.split(MARKER, 1)[0].rstrip()
        if before.strip():
            p.write_text(before + "\n", encoding="utf-8")
            print(f"Removed INTERNAL_RAG block from hook: {name}")
        else:
            p.unlink()
            print(f"Removed hook: {name}")
    return 0


def status() -> int:
    root = git_root()
    hd = hooks_dir(root)
    any_installed = False
    for name in HOOKS:
        p = hd / name
        if p.exists() and MARKER in p.read_text(encoding="utf-8", errors="replace"):
            print(f"  installed: {name}")
            any_installed = True
        else:
            print(f"  not installed: {name}")
    if not any_installed:
        print("No INTERNAL_RAG hooks installed. Run: irag_hooks.py install")
    return 0


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "install":
        return install()
    if action == "uninstall":
        return uninstall()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())