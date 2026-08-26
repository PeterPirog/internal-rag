#!/usr/bin/env python3
"""irag_gc.py — retention + garbage collection for MCP Light Memory.

Non-aggressive lifecycle management. Never auto-deletes important knowledge.

Retention classes:
  - ephemeral_observations: TTL-based, auto-delete on expiry
  - session_snapshots: configurable max_age/count/bytes
  - tentative_hypotheses: low priority, GC candidate after long disuse
  - normal_durable: standard retention
  - protected: decisions/constraints — never GC'd

Decay logic (4 stages, never immediate deletion):
  1. Reduce retrieval priority for unused low-value memories
  2. Mark as GC/archive candidate
  3. Archive after policy satisfied
  4. Physical removal only after additional grace period + explicit policy

Factors:
  - created time, last accessed, access count, confidence, status, type,
    evidence freshness, link/reference count, reinforcement/recent verification

CLI:
  gc --dry-run            (safe default: report only)
  gc --apply              (execute the plan)
  gc --json               (machine-readable)
  gc --grace-days N       (override grace period)

Stdlib-only (Python 3.8+). No external dependencies.
"""
from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Retention classes (from most protected to least)
PROTECTED_TYPES = frozenset(["decision", "constraint"])
PROTECTED_STATUSES = frozenset(["active"])
GC_CANDIDATE_STATUSES = frozenset(["tentative", "superseded", "invalid"])

# Default grace period before physical deletion after archiving
DEFAULT_GRACE_DAYS = 30

# Default decay thresholds
DEFAULT_STALE_DAYS = 90          # not accessed in 90 days -> reduce priority
DEFAULT_GC_CANDIDATE_DAYS = 180  # not accessed in 180 days -> GC candidate
DEFAULT_ARCHIVE_AFTER_DAYS = 365 # archive after 1 year of disuse


def _parse_ts(value: Any) -> Optional[float]:
    """Parse a timestamp value into a UNIX epoch float, or None if unparseable.

    Accepts:
      - int / float epoch seconds (e.g. 1756178400.0)
      - ISO-8601 date or datetime strings (e.g. '2026-08-26', '2026-08-26T10:00:00',
        with 'Z' or explicit UTC offset, as written by irag_index.record_access)

    NOTE: irag_index stores `last_accessed` as an ISO *date* string, not an
    epoch float — this helper is the single place that normalizes both forms.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        return v if v > 0 else None
    s = str(value).strip()
    if not s:
        return None
    # Numeric string -> epoch seconds
    try:
        v = float(s)
        return v if v > 0 else None
    except (ValueError, OverflowError):
        pass
    # ISO-8601 (Python 3.7+ fromisoformat; handle trailing 'Z')
    iso = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        # Try a couple of common explicit formats as a fallback
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        # Naive date/datetime is stored as local wall-clock; interpret as local.
        dt = dt.astimezone()
    return dt.timestamp()


def _load_usage(rag_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load usage data from SQLite if available. Returns {memory_id: {last_accessed, access_count}}."""
    try:
        import sqlite3
        idx = rag_dir / ".index.sqlite3"
        if not idx.exists():
            return {}
        conn = sqlite3.connect(str(idx), timeout=5)
        try:
            rows = conn.execute(
                "SELECT memory_id, last_accessed, access_count FROM usage"
            ).fetchall()
            return {r[0]: {"last_accessed": r[1], "access_count": r[2]} for r in rows}
        finally:
            conn.close()
    except Exception:
        return {}


def _get_retention_class(fm: Dict[str, Any]) -> str:
    """Determine the retention class for a memory."""
    mtype = fm.get("type", "")
    status = fm.get("status", "active")
    if mtype in PROTECTED_TYPES and status in PROTECTED_STATUSES:
        return "protected"
    if status in GC_CANDIDATE_STATUSES:
        return "gc_candidate"
    if mtype == "hypothesis" and status == "tentative":
        return "tentative_hypothesis"
    if status == "archived":
        return "archived"
    return "normal_durable"


