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
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = "1.0.0"

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
    "retrieval": {"limit": 8, "mmr_lambda": 0.5, "min_score": 0.5, "embeddings": "auto"},
    "tokens": {"context_budget": 4000, "warn_ratio": 0.8},
    "checkpoints": {"auto_archive_sessions": True, "max_task_stack": 16},
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


def load_checkpoint() -> Dict[str, Any]:
    try:
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_checkpoint(reason: str) -> Dict[str, Any]:
    data = {
        "version": VERSION, "at": now(), "reason": reason,
        "fingerprint": project_fingerprint(), "branch": git_text("branch", "--show-current"),
        "head": git_text("rev-parse", "--short", "HEAD"),
    }
    CHECKPOINT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


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
    health = (
        "- RECOVERY REQUIRED: project code differs from the last checkpoint.\n"
        "- Inspect `git status` and `git diff`, reconstruct state, checkpoint it, then run guard."
        if recovery else
        "- Checkpoint fingerprint matches current project state.\n"
        "- Create a task-start checkpoint before the first new code edit."
    )
    text = set_section(text, "Checkpoint health", health)
    text = set_header(text, "updated", now())
    save_working(text)
    results = search(task, limit)
    ws_text = WORKING.read_text(encoding="utf-8", errors="replace")
    ws_tokens = estimate_tokens(ws_text)
    mem_tokens = sum(estimate_tokens(sn) for _, _, _, sn in results)
    budget = int(cfg.get("tokens", {}).get("context_budget", 4000))
    if args.json:
        out = {
            "irag_version": VERSION, "task": task,
            "recovery_required": bool(recovery),
            "working_state": ws_text[:10000],
            "working_state_tokens": ws_tokens,
            "candidate_memories": [
                {"path": str(p.relative_to(ROOT)), "type": fm.get("type", "?"),
                 "status": fm.get("status", "?"), "score": round(score, 2), "snippet": sn}
                for score, p, fm, sn in results
            ],
            "memory_tokens": mem_tokens,
            "context_budget": budget,
            "next": "RECOVER -> CHECKPOINT -> GUARD OK -> continue." if recovery
                    else "Checkpoint before first code edit, then continue.",
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    print("# INTERNAL_RAG CONTEXT PACKET")
    print("irag_version:", VERSION)
    print("task:", task)
    print("recovery_required:", "YES" if recovery else "NO")
    print(f"tokens: working_state={ws_tokens} memories={mem_tokens} budget={budget}")
    if recovery:
        print("\n!!! RECOVERY REQUIRED !!!\nInspect git status/diff and checkpoint recovered state BEFORE new edits.")
    print("\n## WORKING_STATE\n" + ws_text[:10000].rstrip())
    print("\n## CANDIDATE MEMORIES")
    if not results:
        print("No relevant durable memories found.")
    for i, (score, p, fm, snip) in enumerate(results, 1):
        print(f"{i}. {p.relative_to(ROOT)} [{fm.get('type','?')}/{fm.get('status','?')}] score={score:.1f}")
        print(f"   {snip}")
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


def bm25_search(query: str, candidates: List[Tuple[Path, str, Dict[str, Any]]],
                limit: int, cfg: Dict[str, Any]) -> List[Tuple[float, Path, Dict[str, Any], str, List[str]]]:
    k1 = 1.5
    b = 0.75
    q_tokens = tokenize(query)
    if not q_tokens:
        q_tokens = re.findall(r"[A-Za-z0-9_./:@+-]{2,}", query.lower())
    docs_tok: List[List[str]] = []
    docs_body: List[str] = []
    for p, text, fm in candidates:
        header = "\n".join(text.splitlines()[:40])
        body = "\n".join(text.splitlines())
        rel = str(p.relative_to(ROOT))
        combined = f"{rel}\n{header}\n{body}"
        docs_body.append(combined)
        docs_tok.append(tokenize(combined))
    N = len(docs_tok)
    if N == 0:
        return []
    avgdl = sum(len(d) for d in docs_tok) / N
    df: Dict[str, int] = {}
    for d in docs_tok:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    idf = {t: max(0.0, ((N - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5) + 1.0)) for t in q_tokens}
    scored: List[Tuple[float, int, List[str]]] = []
    for i, d in enumerate(docs_tok):
        tf: Dict[str, int] = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        matched: List[str] = []
        for t in q_tokens:
            if t in tf:
                matched.append(t)
                denom = tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / max(avgdl, 1)))
                score += idf[t] * denom
        fm = candidates[i][2]
        status = str(fm.get("status", "active")).lower()
        if status == "active":
            score += 1.0
        elif status == "tentative":
            score += 0.3
        elif status == "superseded":
            score -= 4.0
        elif status in ("invalid", "archived"):
            score -= 100.0
        if score > 0:
            scored.append((score, i, matched))
    scored.sort(key=lambda x: -x[0])
    top = scored[: min(limit * 4, len(scored))]
    min_score = float(cfg.get("retrieval", {}).get("min_score", 0.5))
    top = [x for x in top if x[0] >= min_score]
    lam = float(cfg.get("retrieval", {}).get("mmr_lambda", 0.5))
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
    """Try sentence-transformers via irag_embeddings.py. Returns None if unavailable."""
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


