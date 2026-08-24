#!/usr/bin/env python3
"""INTERNAL_RAG CLI - persistent project memory for terminal coding agents.

Zero required dependencies (pure Python 3.8+). Optional embeddings via
irag_embeddings.py (sentence-transformers) if installed.

Subcommands:
  init, context, checkpoint, guard, search, remember, show, update,
  supersede, forget, link, status, diff, timeline, index, validate,
  tasks, resume, forget-task, doctor, export, import, mcp, config,
  embeddings-info
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = "1.3.0"

ALLOWED_TYPES = {"decision", "knowledge", "constraint", "gotcha", "failure", "hypothesis", "session"}
ALLOWED_STATUS = {"active", "tentative", "superseded", "invalid", "archived"}
TYPE_DIR = {
    "decision": "decisions", "knowledge": "knowledge", "constraint": "knowledge",
    "gotcha": "gotchas", "failure": "failures", "hypothesis": "hypotheses", "session": "sessions",
}
SKIP_SEARCH = {"README.md", "INDEX.md", "WORKING_STATE.md"}
INFRA_PREFIXES = (
    "INTERNAL_RAG/", ".agents/skills/internal-rag/", ".opencode/tools/memory-",
    ".opencode/plugins/internal-rag", ".opencode/commands/memory", ".opencode/commands/checkpoint",
)
INFRA_EXACT = {"AGENTS.md"}
DEFAULT_CONFIG = {
    "retrieval": {
        "limit": 8, "mmr_lambda": 0.5, "min_score": 0.5,
        "embeddings": "auto",
        "bm25_k1": 1.5, "bm25_b": 0.75,
        "mode": "hybrid",
        "rrf_k": 60,
        "sparse_weight": 1.0,
        "dense_weight": 1.0,
        "candidate_multiplier": 4,
    },
    "tokens": {"context_budget": 4000, "warn_ratio": 0.8},
    "checkpoints": {"auto_archive_sessions": True, "max_task_stack": 16, "max_age_minutes": 0},
    "privacy": {"scan_on_checkpoint": False},
}


# ----------------------------- paths & git ----------------------------------

def project_root() -> Path:
    p = Path.cwd().resolve()
    try:
        out = subprocess.check_output(
            ["git", "-C", str(p), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return p


ROOT = project_root()
RAG = ROOT / "INTERNAL_RAG"
WORKING = RAG / "WORKING_STATE.md"
CHECKPOINT = RAG / ".checkpoint.json"
TASKS = RAG / ".tasks.json"
CONFIG_PATH = ROOT / ".irag.yml"
FP_CACHE = RAG / ".fpcache.json"
EXPORT_DIR = RAG / "exports"


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return dt.date.today().isoformat()


def git(*args: str, binary: bool = False) -> Any:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), *args],
            stderr=subprocess.DEVNULL, text=not binary,
        )
    except Exception:
        return b"" if binary else ""


def git_text(*args: str) -> str:
    x = git(*args)
    return x.strip() if isinstance(x, str) else ""


def norm(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def infra(p: str) -> bool:
    p = norm(p)
    return p in INFRA_EXACT or any(p.startswith(x) for x in INFRA_PREFIXES)


# ----------------------------- config ---------------------------------------

def load_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            cfg = parse_yaml_simple(CONFIG_PATH.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            cfg = {}
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def parse_yaml_simple(text: str) -> Dict[str, Any]:
    """Tiny YAML subset: top-level key: value and nested key: value under 2-space indent.
    Lists not supported in config (keep simple). Falls back to JSON if YAML parse empty."""
    out: Dict[str, Any] = {}
    cur: Optional[str] = None
    for line in text.splitlines():
        s = line.rstrip()
        if not s or s.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", s.strip())
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if indent == 0:
            if v == "":
                out[k] = {}
                cur = k
            else:
                out[k] = coerce_scalar(v)
                cur = None
        else:
            if cur is None:
                continue
            if not isinstance(out.get(cur), dict):
                out[cur] = {}
            out[cur][k] = coerce_scalar(v)
    if not out:
        try:
            return json.loads(text)
        except Exception:
            return {}
    return out


def coerce_scalar(v: str) -> Any:
    if v in ("true", "True"):
        return True
    if v in ("false", "False"):
        return False
    if v in ("null", "~", "None"):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v.strip("\"'")


# ----------------------------- fingerprint ----------------------------------

def tracked_diff_hash(h: hashlib._Hash, cached: bool = False) -> None:
    cmd = ["git", "-C", str(ROOT), "diff", "--binary", "--no-ext-diff"]
    if cached:
        cmd.append("--cached")
    cmd += ["--", ".", ":(exclude)INTERNAL_RAG/**", ":(exclude)AGENTS.md",
            ":(exclude).agents/skills/internal-rag/**", ":(exclude).opencode/tools/memory-*",
            ":(exclude).opencode/plugins/internal-rag*", ":(exclude).opencode/commands/memory*",
            ":(exclude).opencode/commands/checkpoint*"]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        assert p.stdout is not None
        while True:
            chunk = p.stdout.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
        p.wait()
    except Exception:
        h.update(b"DIFF_ERROR")


def untracked_files() -> List[str]:
    raw = git("ls-files", "--others", "--exclude-standard", "-z", binary=True)
    if not raw:
        return []
    return [norm(x) for x in raw.decode("utf-8", errors="replace").split("\0") if x and not infra(x)]


def project_fingerprint(use_cache: bool = True) -> str:
    head = git_text("rev-parse", "HEAD")
    key = f"head={head}"
    if use_cache and FP_CACHE.exists():
        try:
            cache = json.loads(FP_CACHE.read_text(encoding="utf-8"))
            if cache.get("key") == key:
                cur_mtime = max((_safe_mtime(ROOT / f) for f in untracked_files()), default=0)
                if cache.get("untracked_mtime", 0) >= cur_mtime:
                    return cache["fingerprint"]
        except Exception:
            pass
    h = hashlib.sha256()
    h.update(head.encode())
    tracked_diff_hash(h, False)
    tracked_diff_hash(h, True)
    untracked = untracked_files()
    for rel in sorted(untracked):
        h.update(rel.encode())
        p = ROOT / rel
        try:
            if p.is_file():
                with p.open("rb") as f:
                    while True:
                        c = f.read(1024 * 1024)
                        if not c:
                            break
                        h.update(c)
        except Exception:
            h.update(b"ERR")
    fp = h.hexdigest()
    try:
        FP_CACHE.write_text(json.dumps({
            "key": key, "fingerprint": fp,
            "untracked_mtime": max((_safe_mtime(ROOT / f) for f in untracked), default=0),
            "at": now(),
        }, indent=2), encoding="utf-8")
    except Exception:
        pass
    return fp


def _safe_mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except Exception:
        return 0.0


def changed_entries() -> List[Tuple[str, str]]:
    raw = git("status", "--porcelain=v1", "-z", "-uall", binary=True)
    if not raw:
        return []
    parts = raw.decode("utf-8", errors="replace").split("\0")
    out: List[Tuple[str, str]] = []
    i = 0
    while i < len(parts):
        rec = parts[i]
        i += 1
        if not rec or len(rec) < 4:
            continue
        st = rec[:2]
        path = norm(rec[3:])
        if "R" in st or "C" in st:
            if i < len(parts) and parts[i]:
                old = norm(parts[i])
                i += 1
                if not infra(old):
                    out.append((st + ":old", old))
        if not infra(path):
            out.append((st, path))
    seen = set()
    result = []
    for x in out:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result


# ----------------------------- token estimation -----------------------------

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars/token for code/English, ~0.6 words/token."""
    if not text:
        return 0
    words = len(re.findall(r"\S+", text))
    chars = len(text)
    return max(int(chars / 4), int(words / 0.85))


# ----------------------------- working state --------------------------------

def default_working() -> str:
    return (
        f"# Current Working State\n\n"
        f"updated: {now()}\n"
        f"branch: {git_text('branch', '--show-current') or 'unknown'}\n"
        f"base_commit: {git_text('rev-parse', '--short', 'HEAD') or 'unknown'}\n\n"
        "## Objective\n\nNo active objective yet.\n\n"
        "## Current request\n\nNone.\n\n"
        "## Current phase\n\nIdle.\n\n"
        "## Completed\n\n- None.\n\n"
        "## In progress\n\n- None.\n\n"
        "## Blockers\n\n- None.\n\n"
        "## Important active decisions\n\n- None.\n\n"
        "## Relevant files\n\n- None.\n\n"
        "## Next actions\n\n1. Define the task.\n\n"
        "## Checkpoint health\n\n- No task has started.\n\n"
        "## Recovery snapshot\n\n- None.\n\n"
        "## Memory to retrieve if needed\n\n- None.\n"
    )


def get_section(text: str, name: str) -> str:
    m = re.search(rf"(?ms)^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)", text)
    return m.group(1).strip() if m else ""


def set_section(text: str, name: str, body: str) -> str:
    body = body.strip() or "- None."
    pat = rf"(?ms)^## {re.escape(name)}\s*\n.*?(?=^## |\Z)"
    repl = f"## {name}\n\n{body}\n\n"
    if re.search(pat, text):
        return re.sub(pat, repl, text).rstrip() + "\n"
    return text.rstrip() + f"\n\n{repl}"


def set_header(text: str, key: str, value: str) -> str:
    pat = rf"(?m)^{re.escape(key)}:.*$"
    if re.search(pat, text):
        return re.sub(pat, f"{key}: {value}", text)
    marker = "# Current Working State\n"
    if text.startswith(marker):
        return marker + f"\n{key}: {value}\n" + text[len(marker):].lstrip("\n")
    return f"{key}: {value}\n" + text


def save_working(text: str) -> None:
    RAG.mkdir(exist_ok=True)
    WORKING.write_text(text.rstrip() + "\n", encoding="utf-8")


CHECKPOINT_SCHEMA = 2
TASKS_SCHEMA = 2
HISTORY_FILE = RAG / ".history.jsonl"
_HISTORY_MAX = 100