def _compute_memory_value(fm: Dict[str, Any], usage: Dict[str, Any],
                          evidence_state: str = "unverifiable",
                          now_ts: Optional[float] = None) -> float:
    """Compute a 0.0-1.0 memory-value score.

    Factors:
      - recency: how recently accessed (or created)
      - reuse: access count
      - confidence: high/medium/low
      - evidence freshness: present/missing/unverifiable
      - type importance: decisions > knowledge > ... > session
      - reinforcement: links count (being referenced by others)
    """
    if now_ts is None:
        now_ts = time.time()

    mtype = fm.get("type", "session")
    status = fm.get("status", "active")
    confidence = fm.get("confidence", "")
    created = fm.get("created", "")

    # Type importance (0.1 - 1.0)
    type_scores = {
        "decision": 1.0, "constraint": 0.9, "knowledge": 0.7,
        "gotcha": 0.6, "failure": 0.5, "hypothesis": 0.3, "session": 0.1,
    }
    type_score = type_scores.get(mtype, 0.1)

    # Status modifier
    status_mod = {"active": 1.0, "tentative": 0.6, "superseded": -4.0,
                  "invalid": -4.0, "archived": -5.0}.get(status, 0.0)

    # Recency (last_accessed or created)
    last_accessed = usage.get("last_accessed")
    la_ts = _parse_ts(last_accessed)
    if la_ts is not None:
        age_days = (now_ts - la_ts) / 86400.0
    else:
        # Fall back to created date
        try:
            from datetime import datetime
            ct = datetime.fromisoformat(created.replace("Z", "+00:00"))
            age_days = (now_ts - ct.timestamp()) / 86400.0
        except Exception:
            age_days = 999
    recency_score = max(0.0, 1.0 - (age_days / 365.0))  # decays over 1 year

    # Reuse (access count)
    access_count = usage.get("access_count", 0)
    reuse_score = min(1.0, access_count / 10.0)  # caps at 10 accesses

    # Confidence
    conf_score = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(confidence, 0.5)

    # Evidence freshness
    evidence_score = {"present": 1.0, "missing": 0.5, "unverifiable": 0.7}.get(
        evidence_state, 0.5)

    # Reinforcement (links count)
    links = fm.get("links", [])
    if isinstance(links, str):
        link_count = len([l for l in links.split(",") if l.strip()])
    else:
        link_count = len(links) if isinstance(links, list) else 0
    reinforcement_score = min(1.0, link_count / 5.0)

    # Weighted combination
    value = (
        0.25 * type_score +
        0.15 * status_mod +
        0.20 * recency_score +
        0.15 * reuse_score +
        0.10 * conf_score +
        0.10 * evidence_score +
        0.05 * reinforcement_score
    )
    return max(0.0, min(1.0, value))


def gc_plan(rag_dir: Path,
            memory_files: List[Tuple[Path, Dict[str, Any]]],
            grace_days: int = DEFAULT_GRACE_DAYS,
            stale_days: int = DEFAULT_STALE_DAYS,
            gc_candidate_days: int = DEFAULT_GC_CANDIDATE_DAYS,
            now_ts: Optional[float] = None,
            ) -> Dict[str, Any]:
    """Build a non-destructive GC plan (dry-run by design).

    `memory_files` is a list of (path, frontmatter) tuples from the caller.

    Returns a dict with:
      - candidates: list of {path, id, type, status, value, reason, action}
      - protected_count: how many memories are protected
      - total: total memories scanned
      - would_archive: count
      - would_delete: count (only after grace period)
      - would_deprioritize: count
    """
    if now_ts is None:
        now_ts = time.time()

    usage = _load_usage(rag_dir)
    candidates: List[Dict[str, Any]] = []
    protected_count = 0
    would_archive = 0
    would_delete = 0
    would_deprioritize = 0

    for path, fm in memory_files:
        mid = str(fm.get("id", path.name))
        mtype = fm.get("type", "session")
        status = fm.get("status", "active")
        retention = _get_retention_class(fm)

        if retention == "protected":
            protected_count += 1
            continue

        u = usage.get(mid, {})
        access_count = u.get("access_count", 0)

        # Compute age (last_accessed may be an ISO date string or epoch float —
        # _parse_ts normalizes both; unparseable falls back to created)
        la_ts = _parse_ts(u.get("last_accessed"))
        if la_ts is not None:
            age_days = (now_ts - la_ts) / 86400.0
        else:
            created = fm.get("created", "")
            c_ts = _parse_ts(created)
            age_days = (now_ts - c_ts) / 86400.0 if c_ts is not None else 999

        value = _compute_memory_value(fm, u, now_ts=now_ts)

        # Determine action
        action = "keep"
        reason = ""

        if retention == "archived":
            # Already archived — check grace period for physical deletion
            archived_at = fm.get("archived_at", "") or fm.get("superseded_at", "")
            at_ts = _parse_ts(archived_at)
            if at_ts is not None:
                archive_age_days = (now_ts - at_ts) / 86400.0
                if archive_age_days > grace_days:
                    action = "delete"
                    reason = f"archived {archive_age_days:.0f}d ago, value={value:.2f}, grace={grace_days}d"
                    would_delete += 1
                    candidates.append({
                        "path": str(path),
                        "id": mid,
                        "type": mtype,
                        "status": status,
                        "value": round(value, 3),
                        "age_days": round(age_days, 1),
                        "access_count": access_count,
                        "reason": reason,
                        "action": action,
                        "retention_class": retention,
                    })
            continue

        if age_days > gc_candidate_days and value < 0.3:
            action = "archive"
            reason = f"not accessed in {age_days:.0f}d, value={value:.2f}, type={mtype}"
            would_archive += 1
        elif age_days > stale_days and value < 0.5:
            action = "deprioritize"
            reason = f"stale ({age_days:.0f}d), value={value:.2f}, reducing retrieval priority"
            would_deprioritize += 1

        if action != "keep":
            candidates.append({
                "path": str(path),
                "id": mid,
                "type": mtype,
                "status": status,
                "value": round(value, 3),
                "age_days": round(age_days, 1),
                "access_count": access_count,
                "reason": reason,
                "action": action,
                "retention_class": retention,
            })

    return {
        "candidates": candidates,
        "protected_count": protected_count,
        "total": len(memory_files),
        "would_archive": would_archive,
        "would_delete": would_delete,
        "would_deprioritize": would_deprioritize,
    }