def search(query: str, limit: int = 8) -> List[Tuple[float, Path, Dict[str, Any], str]]:
    cfg = load_config()
    if limit <= 0:
        limit = int(cfg.get("retrieval", {}).get("limit", 8))
    cands: List[Tuple[Path, str, Dict[str, Any]]] = []
    for p in memory_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_fm(text)
        status = str(fm.get("status", "active")).lower()
        if status in {"invalid", "archived"}:
            continue
        cands.append((p, text, fm))
    if not cands:
        return []
    emb = embeddings_search(query, cands, limit, cfg)
    if emb is not None:
        return [(s, p, fm, sn) for s, p, fm, sn, _ in emb]
    bm = bm25_search(query, cands, limit, cfg)
    return [(s, p, fm, sn) for s, p, fm, sn, _ in bm]


# ----------------------------- remember -------------------------------------

def remember(args) -> None:
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
        "---\n\n"
        f"# {args.title}\n\n"
        "## Knowledge\n\n"
        f"{args.body.strip()}\n\n"
        "## Consequence\n\n"
        f"{(args.consequence or 'To be determined.').strip()}\n"
    )
    if args.links:
        links = [x.strip() for x in args.links.split(",") if x.strip()]
        if links:
            content += "\n## Links\n\n" + "\n".join(f"- {x}" for x in links) + "\n"
    path.write_text(content, encoding="utf-8")
    rebuild_index()
    print(path.relative_to(ROOT))


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
    print(f"Validation complete: {errors} error(s), {warnings} warning(s).")
    return 1 if errors else 0


# ----------------------------- tasks (multi-task stack) ---------------------

def load_tasks() -> Dict[str, Any]:
    try:
        return json.loads(TASKS.read_text(encoding="utf-8"))
    except Exception:
        return {"stack": [], "completed": []}


def save_tasks(data: Dict[str, Any]) -> None:
    RAG.mkdir(exist_ok=True)
    cfg = load_config()
    max_stack = int(cfg.get("checkpoints", {}).get("max_task_stack", 16))
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
    """Pop the top task from the stack and restore its WORKING_STATE."""
    top = pop_task()
    if top is None:
        print("No task to resume (stack is empty).", file=sys.stderr)
        return 1
    ws = top.get("working_state", "")
    if ws and not args.discard_state:
        save_working(ws)
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
    n = len(data.get("stack", []))
    data["stack"] = []
    save_tasks(data)
    print(f"Cleared task stack ({n} task(s) dropped).")
    return 0


def compact_working_state() -> None:
    """Compact WORKING_STATE.md: keep only the most recent checkpoint snapshot
    in sessions/.snapshots/ and trim the file to its latest meaningful state."""
    if not WORKING.exists():
        print("No WORKING_STATE.md to compact.")
        return
    text = WORKING.read_text(encoding="utf-8", errors="replace")
    # Archive current snapshot before compaction
    try:
        snap_dir = RAG / "sessions" / ".snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        (snap_dir / f"pre-compact-{stamp}.md").write_text(text, encoding="utf-8")
    except Exception:
        pass
    # Trim Recovery snapshot and Relevant files to last-20 entries (keep concise)
    rs = get_section(text, "Recovery snapshot")
    if rs:
        rs_lines = rs.splitlines()
        if len(rs_lines) > 20:
            text = set_section(text, "Recovery snapshot", "\n".join(rs_lines[:20]) + "\n- (older entries trimmed by compact)")
    rf = get_section(text, "Relevant files")
    if rf:
        rf_lines = rf.splitlines()
        if len(rf_lines) > 20:
            text = set_section(text, "Relevant files", "\n".join(rf_lines[:20]) + "\n- (older entries trimmed by compact)")
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
        issues.append({"severity": "info", "issue": f"config: {CONFIG_PATH.relative_to(ROOT)}"})
    else:
        issues.append({"severity": "info", "issue": "config: defaults (no .irag.yml)"})
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
    info = {"configured": mode, "available": avail,
            "engine": "sentence-transformers" if avail else "bm25-fallback",
            "plugin_path": str(ROOT / ".agents" / "skills" / "internal-rag" / "irag_embeddings.py")}
    if args.json:
        print(json.dumps(info, indent=2))
        return 0
    print(f"Embeddings configured: {mode}")
    print(f"Available: {avail}")
    print(f"Engine: {info['engine']}")
    print(f"Plugin: {info['plugin_path']}")
    return 0


# ----------------------------- config ---------------------------------------

def config_cmd(args) -> int:
    cfg = load_config()
    if args.json:
        print(json.dumps(cfg, indent=2))
        return 0
    if not CONFIG_PATH.exists():
        print(f"No {CONFIG_PATH.relative_to(ROOT)} - using built-in defaults.")
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
        results = search(q, limit)
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
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("index")
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
    p.add_argument("--json", action="store_true")

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

    p = sub.add_parser("show")
    p.add_argument("ref")
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

    sub.add_parser("forget-task")

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

    p = sub.add_parser("config")
    p.add_argument("--json", action="store_true")

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
        r = search(a.query, a.limit)
        if a.json:
            print(json.dumps([{"path": str(p.relative_to(ROOT)), "score": round(s, 2),
                               "type": fm.get("type"), "status": fm.get("status"), "snippet": sn}
                              for s, p, fm, sn in r], ensure_ascii=False, indent=2))
        else:
            print("No matching durable memories." if not r else "\n".join(
                f"{i}. {p.relative_to(ROOT)} score={s:.1f}\n   {sn}"
                for i, (s, p, fm, sn) in enumerate(r, 1)))
    elif a.cmd == "remember":
        remember(a)
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
    elif a.cmd == "index":
        rebuild_index()
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
    elif a.cmd == "embeddings-info":
        raise SystemExit(embeddings_info(a))
    elif a.cmd == "config":
        raise SystemExit(config_cmd(a))
    elif a.cmd == "mcp":
        raise SystemExit(mcp_server())


if __name__ == "__main__":
    main()