def _append_history(entry: Dict[str, Any]) -> None:
    try:
        RAG.mkdir(exist_ok=True)
        with HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        lines = HISTORY_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > _HISTORY_MAX:
            HISTORY_FILE.write_text("\n".join(lines[-_HISTORY_MAX:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def load_checkpoint() -> Dict[str, Any]:
    try:
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_checkpoint(reason: str) -> Dict[str, Any]:
    data = {
        "schema": CHECKPOINT_SCHEMA,
        "version": VERSION, "at": now(), "reason": reason,
        "fingerprint": project_fingerprint(), "branch": git_text("branch", "--show-current"),
        "head": git_text("rev-parse", "--short", "HEAD"),
    }
    CHECKPOINT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _append_history({"at": data["at"], "reason": reason, "head": data["head"],
                     "fingerprint": data["fingerprint"][:16], "branch": data["branch"]})
    return data


def history_cmd(args) -> int:
    if not HISTORY_FILE.exists():
        if args.json:
            print("[]")
        else:
            print("No checkpoint history yet.")
        return 0
    entries = []
    for line in HISTORY_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    entries = entries[::-1]
    if args.limit and args.limit > 0:
        entries = entries[: args.limit]
    if args.json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return 0
    if not entries:
        print("No checkpoint history yet.")
        return 0
    for e in entries:
        print(f"{e.get('at', '?')}  [{e.get('reason', '?')}]  head={e.get('head', '?')}  fp={e.get('fingerprint', '?')}")
    return 0


# ----------------------------- init -----------------------------------------

def init_repo() -> None:
    existed = WORKING.exists()
    RAG.mkdir(exist_ok=True)
    for d in ["decisions", "knowledge", "gotchas", "failures", "hypotheses", "sessions", "archive"]:
        (RAG / d).mkdir(exist_ok=True)
    if not existed:
        save_working(default_working())
        save_checkpoint("init")
    rebuild_index()
    print(f"Initialized INTERNAL_RAG (irag {VERSION})")


# ----------------------------- listify --------------------------------------

def listify(s: Optional[str], numbered: bool = False) -> Optional[str]:
    if s is None:
        return None
    xs = [x.strip() for x in s.split(";") if x.strip()]
    if not xs:
        return "- None."
    return "\n".join((f"{i}. {x}" if numbered else f"- {x}") for i, x in enumerate(xs, 1))


# ----------------------------- checkpoint -----------------------------------

def checkpoint(args) -> None:
    if not WORKING.exists():
        init_repo()
    text = WORKING.read_text(encoding="utf-8", errors="replace")
    if args.task:
        text = set_section(text, "Current request", args.task)
    if args.objective:
        text = set_section(text, "Objective", args.objective)
    if args.phase:
        text = set_section(text, "Current phase", args.phase)
    for arg, sec, num in [
        ("completed", "Completed", False), ("in_progress", "In progress", False),
        ("blockers", "Blockers", False), ("decisions", "Important active decisions", False),
        ("next", "Next actions", True), ("memory", "Memory to retrieve if needed", False),
    ]:
        v = listify(getattr(args, arg), num)
        if v is not None:
            text = set_section(text, sec, v)
    entries = changed_entries()
    files = "\n".join(f"- `{s}` {p}" for s, p in entries[:50]) or "- No project-code changes detected."
    if len(entries) > 50:
        files += f"\n- ... {len(entries) - 50} more"
    text = set_section(text, "Relevant files", files)
    text = set_section(text, "Recovery snapshot",
                       f"- Checkpoint reason: {args.reason}\n"
                       f"- Branch: {git_text('branch', '--show-current') or 'unknown'}\n"
                       f"- HEAD: {git_text('rev-parse', '--short', 'HEAD') or 'unknown'}\n{files}")
    text = set_section(text, "Checkpoint health",
                       "- CHECKPOINT CURRENT at save time.\n- Run `irag.py guard` before final response.")
    text = set_header(text, "updated", now())
    text = set_header(text, "branch", git_text("branch", "--show-current") or "unknown")
    text = set_header(text, "base_commit", git_text("rev-parse", "--short", "HEAD") or "unknown")
    save_working(text)
    data = save_checkpoint(args.reason)
    if load_config().get("checkpoints", {}).get("auto_archive_sessions", True):
        _maybe_archive_session(args.reason)
    if args.json:
        print(json.dumps({"status": "ok", "fingerprint": data["fingerprint"][:16],
                          "changed_paths": len(entries), "reason": args.reason}, indent=2))
        return
    print("CHECKPOINT SAVED")
    print("reason:", args.reason)
    print("fingerprint:", data["fingerprint"][:16])
    print("changed_paths:", len(entries))


def _maybe_archive_session(reason: str) -> None:
    """Archive the previous WORKING_STATE into sessions/.snapshots/ on milestones.
    Snapshots are raw WORKING_STATE copies, not durable memories, so they live
    outside the memory_files() scan."""
    if reason in ("init", "install-init", "recovery-init"):
        return
    try:
        sess = RAG / "sessions" / ".snapshots"
        sess.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = sess / f"session-{stamp}-{slugify(reason)[:40]}.md"
        if WORKING.exists():
            target.write_text(WORKING.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass


# ----------------------------- context --------------------------------------

def context(args) -> int:
    task = args.task
    limit = args.limit
    if not WORKING.exists():
        init_repo()
    cfg = load_config()
    text = WORKING.read_text(encoding="utf-8", errors="replace")
    cp = load_checkpoint()
    cur = project_fingerprint()
    saved = cp.get("fingerprint")
    recovery = (not saved) or saved != cur
    text = set_section(text, "Current request", task)
    if get_section(text, "Objective") in ("", "No active objective yet.", "None.", "- None."):
        text = set_section(text, "Objective", task)
    # G5: checkpoint age warning
    age_warn = ""
    cp_at = cp.get("at", "")
    if cp_at:
        try:
            cp_dt = dt.datetime.fromisoformat(cp_at)
            age_min = (dt.datetime.now().astimezone() - cp_dt).total_seconds() / 60.0
            max_age = float(cfg.get("checkpoints", {}).get("max_age_minutes", 0) or 0)
            if max_age and age_min > max_age:
                age_warn = f"\n- WARNING: last checkpoint was {int(age_min)} min ago (max_age_minutes={int(max_age)})."
        except Exception:
            pass
    health = (
        "- RECOVERY REQUIRED: project code differs from the last checkpoint.\n"
        "- Inspect `git status` and `git diff`, reconstruct state, checkpoint it, then run guard."
        if recovery else
        "- Checkpoint fingerprint matches current project state.\n"
        "- Create a task-start checkpoint before the first new code edit."
    ) + age_warn
    text = set_section(text, "Checkpoint health", health)
    text = set_header(text, "updated", now())
    save_working(text)
    types_f = getattr(args, "type", None)
    statuses_f = getattr(args, "status", None)
    expanded = expand_query(task)
    results = search(expanded, limit, types=types_f, statuses=statuses_f)
    ws_text = WORKING.read_text(encoding="utf-8", errors="replace")
    ws_tokens = estimate_tokens(ws_text)
    budget = int(cfg.get("tokens", {}).get("context_budget", 4000))
    # G1: token budget enforcement — sort by score, cut to budget
    results.sort(key=lambda x: -x[0])
    kept: List[Tuple[float, Path, Dict[str, Any], str]] = []
    used = ws_tokens
    dropped = 0
    for score, p, fm, sn in results:
        sn_t = estimate_tokens(sn)
        if used + sn_t > budget:
            dropped += 1
            continue
        kept.append((score, p, fm, sn))
        used += sn_t
    mem_tokens = used - ws_tokens
    # G6: recent git log
    git_log = ""
    try:
        raw = git("log", "--oneline", "-5", "--no-decorate")
        if raw:
            lines = [l.strip() for l in raw.splitlines() if l.strip()][:5]
            git_log = "\n".join(f"- {l}" for l in lines)
    except Exception:
        pass
    if args.json:
        out = {
            "irag_version": VERSION, "task": task,
            "recovery_required": bool(recovery),
            "working_state": ws_text[:10000],
            "working_state_tokens": ws_tokens,
            "candidate_memories": [
                {"path": str(p.relative_to(ROOT)), "type": fm.get("type", "?"),
                 "status": fm.get("status", "?"), "score": round(score, 2), "snippet": sn}
                for score, p, fm, sn in kept
            ],
            "memory_tokens": mem_tokens,
            "context_budget": budget,
            "memories_dropped_for_budget": dropped,
            "recent_commits": [l for l in git_log.splitlines() if l.strip()],
            "next": "RECOVER -> CHECKPOINT -> GUARD OK -> continue." if recovery
                    else "Checkpoint before first code edit, then continue.",
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    print("# INTERNAL_RAG CONTEXT PACKET")
    print("irag_version:", VERSION)
    print("task:", task)
    print("recovery_required:", "YES" if recovery else "NO")
    print(f"tokens: working_state={ws_tokens} memories={mem_tokens} budget={budget}"
          + (f" dropped={dropped}" if dropped else ""))
    if recovery:
        print("\n!!! RECOVERY REQUIRED !!!\nInspect git status/diff and checkpoint recovered state BEFORE new edits.")
    print("\n## WORKING_STATE\n" + ws_text[:10000].rstrip())
    if git_log:
        print("\n## RECENT COMMITS\n" + git_log)
    print("\n## CANDIDATE MEMORIES")
    if not kept:
        print("No relevant durable memories found.")
    grouped: Dict[str, List[Tuple[float, Path, Dict[str, Any], str]]] = {}
    for score, p, fm, snip in kept:
        mtype = str(fm.get("type", "other"))
        grouped.setdefault(mtype, []).append((score, p, fm, snip))
    type_order = ["decision", "knowledge", "constraint", "gotcha", "failure", "hypothesis", "session", "other"]
    i = 0
    for mtype in type_order:
        items = grouped.get(mtype, [])
        if not items:
            continue
        label = mtype.upper() if mtype != "other" else "OTHER"
        if mtype in ("decision", "knowledge", "constraint"):
            print(f"\n### Verified facts ({label})")
        elif mtype in ("gotcha", "failure"):
            print(f"\n### Lessons & pitfalls ({label})")
        elif mtype == "hypothesis":
            print(f"\n### Unverified hypotheses ({label}) — treat as tentative")
        else:
            print(f"\n### {label}")
        for score, p, fm, snip in items:
            i += 1
            print(f"{i}. {p.relative_to(ROOT)} [{fm.get('type','?')}/{fm.get('status','?')}] score={score:.1f}")
            print(f"   {snip}")
    if dropped:
        print(f"\n({dropped} memory result(s) dropped to fit token budget)")
    print("\n## NEXT")
    print("RECOVER -> CHECKPOINT -> GUARD OK -> continue." if recovery
          else "Checkpoint before first code edit, then continue.")
    return 0


# ----------------------------- guard ----------------------------------------

def guard() -> int:
    cp = load_checkpoint()
    saved = cp.get("fingerprint")
    cur = project_fingerprint(use_cache=False)
    if not saved:
        print("GUARD STALE: no checkpoint fingerprint.")
        return 2
    if saved != cur:
        print("GUARD STALE: project code changed after the last checkpoint.")
        for s, p in changed_entries()[:40]:
            print(f"- `{s}` {p}")
        return 2
    # G5: checkpoint age warning (non-blocking)
    cfg = load_config()
    cp_at = cp.get("at", "")
    if cp_at:
        try:
            cp_dt = dt.datetime.fromisoformat(cp_at)
            age_min = (dt.datetime.now().astimezone() - cp_dt).total_seconds() / 60.0
            max_age = float(cfg.get("checkpoints", {}).get("max_age_minutes", 0) or 0)
            if max_age and age_min > max_age:
                print(f"GUARD OK (WARNING: last checkpoint {int(age_min)} min ago, max_age_minutes={int(max_age)})")
                print("fingerprint:", cur[:16])
                return 0
        except Exception:
            pass
    print("GUARD OK")
    print("fingerprint:", cur[:16])
    return 0


# ----------------------------- memory: frontmatter --------------------------

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:72] or "memory"


def parse_fm(text: str) -> Dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    data: Dict[str, Any] = {}
    current: Optional[str] = None
    for raw in text[4:end].splitlines():
        if re.match(r"^\s+-\s+", raw) and current:
            data.setdefault(current, []).append(re.sub(r"^\s+-\s+", "", raw).strip())
            continue
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", raw)
        if m:
            k, v = m.group(1), m.group(2).strip()
            current = None
            if not v:
                data[k] = []
                current = k
            else:
                data[k] = v.strip("\"'")
    return data


def write_fm(fm: Dict[str, Any]) -> str:
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            else:
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def memory_files() -> List[Path]:
    if not RAG.exists():
        return []
    out = []
    for p in RAG.rglob("*.md"):
        if "archive" in p.parts:
            continue
        if p.name in SKIP_SEARCH:
            continue
        if "sessions" in p.parts and ".snapshots" in p.parts:
            continue
        out.append(p)
    return sorted(out)


def find_memory_by_id_or_path(ref: str) -> Optional[Path]:
    """Resolve a memory reference: relative path, basename, or id."""
    if not ref:
        return None
    ref_norm = ref.replace("\\", "/").lstrip("./")
    direct = ROOT / ref_norm
    if direct.is_file():
        return direct
    candidates = memory_files()
    for p in candidates:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if rel == ref_norm or p.name == ref_norm:
            return p
    for p in candidates:
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_fm(text)
        if str(fm.get("id", "")) == ref:
            return p
    stem = Path(ref_norm).stem
    for p in candidates:
        if p.stem == stem:
            return p
    return None


# ----------------------------- retrieval: BM25 + MMR ------------------------

SYNONYMS: List[Tuple[str, str]] = [
    ("database", "db"), ("db", "database"),
    ("config", "configuration"), ("configuration", "config"),
    ("auth", "authentication"), ("authentication", "auth"),
    ("api", "endpoint"), ("endpoint", "api"),
    ("test", "testing"), ("testing", "test"),
    ("deploy", "deployment"), ("deployment", "deploy"),
    ("perf", "performance"), ("performance", "perf"),
    ("refactor", "refactoring"), ("refactoring", "refactor"),
    ("bug", "defect"), ("defect", "bug"),
    ("cache", "caching"), ("caching", "cache"),
    ("error", "exception"), ("exception", "error"),
    ("async", "asynchronous"), ("asynchronous", "async"),
    ("sync", "synchronous"), ("synchronous", "sync"),
    ("migration", "migrate"), ("migrate", "migration"),
    ("schema", "model"), ("model", "schema"),
    ("route", "endpoint"), ("handler", "controller"),
    ("session", "cookie"), ("token", "jwt"),
    ("redis", "cache"), ("postgres", "database"),
    ("docker", "container"), ("kubernetes", "k8s"),
    ("react", "frontend"), ("vue", "frontend"),
    ("pytest", "test"), ("unittest", "test"),
    ("ssl", "tls"), ("https", "tls"),
    ("env", "environment"), ("var", "variable"),
    ("cron", "scheduler"), ("queue", "worker"),
    ("lint", "linter"), ("format", "formatter"),
]


def expand_query(query: str) -> str:
    """Expand query with synonyms for better recall."""
    tokens = re.findall(r"[A-Za-z0-9_./:@+-]{2,}", query.lower())
    extra: List[str] = []
    for tok in tokens:
        for src, dst in SYNONYMS:
            if tok == src and dst not in tokens and dst not in extra:
                extra.append(dst)
    if not extra:
        return query
    return query + " " + " ".join(extra)


STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "for", "of", "to", "in", "on",
    "at", "by", "with", "from", "is", "are", "was", "were", "be", "been", "being", "this", "that",
    "these", "those", "it", "its", "as", "not", "no", "do", "does", "did", "will", "would", "can",
    "could", "should", "shall", "may", "might", "must", "have", "has", "had", "i", "you", "he",
    "she", "we", "they", "them", "his", "her", "their", "our", "your", "my", "me", "us",
    "how", "what", "when", "where", "why", "who", "which", "whose", "about", "into", "out",
    "up", "down", "over", "under", "again", "more", "most", "some", "any", "all", "each",
    "few", "other", "such", "own", "same", "so", "than", "too", "very", "just", "also",
    "use", "used", "using", "get", "set", "new", "one", "two", "via", "like", "etc",
}


def tokenize(text: str) -> List[str]:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    raw = re.findall(r"[a-z0-9_./:@+-]{2,}", text)
    out: List[str] = []
    for tok in raw:
        if tok in STOPWORDS:
            continue
        if len(tok) < 3 and not tok.isdigit():
            continue
        out.append(tok)
        if tok.endswith("s") and len(tok) > 4:
            out.append(tok[:-1])
        if tok.endswith("ing") and len(tok) > 6:
            out.append(tok[:-3])
        if tok.endswith("ed") and len(tok) > 5:
            out.append(tok[:-2])
    return out


TYPE_PRIORITY = {
    "decision": 0.8, "knowledge": 0.6, "constraint": 0.5,
    "gotcha": 0.4, "failure": 0.3, "hypothesis": 0.2, "session": 0.1,
}


def recency_boost(fm: Dict[str, Any]) -> float:
    """H1: Small score boost for recently created/updated memories."""
    date_str = str(fm.get("updated") or fm.get("created") or "")
    if not date_str:
        return 0.0
    try:
        mem_date = dt.date.fromisoformat(date_str[:10])
    except Exception:
        return 0.0
    age_days = (dt.date.today() - mem_date).days
    if age_days < 0:
        age_days = 0
    if age_days <= 7:
        return 0.3
    if age_days <= 30:
        return 0.1
    return 0.0


def bm25_idf(term: str, df_map: Dict[str, int], n_docs: int) -> float:
    """Standard BM25 IDF: log(1 + (N - df + 0.5) / (df + 0.5)).
    Always non-negative. Returns 0 for terms not in corpus."""
    df = df_map.get(term, 0)
    if df == 0:
        return 0.0
    return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))


def bm25_term_score(term: str, tf: int, doc_len: int, avgdl: float,
                    idf_val: float, k1: float, b: float) -> float:
    """BM25 term-document score component."""
    if tf == 0 or avgdl <= 0:
        return 0.0
    denom = tf * (k1 + 1) / (tf + k1 * (1 - b + b * doc_len / avgdl))
    return idf_val * denom


def bm25_doc_score(q_tokens: List[str], doc_tokens: List[str],
                   df_map: Dict[str, int], n_docs: int, avgdl: float,
                   k1: float, b: float) -> Tuple[float, List[str]]:
    """Score a single document against query tokens.
    Returns (score, matched_tokens)."""
    if not doc_tokens or avgdl <= 0:
        return 0.0, []
    tf: Dict[str, int] = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    matched: List[str] = []
    for t in q_tokens:
        if t in tf:
            idf_val = bm25_idf(t, df_map, n_docs)
            if idf_val <= 0:
                continue
            matched.append(t)
            score += bm25_term_score(t, tf[t], len(doc_tokens), avgdl, idf_val, k1, b)
    return score, matched


def bm25_search(query: str, candidates: List[Tuple[Path, str, Dict[str, Any]]],
                limit: int, cfg: Dict[str, Any]) -> List[Tuple[float, Path, Dict[str, Any], str, List[str]]]:
    r_cfg = cfg.get("retrieval", {})
    k1 = float(r_cfg.get("bm25_k1", 1.5))
    b = float(r_cfg.get("bm25_b", 0.75))
    q_tokens = tokenize(query)
    if not q_tokens:
        q_tokens = re.findall(r"[A-Za-z0-9_./:@+-]{2,}", query.lower())
    docs_tok: List[List[str]] = []
    for p, text, fm in candidates:
        header = "\n".join(text.splitlines()[:40])
        body = "\n".join(text.splitlines())
        rel = str(p.relative_to(ROOT))
        combined = f"{rel}\n{header}\n{body}"
        docs_tok.append(tokenize(combined))
    N = len(docs_tok)
    if N == 0:
        return []
    avgdl = sum(len(d) for d in docs_tok) / N
    df: Dict[str, int] = {}
    for d in docs_tok:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    scored: List[Tuple[float, int, List[str]]] = []
    for i, d in enumerate(docs_tok):
        score, matched = bm25_doc_score(q_tokens, d, df, N, avgdl, k1, b)
        if score <= 0:
            continue
        fm = candidates[i][2]
        status = str(fm.get("status", "active")).lower()
        if status == "active":
            score += 1.0
        elif status == "tentative":
            score += 0.6
        elif status == "superseded":
            score -= 4.0
        elif status in ("invalid", "archived"):
            score -= 100.0
        mtype = str(fm.get("type", "")).lower()
        score += TYPE_PRIORITY.get(mtype, 0.0)
        score += recency_boost(fm)
        if score > 0:
            scored.append((score, i, matched))
    scored.sort(key=lambda x: -x[0])
    top = scored[: min(limit * 4, len(scored))]
    min_score = float(r_cfg.get("min_score", 0.5))
    top = [x for x in top if x[0] >= min_score]
    lam = float(r_cfg.get("mmr_lambda", 0.5))
    selected = mmr_rerank(top, docs_tok, lam, limit)
    out = []
    for score, i, matched in selected:
        p, text, fm = candidates[i]
        snip = " ".join(text.split())[:420]
        out.append((score, p, fm, snip, matched))
    return out


def mmr_rerank(scored: List[Tuple[float, int, List[str]]],
               docs_tok: List[List[str]], lam: float, limit: int
               ) -> List[Tuple[float, int, List[str]]]:
    if not scored:
        return []
    if len(scored) <= limit:
        return scored
    selected: List[Tuple[float, int, List[str]]] = [scored[0]]
    remaining = list(scored[1:])
    while remaining and len(selected) < limit:
        best = None
        best_val = -1e18
        best_idx = 0
        for idx, (sc, i, matched) in enumerate(remaining):
            max_sim = 0.0
            sel_toks = [set(docs_tok[j[1]]) for j in selected]
            cur_set = set(docs_tok[i])
            for st in sel_toks:
                inter = len(cur_set & st)
                union = len(cur_set | st) or 1
                sim = inter / union
                if sim > max_sim:
                    max_sim = sim
            mmr = lam * sc - (1 - lam) * max_sim
            if mmr > best_val:
                best_val = mmr
                best = (sc, i, matched)
                best_idx = idx
        if best is None:
            break
        selected.append(best)
        remaining.pop(best_idx)
    return selected


def embeddings_search(query: str, candidates: List[Tuple[Path, str, Dict[str, Any]]],
                      limit: int, cfg: Dict[str, Any]
                      ) -> Optional[List[Tuple[float, Path, Dict[str, Any], str, List[str]]]]:
    """Legacy interface — full embeddings search with policy boosts.
    Kept for backward compatibility. New hybrid pipeline uses dense_search_raw."""
    mode = str(cfg.get("retrieval", {}).get("embeddings", "auto")).lower()
    if mode in ("off", "no", "false", "0"):
        return None
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "irag_embeddings", str(ROOT / ".agents" / "skills" / "internal-rag" / "irag_embeddings.py"))
        if spec is None or spec.loader is None:
            return None
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.embeddings_search(query, candidates, limit, cfg, ROOT)
    except Exception:
        return None