def _set_fm_field(text: str, key: str, value: str) -> str:
    """Insert or update a single frontmatter scalar field `key: value`.

    Frontmatter block is delimited by the first two '---' lines. If `key` is
    already present it is replaced in place (preserving order); otherwise the
    line is appended before the closing '---'. Body is untouched.
    """
    lines = text.split("\n")
    # locate closing '---' of frontmatter
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        return text
    new_line = f"{key}: {value}"
    for i in range(1, close):
        if lines[i].startswith(f"{key}:"):
            lines[i] = new_line
            return "\n".join(lines)
    lines.insert(close, new_line)
    return "\n".join(lines)


def gc_run(rag_dir: Path, plan: Dict[str, Any], apply: bool = False,
           write_lock: Optional[Any] = None,
           atomic_write: Optional[Any] = None,
           ) -> Dict[str, Any]:
    """Execute a GC plan. If apply=False, only reports. If apply=True, executes.

    Execution:
      - deprioritize: frontmatter `priority: low` (retrieval recency_boost
        reads this; reversible — no file move). If `write_lock` is a
        ProjectWriteLock context manager, all mutations run under it.
      - archive: frontmatter `status: archived` + `archived_at` set, THEN move
        to archive/ (metadata first, so the file is never lost to a crash).
      - delete: unlink the file (only for archived memories past grace period).
    """
    if atomic_write is None:
        try:
            from irag_atomic import atomic_write_text as _awt
            atomic_write = _awt
        except Exception:
            atomic_write = lambda p, c, encoding="utf-8": Path(p).write_text(c, encoding=encoding)

    def _w(p: Path, content: str) -> None:
        atomic_write(p, content, encoding="utf-8")

    results: List[Dict[str, Any]] = []
    archived = 0
    deleted = 0
    deprioritized = 0

    archive_dir = rag_dir / "archive"
    if apply:
        archive_dir.mkdir(exist_ok=True)

    today = time.strftime("%Y-%m-%d", time.gmtime())

    candidates = list(plan.get("candidates", []))

    def _run_locked():
        nonlocal archived, deleted, deprioritized

        for c in candidates:
            path = Path(c["path"])
            action = c["action"]

            if action == "deprioritize":
                if path.exists():
                    try:
                        text = path.read_text(encoding="utf-8", errors="replace")
                        new_text = _set_fm_field(text, "priority", "low")
                        if new_text != text:
                            _w(path, new_text)
                        deprioritized += 1
                        results.append({**c, "executed": True,
                                        "result": "deprioritized (priority: low)"})
                    except Exception as e:
                        results.append({**c, "executed": False, "result": f"error: {e}"})
                else:
                    results.append({**c, "executed": False, "result": "would deprioritize"})
                continue

            if action == "archive":
                if path.exists():
                    try:
                        # metadata first (crash-safe: file keeps its identity),
                        # then move
                        text = path.read_text(encoding="utf-8", errors="replace")
                        new_text = _set_fm_field(text, "archived_at", today)
                        new_text = _set_fm_field(new_text, "status", "archived")
                        if new_text != text:
                            _w(path, new_text)
                        dst = archive_dir / path.name
                        n = 1
                        while dst.exists():
                            dst = archive_dir / f"{path.stem}-{n}.md"
                            n += 1
                        path.rename(dst)
                        archived += 1
                        results.append({**c, "executed": True, "result": f"archived to {dst}"})
                    except Exception as e:
                        results.append({**c, "executed": False, "result": f"error: {e}"})
                else:
                    results.append({**c, "executed": False, "result": "would archive"})
                continue

            if action == "delete":
                if path.exists():
                    try:
                        path.unlink()
                        deleted += 1
                        results.append({**c, "executed": True, "result": "deleted"})
                    except Exception as e:
                        results.append({**c, "executed": False, "result": f"error: {e}"})
                else:
                    results.append({**c, "executed": False, "result": "would delete"})
                continue

    if apply and write_lock is not None:
        with write_lock:
            _run_locked()
    elif apply:
        _run_locked()
    else:
        # dry-run: report what would happen, no file changes
        for c in candidates:
            action = c["action"]
            results.append({
                **c, "executed": False,
                "result": f"would {action}",
            })

    return {
        "applied": apply,
        "archived": archived,
        "deleted": deleted,
        "deprioritized": deprioritized,
        "results": results,
    }