def _dense_search_raw(query: str, candidates: List[Tuple[Path, str, Dict[str, Any]]],
                      cfg: Dict[str, Any]) -> Optional[List[Tuple[float, int]]]:
    """Raw dense retrieval: (cosine_sim, candidate_idx) sorted desc.
    Returns None if unavailable."""
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "irag_embeddings", str(ROOT / ".agents" / "skills" / "internal-rag" / "irag_embeddings.py"))
        if spec is None or spec.loader is None:
            return None
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.dense_search_raw(query, candidates, cfg, ROOT)
    except Exception:
        return None


def _dense_similarity_matrix(candidate_indices: List[int],
                              candidates: List[Tuple[Path, str, Dict[str, Any]]],
                              cfg: Dict[str, Any]) -> Optional[Any]:
    """Compute pairwise cosine similarity matrix for MMR diversity.
    Returns numpy matrix or None."""
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "irag_embeddings", str(ROOT / ".agents" / "skills" / "internal-rag" / "irag_embeddings.py"))
        if spec is None or spec.loader is None:
            return None
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.dense_similarity_matrix(candidate_indices, candidates, cfg, ROOT)
    except Exception:
        return None


# ----------------------------- RRF Fusion -----------------------------------

def rrf_fusion(sparse_ranked: List[Tuple[float, int, List[str]]],
               dense_ranked: Optional[List[Tuple[float, int]]],
               rrf_k: float,
               sparse_weight: float,
               dense_weight: float
               ) -> List[Tuple[float, int, Dict[str, Any]]]:
    """Reciprocal Rank Fusion.

    fused(doc) = sparse_weight/(rrf_k + sparse_rank) + dense_weight/(rrf_k + dense_rank)

    Returns list of (fused_score, candidate_idx, explain_dict) sorted by fused_score desc.
    """
    sparse_map: Dict[int, Tuple[int, float]] = {}  # idx -> (rank, score)
    for rank, (score, idx, matched) in enumerate(sparse_ranked):
        sparse_map[idx] = (rank, score)

    dense_map: Dict[int, Tuple[int, float]] = {}
    if dense_ranked:
        for rank, (score, idx) in enumerate(dense_ranked):
            dense_map[idx] = (rank, score)

    all_indices = set(sparse_map.keys()) | set(dense_map.keys())
    fused: List[Tuple[float, int, Dict[str, Any]]] = []
    for idx in all_indices:
        rrf_score = 0.0
        sparse_rank = None
        sparse_score = None
        dense_rank = None
        dense_score = None
        if idx in sparse_map:
            sr, ss = sparse_map[idx]
            sparse_rank = sr
            sparse_score = ss
            rrf_score += sparse_weight / (rrf_k + sr)
        if idx in dense_map:
            dr, ds = dense_map[idx]
            dense_rank = dr
            dense_score = ds
            rrf_score += dense_weight / (rrf_k + dr)
        explain = {
            "sparse_score": round(sparse_score, 4) if sparse_score is not None else None,
            "sparse_rank": sparse_rank,
            "dense_score": round(dense_score, 4) if dense_score is not None else None,
            "dense_rank": dense_rank,
            "rrf_score": round(rrf_score, 6),
        }
        fused.append((rrf_score, idx, explain))
    fused.sort(key=lambda x: -x[0])
    return fused


def _policy_boost(fm: Dict[str, Any]) -> float:
    """Status + type + recency boost applied after fusion."""
    boost = 0.0
    status = str(fm.get("status", "active")).lower()
    if status == "active":
        boost += 1.0
    elif status == "tentative":
        boost += 0.6
    elif status == "superseded":
        boost -= 4.0
    elif status in ("invalid", "archived"):
        boost -= 100.0
    mtype = str(fm.get("type", "")).lower()
    boost += TYPE_PRIORITY.get(mtype, 0.0)
    boost += recency_boost(fm)
    return boost


def _mmr_post_fusion(fused: List[Tuple[float, int, Dict[str, Any]]],
                     candidates: List[Tuple[Path, str, Dict[str, Any]]],
                     docs_tok: List[List[str]],
                     cfg: Dict[str, Any],
                     limit: int
                     ) -> List[Tuple[float, int, Dict[str, Any]]]:
    """MMR reranking after fusion. Uses dense cosine similarity for diversity
    if embeddings available, otherwise token-Jaccard fallback."""
    if not fused:
        return []
    if len(fused) <= limit:
        return fused
    lam = float(cfg.get("retrieval", {}).get("mmr_lambda", 0.5))

    # Try dense similarity for MMR diversity
    candidate_indices = [idx for _, idx, _ in fused]
    dense_sim = _dense_similarity_matrix(candidate_indices, candidates, cfg)

    selected: List[Tuple[float, int, Dict[str, Any]]] = [fused[0]]
    remaining = list(fused[1:])
    while remaining and len(selected) < limit:
        best = None
        best_val = -1e18
        best_idx = 0
        for idx_pos, (rrf_sc, cand_idx, explain) in enumerate(remaining):
            max_sim = 0.0
            if dense_sim is not None:
                # Use dense cosine similarity
                cur_pos = candidate_indices.index(cand_idx)
                for sel in selected:
                    sel_pos = candidate_indices.index(sel[1])
                    sim = float(dense_sim[cur_pos][sel_pos])
                    if sim > max_sim:
                        max_sim = sim
            else:
                # Fallback: token-Jaccard
                cur_set = set(docs_tok[cand_idx])
                for sel in selected:
                    sel_set = set(docs_tok[sel[1]])
                    inter = len(cur_set & sel_set)
                    union = len(cur_set | sel_set) or 1
                    sim = inter / union
                    if sim > max_sim:
                        max_sim = sim
            mmr = lam * rrf_sc - (1 - lam) * max_sim
            if mmr > best_val:
                best_val = mmr
                best = (rrf_sc, cand_idx, explain)
                best_idx = idx_pos
        if best is None:
            break
        selected.append(best)
        remaining.pop(best_idx)
    return selected


def _mark_accessed_db(mem_ids: List[str]) -> None:
    """Record access in SQLite usage table (does NOT modify Markdown)."""
    idx = _open_sqlite_index()
    if idx is None:
        return
    try:
        for mid in mem_ids:
            idx.record_access(mid)
    except Exception:
        pass
    finally:
        idx.close()


def _mark_accessed(paths: List[Path]) -> None:
    """Legacy: write last_accessed to frontmatter. Kept for migrate-usage only.
    Search/context no longer call this — use _mark_accessed_db instead."""
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            fm = parse_fm(text)
            fm["last_accessed"] = today()
            body_start = text.find("\n---", 4)
            body = text[body_start + 4:].lstrip("\n") if body_start >= 0 else text
            p.write_text(write_fm(fm) + "\n" + body, encoding="utf-8")
        except Exception:
            pass


def search(query: str, limit: int = 8, types: Optional[List[str]] = None,
           statuses: Optional[List[str]] = None,
           explain: bool = False
           ) -> List[Tuple[float, Path, Dict[str, Any], str]]:
    return _search_with_cfg(query, limit, load_config(), types, statuses, explain=explain)


def _search_with_cfg(query: str, limit: int, cfg: Dict[str, Any],
                     types: Optional[List[str]] = None,
                     statuses: Optional[List[str]] = None,
                     explain: bool = False
                     ) -> List[Tuple[float, Path, Dict[str, Any], str]]:
    if limit <= 0:
        limit = int(cfg.get("retrieval", {}).get("limit", 8))
    r_cfg = cfg.get("retrieval", {})
    mode = str(r_cfg.get("mode", "hybrid")).lower()
    emb_setting = str(r_cfg.get("embeddings", "auto")).lower()
    cand_mult = int(r_cfg.get("candidate_multiplier", 4))
    cand_limit = limit * cand_mult
    # Filter candidates
    cands: List[Tuple[Path, str, Dict[str, Any]]] = []
    for p in memory_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_fm(text)
        status = str(fm.get("status", "active")).lower()
        if status in {"invalid", "archived"}:
            continue
        if types:
            mt = str(fm.get("type", "")).lower()
            if mt not in [t.lower() for t in types]:
                continue
        if statuses:
            if status not in [s.lower() for s in statuses]:
                continue
        cands.append((p, text, fm))
    if not cands:
        return []

    # 1. Sparse retrieval — try FTS5 first, fall back to Python BM25
    q_tokens = tokenize(query)
    if not q_tokens:
        q_tokens = re.findall(r"[A-Za-z0-9_./:@+-]{2,}", query.lower())
    # Try SQLite FTS5 for sparse channel
    fts5_used = False
    sparse_scored: List[Tuple[float, int, List[str]]] = []
    idx = _open_sqlite_index()
    if idx is not None and idx.fts5_available():
        # Map memory_ids to candidate indices
        mem_id_to_cand_idx: Dict[str, int] = {}
        for i, (p, text, fm) in enumerate(cands):
            mid = str(fm.get("id", ""))
            if mid:
                mem_id_to_cand_idx[mid] = i
        # Apply filters for FTS5 query
        fts_types = [t.lower() for t in types] if types else None
        fts_statuses = [s.lower() for s in statuses] if statuses else None
        fts_results = idx.fts5_search(query, cand_limit, types=fts_types, statuses=fts_statuses)
        if fts_results is not None and len(fts_results) > 0:
            for fts_score, mem_id, path in fts_results:
                ci = mem_id_to_cand_idx.get(mem_id)
                if ci is not None:
                    matched = [t for t in q_tokens if t in " ".join(docs_tok_placeholder(cands[ci][1]))]
                    sparse_scored.append((fts_score, ci, matched))
            fts5_used = True
    if idx is not None:
        idx.close()
    # Fallback to Python BM25 if FTS5 not available or returned nothing
    if not fts5_used or not sparse_scored:
        docs_tok: List[List[str]] = []
        for p, text, fm in cands:
            header = "\n".join(text.splitlines()[:40])
            body = "\n".join(text.splitlines())
            rel = str(p.relative_to(ROOT))
            combined = f"{rel}\n{header}\n{body}"
            docs_tok.append(tokenize(combined))
        N = len(docs_tok)
        avgdl = sum(len(d) for d in docs_tok) / N if N else 0
        df: Dict[str, int] = {}
        for d in docs_tok:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        k1 = float(r_cfg.get("bm25_k1", 1.5))
        b = float(r_cfg.get("bm25_b", 0.75))
        sparse_scored = []
        for i, d in enumerate(docs_tok):
            score, matched = bm25_doc_score(q_tokens, d, df, N, avgdl, k1, b)
            if score > 0:
                sparse_scored.append((score, i, matched))
    else:
        # Build docs_tok for MMR fallback
        docs_tok = []
        for p, text, fm in cands:
            header = "\n".join(text.splitlines()[:40])
            body = "\n".join(text.splitlines())
            rel = str(p.relative_to(ROOT))
            combined = f"{rel}\n{header}\n{body}"
            docs_tok.append(tokenize(combined))
    sparse_scored.sort(key=lambda x: -x[0])
    sparse_scored = sparse_scored[:cand_limit]

    # 2. Dense retrieval — if mode != sparse and embeddings available
    dense_ranked: Optional[List[Tuple[float, int]]] = None
    retrieval_mode = "sparse"
    if mode != "sparse" and emb_setting not in ("off", "no", "false", "0"):
        dense_ranked = _dense_search_raw(query, cands, cfg)
        if dense_ranked is not None:
            retrieval_mode = "hybrid"
            dense_ranked = dense_ranked[:cand_limit]
    # If mode was "dense" but dense failed, fall back to sparse gracefully

    # 3. RRF fusion (or sparse-only)
    rrf_k = float(r_cfg.get("rrf_k", 60))
    sp_w = float(r_cfg.get("sparse_weight", 1.0))
    dn_w = float(r_cfg.get("dense_weight", 1.0))
    if retrieval_mode == "hybrid" and dense_ranked is not None:
        fused = rrf_fusion(sparse_scored, dense_ranked, rrf_k, sp_w, dn_w)
    else:
        # Sparse-only: convert to fused format
        fused = []
        for rank, (score, idx, matched) in enumerate(sparse_scored):
            explain_dict = {
                "sparse_score": round(score, 4),
                "sparse_rank": rank,
                "dense_score": None,
                "dense_rank": None,
                "rrf_score": round(sp_w / (rrf_k + rank), 6),
            }
            fused.append((explain_dict["rrf_score"], idx, explain_dict))

    # 4. Apply policy boost
    min_score = float(r_cfg.get("min_score", 0.5))
    boosted: List[Tuple[float, int, Dict[str, Any]]] = []
    for rrf_sc, idx, expl in fused:
        fm = cands[idx][2]
        pb = _policy_boost(fm)
        final_score = rrf_sc + pb
        if final_score >= min_score:
            expl["policy_boost"] = round(pb, 4)
            expl["final_score"] = round(final_score, 6)
            boosted.append((final_score, idx, expl))
    boosted.sort(key=lambda x: -x[0])

    # 5. MMR post-fusion
    selected = _mmr_post_fusion(boosted, cands, docs_tok, cfg, limit)

    # 6. Build output
    out = []
    for rank, (final_score, idx, expl) in enumerate(selected):
        p, text, fm = cands[idx]
        snip = " ".join(text.split())[:420]
        # Add rank and retrieval_mode to explain
        expl["final_rank"] = rank
        expl["retrieval_mode"] = retrieval_mode
        expl["matched_tokens"] = _matched_for(fm, query)
        out.append((final_score, p, fm, snip))
        # Attach explain to fm for --explain consumers
        if explain:
            fm["_explain"] = expl
    _mark_accessed_db([str(fm.get("id", str(p))) for _, p, fm, _ in out])
    return out


def _matched_for(fm: Dict[str, Any], query: str = "") -> List[str]:
    """Return matched tokens (from tags/scope + query overlap) for JSON consumers."""
    out: List[str] = []
    tags = fm.get("tags", [])
    if isinstance(tags, list):
        out.extend(str(t) for t in tags if str(t) not in ("[]", ""))
    elif tags and str(tags) != "[]":
        out.append(str(tags))
    if query:
        q_tokens = set(tokenize(query))
        title = str(fm.get("id", ""))
        for t in q_tokens:
            if t in title.lower():
                out.append(t)
    return out


# ----------------------------- remember -------------------------------------