def snapshot_gc_plan(rag_dir: Path,
                     max_age_days: int = 30,
                     max_count: int = 20,
                     max_bytes: int = 0,  # 0 = unlimited
                     ) -> Dict[str, Any]:
    """Build a session snapshot cleanup plan.

    Removes only snapshots that are safe to delete (not the active recovery
    point). Returns a dry-run plan.
    """
    snap_dir = rag_dir / "sessions" / ".snapshots"
    if not snap_dir.exists():
        return {"candidates": [], "total": 0, "would_delete": 0}

    snapshots = sorted(snap_dir.glob("*.md"), key=lambda p: p.stat().st_mtime,
                       reverse=True)
    # The most recent snapshot is the active recovery point — never delete it
    if not snapshots:
        return {"candidates": [], "total": 0, "would_delete": 0}

    active = snapshots[0]
    now_ts = time.time()
    candidates: List[Dict[str, Any]] = []
    total_bytes = sum(s.stat().st_size for s in snapshots)

    for i, snap in enumerate(snapshots[1:]):  # skip active
        age_days = (now_ts - snap.stat().st_mtime) / 86400.0
        reason = ""
        should_delete = False

        if age_days > max_age_days:
            reason = f"age {age_days:.0f}d > max_age {max_age_days}d"
            should_delete = True
        elif i + 1 > max_count - 1:  # -1 for the active snapshot
            reason = f"count {i+2} > max_count {max_count}"
            should_delete = True
        elif max_bytes > 0 and total_bytes > max_bytes:
            reason = f"total_bytes {total_bytes} > max_bytes {max_bytes}"
            should_delete = True

        if should_delete:
            candidates.append({
                "path": str(snap),
                "age_days": round(age_days, 1),
                "size_bytes": snap.stat().st_size,
                "reason": reason,
            })

    return {
        "candidates": candidates,
        "total": len(snapshots),
        "active_recovery_point": str(active),
        "would_delete": len(candidates),
    }


def snapshot_gc_run(plan: Dict[str, Any], apply: bool = False) -> Dict[str, Any]:
    """Execute a snapshot cleanup plan."""
    deleted = 0
    results: List[Dict[str, Any]] = []

    for c in plan.get("candidates", []):
        path = Path(c["path"])
        if apply and path.exists():
            try:
                path.unlink()
                deleted += 1
                results.append({**c, "executed": True})
            except Exception as e:
                results.append({**c, "executed": False, "error": str(e)})
        else:
            results.append({**c, "executed": False})

    return {"applied": apply, "deleted": deleted, "results": results}