SECRET_PATTERNS = [
    re.compile(r"(?i)(?:password|passwd|pwd)\s*[:=]\s*\S{4,}"),
    re.compile(r"(?i)(?:api[_-]?key|apikey)\s*[:=]\s*\S{8,}"),
    re.compile(r"(?i)(?:secret|token)\s*[:=]\s*\S{8,}"),
    re.compile(r"(?i)(?:AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+]{20,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
]


def scan_secrets(text: str) -> List[str]:
    """Return list of detected secret pattern descriptions."""
    found: List[str] = []
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            found.append(pat.pattern[:60])
    return found


def remember(args) -> None:
    # G4: privacy scan at write-time
    scan_text = f"{args.title}\n{args.body}\n{args.consequence or ''}\n{args.evidence or ''}"
    secrets = scan_secrets(scan_text)
    allow_secret = getattr(args, "allow_secret", False)
    if secrets and not allow_secret:
        print("REFUSED: potential secret pattern detected in memory content:", file=sys.stderr)
        for s in secrets:
            print(f"  pattern: {s}", file=sys.stderr)
        print("If this is a false positive, re-run with --allow-secret.", file=sys.stderr)
        return
    # G3: duplicate detection by title similarity
    dupes = _find_duplicates(args.title, args.type)
    if dupes and not getattr(args, "force", False):
        print(f"WARNING: similar memory already exists:", file=sys.stderr)
        for d in dupes:
            print(f"  {d}", file=sys.stderr)
        print("Use --force to create anyway, or `update` the existing memory.", file=sys.stderr)
        return
    # H2: conflict detection for decision/knowledge/constraint
    conflicts = _find_conflicts(args.type, args.body, args.scope)
    if conflicts and not getattr(args, "force", False):
        print("WARNING: potential conflict with active memory of same type/scope:", file=sys.stderr)
        for c in conflicts:
            print(f"  {c}", file=sys.stderr)
        print("Consider `supersede` instead. Use --force to create anyway.", file=sys.stderr)
        return
    status = "tentative" if args.type == "hypothesis" and args.status == "active" else args.status
    folder = RAG / TYPE_DIR[args.type]
    folder.mkdir(parents=True, exist_ok=True)
    d = dt.date.today().strftime("%Y%m%d")
    path = folder / f"{d}-{slugify(args.title)}.md"
    n = 2
    while path.exists():
        path = folder / f"{d}-{slugify(args.title)}-{n}.md"
        n += 1

    def yl(name: str, val: str) -> str:
        xs = [x.strip() for x in val.split(",") if x.strip()]
        return f"{name}: []\n" if not xs else f"{name}:\n" + "".join(f"  - {x}\n" for x in xs)

    content = (
        "---\n"
        f"id: mem-{d}-{slugify(args.title)[:40]}\n"
        f"type: {args.type}\n"
        f"status: {status}\n"
        f"created: {today()}\n"
        f"verified: {today() if args.type != 'hypothesis' else 'unverified'}\n"
        f"{yl('scope', args.scope)}"
        f"{yl('tags', args.tags)}"
        f"{yl('sources', args.evidence)}"
    )
    if args.links:
        links = [x.strip() for x in args.links.split(",") if x.strip()]
        if links:
            content += "links:\n" + "".join(f"  - {x}\n" for x in links)
        else:
            content += "links: []\n"
    else:
        content += "links: []\n"
    content += (
        "---\n\n"
        f"# {args.title}\n\n"
        "## Knowledge\n\n"
        f"{args.body.strip()}\n\n"
        "## Consequence\n\n"
        f"{(args.consequence or 'To be determined.').strip()}\n"
    )
    path.write_text(content, encoding="utf-8")
    rebuild_index()
    print(path.relative_to(ROOT))


def remember_batch(args) -> int:
    """H4: Batch-create memories from a JSON file.
    JSON format: [{"type":"decision","title":"...","body":"...","tags":"a,b",...}, ...]"""
    src = Path(args.file).expanduser().resolve()
    if not src.is_file():
        print(f"Batch file not found: {src}", file=sys.stderr)
        return 1
    try:
        items = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 1
    if not isinstance(items, list):
        print("Expected a JSON array of memory objects.", file=sys.stderr)
        return 1
    created = 0
    skipped = 0
    for item in items:
        if not isinstance(item, dict) or not item.get("type") or not item.get("title") or not item.get("body"):
            print(f"SKIP: invalid entry (needs type, title, body): {item.get('title', '?')}", file=sys.stderr)
            skipped += 1
            continue
        class _BatchArgs:
            type = item.get("type", "knowledge")
            status = item.get("status", "active")
            title = item.get("title", "untitled")
            scope = item.get("scope", "")
            tags = item.get("tags", "")
            evidence = item.get("evidence", "")
            body = item.get("body", "")
            consequence = item.get("consequence", "")
            links = item.get("links", "")
            force = True
            allow_secret = False
        remember(_BatchArgs())
        created += 1
    print(f"Batch complete: {created} created, {skipped} skipped.")
    return 0


def _find_duplicates(title: str, mtype: str, threshold: float = 0.7) -> List[str]:
    """Find existing memories with similar title (Jaccard on tokens)."""
    title_toks = set(tokenize(title))
    if not title_toks:
        return []
    dupes: List[str] = []
    for p in memory_files():
        fm = parse_fm(p.read_text(encoding="utf-8", errors="replace"))
        if str(fm.get("type", "")).lower() != mtype.lower():
            continue
        existing_title = ""
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                existing_title = line[2:].strip()
                break
        if not existing_title:
            continue
        ext_toks = set(tokenize(existing_title))
        if not ext_toks:
            continue
        jaccard = len(title_toks & ext_toks) / len(title_toks | ext_toks)
        if jaccard >= threshold:
            dupes.append(f"{p.relative_to(ROOT)} (title: {existing_title}, similarity: {jaccard:.0%})")
    return dupes


def _find_conflicts(mtype: str, body: str, scope: str) -> List[str]:
    """H2: Detect potential conflicts with active memories of same type/scope.
    Heuristic: same type + overlapping scope + significant body token overlap."""
    if mtype not in ("decision", "knowledge", "constraint"):
        return []
    body_toks = set(tokenize(body))
    if not body_toks:
        return []
    scope_set = set(x.strip() for x in (scope or "").split(",") if x.strip())
    conflicts: List[str] = []
    for p in memory_files():
        fm = parse_fm(p.read_text(encoding="utf-8", errors="replace"))
        if str(fm.get("type", "")).lower() != mtype.lower():
            continue
        if str(fm.get("status", "")).lower() != "active":
            continue
        # Check scope overlap
        existing_scopes = fm.get("scope", [])
        if isinstance(existing_scopes, str):
            existing_scopes = [existing_scopes] if existing_scopes else []
        if not isinstance(existing_scopes, list):
            existing_scopes = []
        existing_scope_set = set(str(s).strip() for s in existing_scopes if str(s).strip())
        if scope_set and existing_scope_set and not (scope_set & existing_scope_set):
            continue
        # Check body token overlap
        existing_body = ""
        in_body = False
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("## Knowledge"):
                in_body = True
                continue
            if in_body and line.startswith("## "):
                break
            if in_body:
                existing_body += line + "\n"
        ext_body_toks = set(tokenize(existing_body))
        if not ext_body_toks:
            continue
        overlap = len(body_toks & ext_body_toks) / len(body_toks | ext_body_toks)
        if overlap >= 0.5:
            title = ""
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            conflicts.append(f"{p.relative_to(ROOT)} (title: {title}, body overlap: {overlap:.0%})")
    return conflicts


# ----------------------------- memory CRUD ----------------------------------

def _read_memory(p: Path) -> Tuple[str, Dict[str, Any]]:
    text = p.read_text(encoding="utf-8", errors="replace")
    return text, parse_fm(text)


def show_memory(args) -> int:
    p = find_memory_by_id_or_path(args.ref)
    if p is None:
        print(f"Memory not found: {args.ref}", file=sys.stderr)
        return 1
    text = p.read_text(encoding="utf-8", errors="replace")
    if args.section:
        body = text
        fm_end = text.find("\n---", 4)
        if fm_end >= 0:
            body = text[fm_end + 4:].lstrip("\n")
        section = get_section(body, args.section)
        if not section:
            print(f"Section not found: {args.section}", file=sys.stderr)
            return 1
        print(section)
        return 0
    if args.json:
        fm = parse_fm(text)
        print(json.dumps({"path": str(p.relative_to(ROOT)), "frontmatter": fm,
                          "content": text}, indent=2, ensure_ascii=False))
        return 0
    print(text)
    return 0


def update_memory(args) -> int:
    p = find_memory_by_id_or_path(args.ref)
    if p is None:
        print(f"Memory not found: {args.ref}", file=sys.stderr)
        return 1
    text = p.read_text(encoding="utf-8", errors="replace")
    fm = parse_fm(text)
    if args.status:
        fm["status"] = args.status
    if args.verified:
        fm["verified"] = args.verified
    if args.add_tags:
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        for t in args.add_tags.split(","):
            t = t.strip()
            if t and t not in tags:
                tags.append(t)
        fm["tags"] = tags
    if args.remove_tags:
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        rm = {x.strip() for x in args.remove_tags.split(",")}
        fm["tags"] = [t for t in tags if t not in rm]
    fm["updated"] = today()
    body_start = text.find("---\n", 4)
    body = text[body_start + 4:] if body_start >= 0 else text
    if body.startswith("\n"):
        body = body[1:]
    new_text = write_fm(fm) + "\n" + body
    if args.append:
        new_text = new_text.rstrip() + "\n\n## Update " + today() + "\n\n" + args.append.strip() + "\n"
    p.write_text(new_text, encoding="utf-8")
    rebuild_index()
    print(f"Updated: {p.relative_to(ROOT)}")
    return 0


def supersede(args) -> int:
    p = find_memory_by_id_or_path(args.ref)
    if p is None:
        print(f"Memory not found: {args.ref}", file=sys.stderr)
        return 1
    text, fm = _read_memory(p)
    fm["status"] = "superseded"
    fm["superseded_by"] = args.by or "unspecified"
    fm["superseded_at"] = today()
    fm["supersede_reason"] = args.reason or "unspecified"
    fm["updated"] = today()
    body_start = text.find("---\n", 4)
    body = text[body_start + 4:].lstrip("\n") if body_start >= 0 else text
    p.write_text(write_fm(fm) + "\n" + body, encoding="utf-8")
    rebuild_index()
    print(f"Superseded: {p.relative_to(ROOT)} (by {args.by or 'unspecified'})")
    return 0


def forget(args) -> int:
    p = find_memory_by_id_or_path(args.ref)
    if p is None:
        print(f"Memory not found: {args.ref}", file=sys.stderr)
        return 1
    archive = RAG / "archive"
    archive.mkdir(exist_ok=True)
    target = archive / p.name
    n = 1
    while target.exists():
        target = archive / f"{p.stem}-{n}.md"
        n += 1
    p.rename(target)
    rebuild_index()
    print(f"Archived: {p.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
    return 0


def clean_cmd(args) -> int:
    """H5: Permanently delete all files from archive/ (forgotten memories)."""
    archive = RAG / "archive"
    if not archive.exists():
        print("No archive directory.")
        return 0
    targets = list(archive.glob("*.md"))
    if not targets:
        print("No archived memories to clean.")
        return 0
    if not args.force:
        print(f"Found {len(targets)} archived memory file(s) to permanently delete:")
        for p in targets:
            print(f"  {p.relative_to(ROOT)}")
        print("Run with --force to confirm permanent deletion.")
        return 1
    for p in targets:
        p.unlink()
    print(f"Permanently deleted {len(targets)} archived memory file(s).")
    return 0


def link_memories(args) -> int:
    p1 = find_memory_by_id_or_path(args.from_ref)
    p2 = find_memory_by_id_or_path(args.to_ref)
    if p1 is None or p2 is None:
        print(f"Memory not found: {args.from_ref} or {args.to_ref}", file=sys.stderr)
        return 1
    text, fm = _read_memory(p1)
    links = fm.get("links", [])
    if isinstance(links, str):
        links = [links]
    rel2 = str(p2.relative_to(ROOT)).replace("\\", "/")
    if rel2 not in links:
        links.append(rel2)
    fm["links"] = links
    fm["updated"] = today()
    body_start = text.find("---\n", 4)
    body = text[body_start + 4:].lstrip("\n") if body_start >= 0 else text
    p1.write_text(write_fm(fm) + "\n" + body, encoding="utf-8")
    print(f"Linked: {p1.relative_to(ROOT)} -> {p2.relative_to(ROOT)}")
    return 0


def memory_status(args) -> int:
    counts: Dict[str, Dict[str, int]] = {}
    total = 0
    for p in memory_files():
        _, fm = _read_memory(p)
        t = str(fm.get("type", "unknown"))
        s = str(fm.get("status", "unknown"))
        counts.setdefault(t, {})
        counts[t][s] = counts[t].get(s, 0) + 1
        total += 1
    cp = load_checkpoint()
    cur = project_fingerprint()
    fresh = cp.get("fingerprint") == cur
    out = {
        "total_memories": total,
        "by_type": counts,
        "checkpoint_fresh": fresh,
        "checkpoint_at": cp.get("at"),
        "checkpoint_reason": cp.get("reason"),
        "head": git_text("rev-parse", "--short", "HEAD"),
        "branch": git_text("branch", "--show-current"),
    }
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    print(f"Total memories: {total}")
    for t in sorted(counts):
        parts = ", ".join(f"{s}={n}" for s, n in sorted(counts[t].items()))
        print(f"  {t}: {parts}")
    print(f"Checkpoint: {'FRESH' if fresh else 'STALE'} ({cp.get('reason', '?')} at {cp.get('at', '?')})")
    print(f"Branch: {out['branch']}  HEAD: {out['head']}")
    return 0


def diff_memory(args) -> int:
    """Show what changed in project code since the last checkpoint."""
    cp = load_checkpoint()
    saved = cp.get("fingerprint")
    cur = project_fingerprint()
    if args.json:
        print(json.dumps({
            "checkpoint_fingerprint": saved[:16] if saved else None,
            "current_fingerprint": cur[:16],
            "fresh": saved == cur,
            "changed": changed_entries(),
        }, indent=2, ensure_ascii=False))
        return 0
    if saved == cur:
        print("No changes since last checkpoint.")
        return 0
    print(f"Changed since last checkpoint ({cp.get('reason', '?')}):")
    for s, p in changed_entries():
        print(f"- `{s}` {p}")
    return 0


def timeline(args) -> int:
    """Show memory timeline (by created date)."""
    items = []
    for p in memory_files():
        _, fm = _read_memory(p)
        items.append({
            "created": str(fm.get("created", "unknown")),
            "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "type": str(fm.get("type", "?")),
            "status": str(fm.get("status", "?")),
            "title": next((x[2:].strip() for x in p.read_text(encoding="utf-8", errors="replace").splitlines()
                           if x.startswith("# ")), p.stem),
        })
    items.sort(key=lambda x: (x["created"], x["path"]), reverse=True)
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    if args.json:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return 0
    if not items:
        print("No memories yet.")
        return 0
    for it in items:
        print(f"{it['created']}  [{it['type']}/{it['status']}]  {it['path']}")
        print(f"    {it['title']}")
    return 0


# ----------------------------- index & validate -----------------------------

def rebuild_index() -> None:
    RAG.mkdir(exist_ok=True)
    entries = []
    for p in memory_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_fm(text)
        title = next((x[2:].strip() for x in text.splitlines() if x.startswith("# ")), p.stem)
        entries.append((str(fm.get("type", "unknown")), str(fm.get("status", "unknown")),
                        title, p.relative_to(ROOT)))
    entries.sort(key=lambda x: (x[0], x[2].lower()))
    lines = ["# Memory Index", "", "Generated by `irag.py index`. Read entries lazily.", ""]
    cur = None
    for typ, status, title, rel in entries:
        if typ != cur:
            cur = typ
            lines += [f"## {typ}", ""]
        lines.append(f"- `{rel}` — **{title}** [{status}]")
    if not entries:
        lines.append("No durable memories yet.")
    (RAG / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Indexed {len(entries)} memories.")


def _open_sqlite_index() -> Optional[Any]:
    """Open the SQLite FTS5 index. Returns IndexDB or None."""
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "irag_index", str(ROOT / ".agents" / "skills" / "internal-rag" / "irag_index.py"))
        if spec is None or spec.loader is None:
            return None
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.open_index(ROOT)
    except Exception:
        return None


def docs_tok_placeholder(text: str) -> List[str]:
    """Quick tokenize for matched-token extraction in FTS5 path."""
    return tokenize(text)


def index_cmd(args) -> int:
    """Handle `irag.py index` with subcommands: --rebuild, --status, --vacuum."""
    if getattr(args, "rebuild", False):
        # Rebuild INDEX.md
        rebuild_index()
        # Rebuild SQLite index
        idx = _open_sqlite_index()
        if idx is None:
            print("SQLite index: unavailable (open failed)")
            return 1
        cands = [(p, p.read_text(encoding="utf-8", errors="replace"),
                  parse_fm(p.read_text(encoding="utf-8", errors="replace")))
                 for p in memory_files()]
        result = idx.rebuild(cands)
        idx.close()
        fts = "yes" if result["fts5"] else "no"
        print(f"SQLite index rebuilt: {result['indexed']} documents, FTS5={fts}")
        return 0
    if getattr(args, "status", False):
        idx = _open_sqlite_index()
        if idx is None:
            print("SQLite index: unavailable")
            return 1
        st = idx.status()
        # Stale check
        cands = [(p, p.read_text(encoding="utf-8", errors="replace"),
                  parse_fm(p.read_text(encoding="utf-8", errors="replace")))
                 for p in memory_files()]
        stale = idx.stale_check(cands)
        idx.close()
        if getattr(args, "json", False):
            print(json.dumps({**st, **stale}, indent=2))
            return 0
        print(f"SQLite version: {st['sqlite_version']}")
        print(f"Schema version: {st['schema_version']}")
        print(f"FTS5 available: {'yes' if st['fts5_available'] else 'no'}")
        print(f"Indexed memories: {st['indexed_memories']}")
        print(f"Chunks: {st['chunks']}")
        print(f"DB path: {st['db_path']}")
        print(f"DB size: {st['db_size_bytes']} bytes")
        print(f"Stale: {stale['stale']}, Missing: {stale['missing']}")
        return 0
    if getattr(args, "vacuum", False):
        idx = _open_sqlite_index()
        if idx is None:
            print("SQLite index: unavailable")
            return 1
        idx.vacuum()
        # Cleanup stale embeddings
        cands = [(p, p.read_text(encoding="utf-8", errors="replace"),
                  parse_fm(p.read_text(encoding="utf-8", errors="replace")))
                 for p in memory_files()]
        current_chunk_ids = set()
        for p, text, fm in cands:
            mem_id = str(fm.get("id", str(p)))
            current_chunk_ids.add(f"{mem_id}-c0")
        deleted = idx.cleanup_stale_embeddings(current_chunk_ids)
        # Detect and report corrupt embeddings
        corrupt = idx.detect_corrupt_embeddings()
        idx.close()
        print(f"SQLite index vacuumed. Stale embeddings removed: {deleted}")
        if corrupt:
            print(f"Corrupt embeddings detected: {len(corrupt)} (will be regenerated on next search)")
        return 0
    if getattr(args, "embed_missing", False):
        idx = _open_sqlite_index()
        if idx is None:
            print("SQLite index: unavailable")
            return 1
        cands = [(p, p.read_text(encoding="utf-8", errors="replace"),
                  parse_fm(p.read_text(encoding="utf-8", errors="replace")))
                 for p in memory_files()]
        # First ensure documents are indexed
        idx.sync_incremental(cands)
        # Get model info
        cfg = load_config()
        model_name = str(cfg.get("retrieval", {}).get("embeddings_model", "all-MiniLM-L6-v2"))
        # Compute content hashes for chunks
        chunk_ids = []
        content_hashes = {}
        for p, text, fm in cands:
            mem_id = str(fm.get("id", str(p)))
            cid = f"{mem_id}-c0"
            chunk_ids.append(cid)
            body_start = text.find("\n---", 4)
            body = text[body_start + 4:].strip() if body_start >= 0 else text
            content_hashes[cid] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        missing = idx.get_missing_chunks(chunk_ids, model_name, content_hashes)
        idx.close()
        if not missing:
            print(f"All {len(chunk_ids)} chunks have cached embeddings for model '{model_name}'.")
            return 0
        print(f"Missing/stale embeddings: {len(missing)}/{len(chunk_ids)} for model '{model_name}'")
        print("Run a search or context command to lazily embed missing chunks.")
        return 0
    # Default: rebuild INDEX.md only
    rebuild_index()
    return 0


def validate() -> int:
    errors = 0
    warnings = 0
    if not WORKING.exists():
        print("ERROR INTERNAL_RAG/WORKING_STATE.md missing")
        errors += 1
    for p in memory_files():
        fm = parse_fm(p.read_text(encoding="utf-8", errors="replace"))
        rel = p.relative_to(ROOT)
        for k in ("id", "type", "status", "created"):
            if not fm.get(k):
                print(f"ERROR {rel}: missing `{k}`")
                errors += 1
        if fm.get("type") and fm.get("type") not in ALLOWED_TYPES:
            print(f"ERROR {rel}: invalid type `{fm.get('type')}`")
            errors += 1
        if fm.get("status") and fm.get("status") not in ALLOWED_STATUS:
            print(f"ERROR {rel}: invalid status `{fm.get('status')}`")
            errors += 1
        # G2: stale evidence path check
        sources = fm.get("sources", [])
        if isinstance(sources, str):
            if sources in ("[]", ""):
                sources = []
            else:
                sources = [sources]
        if not isinstance(sources, list):
            sources = []
        for src in sources:
            src_s = str(src).strip()
            if not src_s:
                continue
            if src_s.startswith("http") or src_s.startswith("https"):
                continue
            check_path = src_s.split(":")[0].split("#")[0].strip()
            if not check_path:
                continue
            candidate = ROOT / check_path
            if not candidate.exists():
                print(f"WARN {rel}: evidence path not found: {src_s}")
                warnings += 1
    print(f"Validation complete: {errors} error(s), {warnings} warning(s).")
    return 1 if errors else 0


# ----------------------------- tasks (multi-task stack) ---------------------

def load_tasks() -> Dict[str, Any]:
    try:
        data = json.loads(TASKS.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"schema": TASKS_SCHEMA, "stack": [], "completed": []}
        if "schema" not in data:
            data["schema"] = TASKS_SCHEMA
        return data
    except Exception:
        return {"schema": TASKS_SCHEMA, "stack": [], "completed": []}


def save_tasks(data: Dict[str, Any]) -> None:
    RAG.mkdir(exist_ok=True)
    cfg = load_config()
    max_stack = int(cfg.get("checkpoints", {}).get("max_task_stack", 16))
    data["schema"] = TASKS_SCHEMA
    data["stack"] = data.get("stack", [])[-max_stack:]
    TASKS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def push_task(task: str, reason: str = "user") -> None:
    data = load_tasks()
    stack = data.get("stack", [])
    stack.append({"task": task, "reason": reason, "at": now(),
                  "fingerprint": project_fingerprint(),
                  "head": git_text("rev-parse", "--short", "HEAD"),
                  "working_state": WORKING.read_text(encoding="utf-8", errors="replace")
                  if WORKING.exists() else ""})
    data["stack"] = stack
    save_tasks(data)


def pop_task() -> Optional[Dict[str, Any]]:
    data = load_tasks()
    stack = data.get("stack", [])
    if not stack:
        return None
    top = stack.pop()
    data["stack"] = stack
    data.setdefault("completed", []).append({**top, "completed_at": now()})
    save_tasks(data)
    return top


def tasks_cmd(args) -> int:
    data = load_tasks()
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    stack = data.get("stack", [])
    print(f"Task stack depth: {len(stack)}")
    for i, t in enumerate(stack, 1):
        print(f"  {i}. [{t.get('reason', '?')}] {t.get('task', '?')}")
        print(f"     at: {t.get('at')}  head: {t.get('head', '?')}")
    if not stack:
        print("  (empty)")
    return 0


def resume_cmd(args) -> int:
    """Pop the top task from the stack and restore its WORKING_STATE.
    Also update Current request / Current phase / Next actions to reflect the resume."""
    top = pop_task()
    if top is None:
        print("No task to resume (stack is empty).", file=sys.stderr)
        return 1
    ws = top.get("working_state", "")
    if ws and not args.discard_state:
        save_working(ws)
    if WORKING.exists():
        text = WORKING.read_text(encoding="utf-8", errors="replace")
        text = set_section(text, "Current request", top.get("task", "resumed"))
        text = set_section(text, "Current phase", f"resumed: {top.get('reason', '?')}")
        text = set_header(text, "updated", now())
        save_working(text)
    fp_saved = top.get("fingerprint")
    cur = project_fingerprint()
    fresh = fp_saved == cur
    if args.json:
        print(json.dumps({"resumed_task": top.get("task"), "reason": top.get("reason"),
                          "head_at_push": top.get("head"), "fingerprint_fresh": fresh}, indent=2))
        return 0
    print(f"Resumed task: {top.get('task')}")
    print(f"Reason: {top.get('reason')}")
    print(f"Pushed at: {top.get('at')}  head: {top.get('head', '?')}")
    print(f"State: {'FRESH (project code matches)' if fresh else 'STALE (project code changed since push)'}")
    if not fresh:
        print("Run `irag.py context --task ...` to see recovery guidance.")
    return 0


def forget_task_cmd(args) -> int:
    data = load_tasks()
    stack = data.get("stack", [])
    if args.id is None:
        n = len(stack)
        data["stack"] = []
        save_tasks(data)
        print(f"Cleared task stack ({n} task(s) dropped).")
        return 0
    try:
        idx = int(args.id)
        if idx < 1 or idx > len(stack):
            print(f"Invalid task id: {idx} (stack depth: {len(stack)})", file=sys.stderr)
            return 1
        removed = stack.pop(idx - 1)
        data["stack"] = stack
        save_tasks(data)
        print(f"Dropped task #{idx}: {removed.get('task', '?')}")
        return 0
    except ValueError:
        print(f"Invalid task id (expected integer): {args.id}", file=sys.stderr)
        return 1


def compact_working_state() -> None:
    """Compact WORKING_STATE.md: archive a snapshot and trim long list sections
    (preserves the full section structure, only shortens overlong lists)."""
    if not WORKING.exists():
        print("No WORKING_STATE.md to compact.")
        return
    text = WORKING.read_text(encoding="utf-8", errors="replace")
    try:
        snap_dir = RAG / "sessions" / ".snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        (snap_dir / f"pre-compact-{stamp}.md").write_text(text, encoding="utf-8")
    except Exception:
        pass
    max_lines = 20
    for sec in ("Recovery snapshot", "Relevant files"):
        body = get_section(text, sec)
        if not body:
            continue
        lines = body.splitlines()
        if len(lines) > max_lines:
            kept = "\n".join(lines[:max_lines])
            text = set_section(text, sec, kept + "\n- (older entries trimmed by compact)")
    text = set_header(text, "updated", now())
    save_working(text)
    print("WORKING_STATE compacted (snapshot archived in sessions/.snapshots/).")


# ----------------------------- doctor ---------------------------------------

def doctor(args) -> int:
    issues: List[Dict[str, str]] = []
    if not (ROOT / ".git").is_dir() and not git_text("rev-parse", "--is-inside-work-tree"):
        issues.append({"severity": "critical", "issue": "not a git repository"})
    if not RAG.exists():
        issues.append({"severity": "critical", "issue": "INTERNAL_RAG/ missing; run init"})
    else:
        for d in ["decisions", "knowledge", "gotchas", "failures", "hypotheses", "sessions", "archive"]:
            if not (RAG / d).is_dir():
                issues.append({"severity": "warning", "issue": f"missing subdir: {d}"})
    if not WORKING.exists():
        issues.append({"severity": "critical", "issue": "WORKING_STATE.md missing"})
    if not CHECKPOINT.exists():
        issues.append({"severity": "warning", "issue": "no checkpoint yet"})
    cp = load_checkpoint()
    if cp.get("fingerprint") and cp.get("fingerprint") != project_fingerprint():
        issues.append({"severity": "info", "issue": "checkpoint stale (project code changed since last checkpoint)"})
    py_ver = sys.version.split()[0]
    major, minor = sys.version_info[0], sys.version_info[1]
    if (major, minor) < (3, 8):
        issues.append({"severity": "critical", "issue": f"python {py_ver} too old (need >=3.8)"})
    emb = embeddings_search("test", [], 1, load_config())
    emb_status = "available" if emb is not None else "not available (BM25 fallback)"
    issues.append({"severity": "info", "issue": f"embeddings: {emb_status}"})
    if CONFIG_PATH.exists():
        config_issues = _validate_config(load_config())
        if config_issues:
            for ci in config_issues:
                issues.append({"severity": "warning", "issue": f"config: {ci}"})
        issues.append({"severity": "info", "issue": f"config: {CONFIG_PATH.relative_to(ROOT)}"})
    else:
        issues.append({"severity": "info", "issue": "config: defaults (no .irag.yml)"})
    # Usage stats now from SQLite DB (see below)
    # SQLite index status
    try:
        import sqlite3 as _sqlite3
        sqlite_ver = _sqlite3.sqlite_version
        idx = _open_sqlite_index()
        if idx is not None:
            idx_st = idx.status()
            fts5 = "yes" if idx_st["fts5_available"] else "no"
            issues.append({"severity": "info", "issue": f"SQLite: v{sqlite_ver}, FTS5={fts5}, schema=v{idx_st['schema_version']}, indexed={idx_st['indexed_memories']}"})
            # Stale check
            cands = [(p, p.read_text(encoding="utf-8", errors="replace"),
                      parse_fm(p.read_text(encoding="utf-8", errors="replace")))
                     for p in memory_files()]
            stale = idx.stale_check(cands)
            if stale["stale"] > 0:
                issues.append({"severity": "warning", "issue": f"SQLite index: {stale['stale']} stale document(s) — run 'index --rebuild'"})
            if stale["missing"] > 0:
                issues.append({"severity": "warning", "issue": f"SQLite index: {stale['missing']} missing document(s) — run 'index --rebuild'"})
            idx.close()
        else:
            issues.append({"severity": "info", "issue": f"SQLite: v{sqlite_ver}, index not available"})
    except Exception:
        issues.append({"severity": "info", "issue": "SQLite: not available"})
    # Usage stats from DB (replaces frontmatter-based never-accessed check)
    try:
        idx2 = _open_sqlite_index()
        if idx2 is not None:
            total_mem = 0
            never_accessed_db = 0
            top_accessed: List[Tuple[str, int]] = []
            for p in memory_files():
                total_mem += 1
                fm = parse_fm(p.read_text(encoding="utf-8", errors="replace"))
                mid = str(fm.get("id", str(p)))
                row = idx2.conn.execute("SELECT access_count, last_accessed FROM usage WHERE memory_id=?", (mid,)).fetchone()
                if row is None or (row["access_count"] == 0 and not row["last_accessed"]):
                    never_accessed_db += 1
                elif row["access_count"] > 0:
                    top_accessed.append((mid, row["access_count"]))
            if total_mem > 0 and never_accessed_db > 0:
                issues.append({"severity": "info", "issue": f"memories never accessed: {never_accessed_db}/{total_mem} (candidates for archive)"})
            top_accessed.sort(key=lambda x: -x[1])
            for mid, cnt in top_accessed[:3]:
                issues.append({"severity": "info", "issue": f"top accessed: {mid} ({cnt}x)"})
            idx2.close()
    except Exception:
        pass
    if args.json:
        print(json.dumps({"issues": issues, "version": VERSION,
                          "python": py_ver, "root": str(ROOT)}, indent=2, ensure_ascii=False))
        return 0 if not any(i["severity"] == "critical" for i in issues) else 2
    print(f"INTERNAL_RAG doctor (irag {VERSION})")
    print(f"Root: {ROOT}")
    print(f"Python: {py_ver}")
    for i in issues:
        print(f"  [{i['severity'].upper()}] {i['issue']}")
    crit = sum(1 for i in issues if i["severity"] == "critical")
    return 2 if crit else 0


# ----------------------------- migrate-usage ------------------------------

def migrate_usage_cmd(args) -> int:
    """Migrate last_accessed from Markdown frontmatter to SQLite usage table.
    --dry-run: report what would change. --apply: write to DB, optionally strip from Markdown."""
    dry_run = getattr(args, "dry_run", False)
    apply_changes = getattr(args, "apply", False)
    strip_markdown = getattr(args, "strip", False)
    if not dry_run and not apply_changes:
        print("Specify --dry-run or --apply", file=sys.stderr)
        return 1
    idx = _open_sqlite_index()
    if idx is None and apply_changes:
        print("SQLite index unavailable — cannot apply migration.", file=sys.stderr)
        return 1
    changed_files: List[str] = []
    imported = 0
    stripped = 0
    for p in memory_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_fm(text)
        mid = str(fm.get("id", str(p)))
        fm_last = str(fm.get("last_accessed", ""))
        if not fm_last:
            continue
        # Check if DB already has a value
        existing = None
        if idx is not None:
            row = idx.conn.execute("SELECT access_count, last_accessed FROM usage WHERE memory_id=?", (mid,)).fetchone()
            if row and row["last_accessed"]:
                existing = row["last_accessed"]
        if existing:
            continue  # Already in DB
        imported += 1
        changed_files.append(str(p.relative_to(ROOT)))
        if apply_changes and idx is not None:
            idx.record_access(mid)
        if apply_changes and strip_markdown:
            # Remove last_accessed from frontmatter
            fm.pop("last_accessed", None)
            body_start = text.find("\n---", 4)
            body = text[body_start + 4:].lstrip("\n") if body_start >= 0 else text
            p.write_text(write_fm(fm) + "\n" + body, encoding="utf-8")
            stripped += 1
    if idx is not None:
        idx.close()
    if getattr(args, "json", False):
        print(json.dumps({"dry_run": dry_run, "imported": imported, "stripped": stripped,
                          "changed_files": changed_files}, indent=2, ensure_ascii=False))
        return 0
    action = "DRY RUN" if dry_run else "APPLIED"
    print(f"migrate-usage {action}: {imported} entries to import, {stripped} stripped from Markdown")
    for f in changed_files:
        print(f"  {f}")
    return 0


# ----------------------------- export / import ------------------------------

def export_cmd(args) -> int:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = EXPORT_DIR / f"irag-export-{stamp}.json"
    memories = []
    for p in memory_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        memories.append({
            "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "frontmatter": parse_fm(text),
            "content": text,
        })
    working = WORKING.read_text(encoding="utf-8", errors="replace") if WORKING.exists() else ""
    payload = {
        "schema": 1, "irag_version": VERSION, "exported_at": now(),
        "source_root": str(ROOT), "head": git_text("rev-parse", "--short", "HEAD"),
        "working_state": working, "checkpoint": load_checkpoint(),
        "memories": memories,
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(memories)} memories -> {target.relative_to(ROOT)}")
    return 0


def import_cmd(args) -> int:
    src = Path(args.file).expanduser().resolve()
    if not src.is_file():
        print(f"Import file not found: {src}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 1
    RAG.mkdir(exist_ok=True)
    for d in ["decisions", "knowledge", "gotchas", "failures", "hypotheses", "sessions", "archive"]:
        (RAG / d).mkdir(exist_ok=True)
    imported = 0
    skipped = 0
    for m in payload.get("memories", []):
        rel = m.get("path", "")
        if not rel or rel.startswith("INTERNAL_RAG/") is False:
            continue
        rel_clean = rel[len("INTERNAL_RAG/"):] if rel.startswith("INTERNAL_RAG/") else rel
        dst = RAG / rel_clean
        if dst.exists() and not args.overwrite:
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(m.get("content", ""), encoding="utf-8")
        imported += 1
    if payload.get("working_state") and not WORKING.exists():
        save_working(payload["working_state"])
    rebuild_index()
    print(f"Imported {imported} memory file(s), skipped {skipped}.")
    return 0


# ----------------------------- embeddings info ------------------------------

def embeddings_info(args) -> int:
    cfg = load_config()
    mode = str(cfg.get("retrieval", {}).get("embeddings", "auto")).lower()
    avail = embeddings_search("test", [], 1, cfg) is not None
    model_name = str(cfg.get("retrieval", {}).get("embeddings_model", "all-MiniLM-L6-v2"))
    info: Dict[str, Any] = {"configured": mode, "available": avail,
            "engine": "sentence-transformers" if avail else "bm25-fallback",
            "model": model_name,
            "plugin_path": str(ROOT / ".agents" / "skills" / "internal-rag" / "irag_embeddings.py")}
    # Persistent embedding cache status
    idx = _open_sqlite_index()
    if idx is not None:
        emb_st = idx.embeddings_status(model_id=model_name if avail else "")
        info["cache"] = emb_st
        idx.close()
    else:
        info["cache"] = {"error": "index unavailable"}
    if args.json:
        print(json.dumps(info, indent=2))
        return 0
    print(f"Embeddings configured: {mode}")
    print(f"Available: {avail}")
    print(f"Engine: {info['engine']}")
    print(f"Model: {model_name}")
    print(f"Plugin: {info['plugin_path']}")
    cache = info.get("cache", {})
    if "error" not in cache:
        print(f"Cache: {cache.get('cached_chunks', 0)} cached, "
              f"{cache.get('missing_chunks', 0)} missing, "
              f"{cache.get('total_chunks', 0)} total, "
              f"{cache.get('disk_bytes', 0)} bytes")
        if cache.get("models"):
            print(f"Cache models: {', '.join(str(m) for m in cache['models'])}")
    else:
        print(f"Cache: {cache.get('error', 'unavailable')}")
    return 0


# ----------------------------- config ---------------------------------------

CONFIG_TEMPLATE = """# INTERNAL_RAG configuration (v1.0.2)
# Optional — remove this file to use built-in defaults.

retrieval:
  limit: 10
  mmr_lambda: 0.5
  min_score: 0.5
  embeddings: auto        # auto | on | off
  embeddings_model: all-MiniLM-L6-v2
tokens:
  context_budget: 4000
  warn_ratio: 0.8
checkpoints:
  auto_archive_sessions: true
  max_task_stack: 16
  max_age_minutes: 0       # 0=disabled; e.g. 60 = warn if checkpoint older than 1h
privacy:
  scan_on_checkpoint: false
"""


def _validate_config(cfg: Dict[str, Any]) -> List[str]:
    """H6: Validate config values, return list of issues."""
    issues: List[str] = []
    known_sections = {"retrieval", "tokens", "checkpoints", "privacy"}
    for key in cfg:
        if key not in known_sections:
            issues.append(f"unknown section: {key}")
    r = cfg.get("retrieval", {})
    if not isinstance(r, dict):
        issues.append("retrieval: must be a mapping")
    else:
        if "limit" in r and not isinstance(r["limit"], int):
            issues.append("retrieval.limit: must be integer")
        if "mmr_lambda" in r:
            v = r["mmr_lambda"]
            if not isinstance(v, (int, float)) or v < 0 or v > 1:
                issues.append("retrieval.mmr_lambda: must be 0.0-1.0")
        if "min_score" in r:
            v = r["min_score"]
            if not isinstance(v, (int, float)) or v < 0:
                issues.append("retrieval.min_score: must be >= 0")
        if "embeddings" in r and str(r["embeddings"]).lower() not in ("auto", "on", "off"):
            issues.append("retrieval.embeddings: must be auto|on|off")
    t = cfg.get("tokens", {})
    if not isinstance(t, dict):
        issues.append("tokens: must be a mapping")
    else:
        if "context_budget" in t and not isinstance(t["context_budget"], int):
            issues.append("tokens.context_budget: must be integer")
    c = cfg.get("checkpoints", {})
    if not isinstance(c, dict):
        issues.append("checkpoints: must be a mapping")
    else:
        if "max_task_stack" in c and not isinstance(c["max_task_stack"], int):
            issues.append("checkpoints.max_task_stack: must be integer")
        if "max_age_minutes" in c:
            v = c["max_age_minutes"]
            if not isinstance(v, (int, float)) or v < 0:
                issues.append("checkpoints.max_age_minutes: must be >= 0")
    return issues


def config_cmd(args) -> int:
    if getattr(args, "init", False):
        if CONFIG_PATH.exists():
            print(f"{CONFIG_PATH.relative_to(ROOT)} already exists; not overwriting.", file=sys.stderr)
            return 1
        CONFIG_PATH.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        print(f"Wrote {CONFIG_PATH.relative_to(ROOT)}")
        return 0
    cfg = load_config()
    if getattr(args, "validate", False):
        issues = _validate_config(cfg)
        if not issues:
            print("Config valid.")
            return 0
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(cfg, indent=2))
        return 0
    if not CONFIG_PATH.exists():
        print(f"No {CONFIG_PATH.relative_to(ROOT)} - using built-in defaults. Run `config --init` to create one.")
    else:
        print(CONFIG_PATH.read_text(encoding="utf-8", errors="replace"))
    return 0


# ----------------------------- MCP server (minimal stdio) -------------------

def mcp_server() -> int:
    """Minimal MCP-like stdio server. Speaks JSON-RPC-ish lines on stdin/stdout.
    Tools exposed: context, search, checkpoint, guard, remember, status, tasks, resume.
    Not a full MCP spec implementation, but a stable, agent-callable bridge."""
    tools = [
        {"name": "context", "description": "Start/resume a task with INTERNAL_RAG context packet.",
         "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}},
        {"name": "search", "description": "Search durable memories (BM25 + MMR, optional embeddings).",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                         "required": ["query"]}},
        {"name": "checkpoint", "description": "Persist current operational state.",
         "inputSchema": {"type": "object", "properties": {"reason": {"type": "string"},
                         "phase": {"type": "string"}, "completed": {"type": "string"},
                         "in_progress": {"type": "string"}, "blockers": {"type": "string"},
                         "next": {"type": "string"}}, "required": ["reason"]}},
        {"name": "guard", "description": "Verify no uncheckpointed changes.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "remember", "description": "Store durable memory.",
         "inputSchema": {"type": "object", "properties": {"type": {"type": "string"},
                         "title": {"type": "string"}, "body": {"type": "string"},
                         "tags": {"type": "string"}, "evidence": {"type": "string"},
                         "scope": {"type": "string"}, "consequence": {"type": "string"}},
                         "required": ["type", "title", "body"]}},
        {"name": "status", "description": "Memory and checkpoint status.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "tasks", "description": "Show task stack.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "resume", "description": "Pop and resume the top task.",
         "inputSchema": {"type": "object", "properties": {}}},
    ]
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse error"}}))
            sys.stdout.flush()
            continue
        method = req.get("method", "")
        rid = req.get("id")
        if method == "notifications/initialized":
            continue
        if method == "shutdown":
            if rid is not None:
                print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {}}))
                sys.stdout.flush()
            break
        if method == "tools/list":
            print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}}))
            sys.stdout.flush()
            continue
        if method == "tools/call":
            name = req.get("params", {}).get("name")
            args_d = req.get("params", {}).get("arguments", {}) or {}
            try:
                result = _mcp_dispatch(name, args_d)
                print(json.dumps({"jsonrpc": "2.0", "id": rid,
                                  "result": {"content": [{"type": "text", "text": result}]}}))
            except Exception as e:
                print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(e)}}))
            sys.stdout.flush()
            continue
        if method == "initialize":
            print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05", "serverInfo": {"name": "internal-rag", "version": VERSION},
                "capabilities": {"tools": {}}}}))
            sys.stdout.flush()
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}))
        sys.stdout.flush()
    return 0


class _Args:
    """Minimal attribute bag for dispatching MCP calls to argparse-style handlers."""
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def _mcp_dispatch(name: str, args_d: Dict[str, Any]) -> str:
    import io
    if name == "context":
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            context(_Args(task=args_d.get("task", ""), limit=int(args_d.get("limit", 6)), json=True))
        finally:
            sys.stdout = old
        return buf.getvalue()
    if name == "search":
        q = args_d.get("query", "")
        limit = int(args_d.get("limit", 8))
        types_f = args_d.get("types")
        statuses_f = args_d.get("statuses")
        if isinstance(types_f, str):
            types_f = [types_f]
        if isinstance(statuses_f, str):
            statuses_f = [statuses_f]
        results = search(q, limit, types=types_f, statuses=statuses_f)
        return json.dumps([{"path": str(p.relative_to(ROOT)), "score": round(s, 2),
                            "type": fm.get("type"), "status": fm.get("status"), "snippet": sn}
                           for s, p, fm, sn in results], ensure_ascii=False, indent=2)
    if name == "checkpoint":
        old = sys.stdout
        buf = io.StringIO()
        sys.stdout = buf
        try:
            checkpoint(_Args(
                task=None, objective=None, phase=args_d.get("phase"),
                completed=args_d.get("completed"), in_progress=args_d.get("in_progress"),
                blockers=args_d.get("blockers"), decisions=None,
                next=args_d.get("next"), memory=None,
                reason=args_d.get("reason", "mcp"), json=True))
        finally:
            sys.stdout = old
        return buf.getvalue()
    if name == "guard":
        rc = guard()
        return f"exit={rc}"
    if name == "remember":
        remember(_Args(
            type=args_d.get("type", "knowledge"), status="active",
            title=args_d.get("title", "untitled"), scope=args_d.get("scope", ""),
            tags=args_d.get("tags", ""), evidence=args_d.get("evidence", ""),
            body=args_d.get("body", ""), consequence=args_d.get("consequence", ""),
            links=""))
        return "ok"
    if name == "status":
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            memory_status(_Args(json=True))
        finally:
            sys.stdout = old
        return buf.getvalue()
    if name == "tasks":
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            tasks_cmd(_Args(json=True))
        finally:
            sys.stdout = old
        return buf.getvalue()
    if name == "resume":
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            resume_cmd(_Args(json=True, discard_state=False))
        finally:
            sys.stdout = old
        return buf.getvalue()
    raise ValueError(f"unknown tool: {name}")


# ----------------------------- main / arg parsing ---------------------------

def main() -> None:
    ap = argparse.ArgumentParser(prog="irag.py", description=f"INTERNAL_RAG v{VERSION}")
    ap.add_argument("--version", action="version", version=VERSION)
    ap.add_argument("--quiet", action="store_true", help="Suppress non-essential output.")
    ap.add_argument("--verbose", action="store_true", help="Show extra detail.")
    ap.add_argument("--embeddings", choices=["on", "off", "auto"], default=None,
                    help="Override retrieval engine for this invocation.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    p = sub.add_parser("index")
    p.add_argument("--rebuild", action="store_true", help="Rebuild the SQLite index from Markdown.")
    p.add_argument("--status", action="store_true", help="Show SQLite index status.")
    p.add_argument("--vacuum", action="store_true", help="VACUUM the database and clean stale embeddings.")
    p.add_argument("--embed-missing", action="store_true", help="Show missing/stale embeddings for the configured model.")
    p.add_argument("--json", action="store_true")
    sub.add_parser("validate")
    sub.add_parser("guard")
    sub.add_parser("compact")
    sub.add_parser("mcp")

    p = sub.add_parser("doctor")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("embeddings-info")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("context")
    p.add_argument("--task", required=True)
    p.add_argument("--limit", type=int, default=6)
    p.add_argument("--type", nargs="*", default=None, help="Filter by memory type(s).")
    p.add_argument("--status", nargs="*", default=None, help="Filter by memory status(es).")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("checkpoint")
    p.add_argument("--reason", default="manual")
    p.add_argument("--task")
    p.add_argument("--objective")
    p.add_argument("--phase")
    p.add_argument("--completed")
    p.add_argument("--in-progress", dest="in_progress")
    p.add_argument("--blockers")
    p.add_argument("--decisions")
    p.add_argument("--next")
    p.add_argument("--memory")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("search")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--type", nargs="*", default=None, help="Filter by memory type(s).")
    p.add_argument("--status", nargs="*", default=None, help="Filter by memory status(es).")
    p.add_argument("--json", action="store_true")
    p.add_argument("--explain", action="store_true", help="Include per-channel scoring breakdown in JSON output.")
    p.add_argument("--embeddings", choices=["on", "off", "auto"], default=None)

    p = sub.add_parser("remember")
    p.add_argument("--type", required=True, choices=sorted(ALLOWED_TYPES))
    p.add_argument("--status", default="active", choices=sorted(ALLOWED_STATUS))
    p.add_argument("--title", required=True)
    p.add_argument("--scope", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--evidence", default="")
    p.add_argument("--body", required=True)
    p.add_argument("--consequence", default="")
    p.add_argument("--links", default="")
    p.add_argument("--force", action="store_true", help="Create even if a similar/conflicting memory exists.")
    p.add_argument("--allow-secret", action="store_true", help="Bypass secret-pattern scan (use with caution).")

    p = sub.add_parser("remember-batch")
    p.add_argument("file", help="JSON file: array of {type, title, body, ...}")

    p = sub.add_parser("clean")
    p.add_argument("--force", action="store_true", help="Confirm permanent deletion.")

    p = sub.add_parser("show")
    p.add_argument("ref")
    p.add_argument("--section")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("update")
    p.add_argument("ref")
    p.add_argument("--status", choices=sorted(ALLOWED_STATUS))
    p.add_argument("--verified")
    p.add_argument("--add-tags")
    p.add_argument("--remove-tags")
    p.add_argument("--append")

    p = sub.add_parser("supersede")
    p.add_argument("ref")
    p.add_argument("--by")
    p.add_argument("--reason")

    p = sub.add_parser("forget")
    p.add_argument("ref")

    p = sub.add_parser("link")
    p.add_argument("--from", dest="from_ref", required=True)
    p.add_argument("--to", dest="to_ref", required=True)

    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("diff")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("timeline")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("history")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("forget-task")
    p.add_argument("id", nargs="?")

    p = sub.add_parser("tasks")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("resume")
    p.add_argument("--discard-state", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("push")
    p.add_argument("--task", required=True)
    p.add_argument("--reason", default="user")

    p = sub.add_parser("export")

    p = sub.add_parser("import")
    p.add_argument("file")
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("migrate-usage")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--strip", action="store_true", help="Also remove last_accessed from Markdown.")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("config")
    p.add_argument("--json", action="store_true")
    p.add_argument("--init", action="store_true")
    p.add_argument("--validate", action="store_true", help="Validate config values.")

    a = ap.parse_args()

    if a.cmd == "init":
        init_repo()
    elif a.cmd == "context":
        raise SystemExit(context(a))
    elif a.cmd == "checkpoint":
        checkpoint(a)
    elif a.cmd == "guard":
        raise SystemExit(guard())
    elif a.cmd == "search":
        types_f = getattr(a, "type", None)
        statuses_f = getattr(a, "status", None)
        emb_override = getattr(a, "embeddings", None)
        want_explain = getattr(a, "explain", False)
        if emb_override:
            cfg = load_config()
            cfg["retrieval"]["embeddings"] = emb_override
            r = _search_with_cfg(a.query, a.limit, cfg, types=types_f, statuses=statuses_f, explain=want_explain)
        else:
            r = search(a.query, a.limit, types=types_f, statuses=statuses_f, explain=want_explain)
        if a.json:
            items = []
            for s, p, fm, sn in r:
                item = {"path": str(p.relative_to(ROOT)), "score": round(s, 2),
                        "type": fm.get("type"), "status": fm.get("status"),
                        "snippet": sn, "matched_tokens": _matched_for(fm, a.query)}
                if want_explain and "_explain" in fm:
                    item["explain"] = fm.pop("_explain")
                items.append(item)
            print(json.dumps(items, ensure_ascii=False, indent=2))
        elif getattr(a, "verbose", False) and r:
            for i, (s, p, fm, sn) in enumerate(r, 1):
                print(f"{i}. {p.relative_to(ROOT)} score={s:.2f}")
                print(f"   type={fm.get('type')} status={fm.get('status')}")
                print(f"   {sn}")
        else:
            print("No matching durable memories." if not r else "\n".join(
                f"{i}. {p.relative_to(ROOT)} score={s:.1f}\n   {sn}"
                for i, (s, p, fm, sn) in enumerate(r, 1)))
    elif a.cmd == "remember":
        remember(a)
    elif a.cmd == "remember-batch":
        raise SystemExit(remember_batch(a))
    elif a.cmd == "clean":
        raise SystemExit(clean_cmd(a))
    elif a.cmd == "show":
        raise SystemExit(show_memory(a))
    elif a.cmd == "update":
        raise SystemExit(update_memory(a))
    elif a.cmd == "supersede":
        raise SystemExit(supersede(a))
    elif a.cmd == "forget":
        raise SystemExit(forget(a))
    elif a.cmd == "link":
        raise SystemExit(link_memories(a))
    elif a.cmd == "status":
        raise SystemExit(memory_status(a))
    elif a.cmd == "diff":
        raise SystemExit(diff_memory(a))
    elif a.cmd == "timeline":
        raise SystemExit(timeline(a))
    elif a.cmd == "history":
        raise SystemExit(history_cmd(a))
    elif a.cmd == "index":
        raise SystemExit(index_cmd(a))
    elif a.cmd == "validate":
        raise SystemExit(validate())
    elif a.cmd == "tasks":
        raise SystemExit(tasks_cmd(a))
    elif a.cmd == "resume":
        raise SystemExit(resume_cmd(a))
    elif a.cmd == "forget-task":
        raise SystemExit(forget_task_cmd(a))
    elif a.cmd == "push":
        push_task(a.task, a.reason)
        print(f"Pushed task: {a.task} (stack depth: {len(load_tasks().get('stack', []))})")
    elif a.cmd == "compact":
        compact_working_state()
    elif a.cmd == "doctor":
        raise SystemExit(doctor(a))
    elif a.cmd == "export":
        raise SystemExit(export_cmd(a))
    elif a.cmd == "import":
        raise SystemExit(import_cmd(a))
    elif a.cmd == "migrate-usage":
        raise SystemExit(migrate_usage_cmd(a))
    elif a.cmd == "embeddings-info":
        raise SystemExit(embeddings_info(a))
    elif a.cmd == "config":
        raise SystemExit(config_cmd(a))
    elif a.cmd == "mcp":
        raise SystemExit(mcp_server())


if __name__ == "__main__":
    main()