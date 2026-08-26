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
    if last_accessed:
        try:
            age_days = (now_ts - float(last_accessed)) / 86400.0
        except (ValueError, TypeError):
            age_days = 999
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
        last_accessed = u.get("last_accessed")
        access_count = u.get("access_count", 0)

        # Compute age
        if last_accessed:
            try:
                age_days = (now_ts - float(last_accessed)) / 86400.0
            except (ValueError, TypeError):
                age_days = 999
        else:
            created = fm.get("created", "")
            try:
                from datetime import datetime
                ct = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_days = (now_ts - ct.timestamp()) / 86400.0
            except Exception:
                age_days = 999

        value = _compute_memory_value(fm, u, now_ts=now_ts)

        # Determine action
        action = "keep"
        reason = ""

        if retention == "archived":
            # Already archived — check grace period for physical deletion
            archived_at = fm.get("archived_at", "")
            if archived_at:
                try:
                    from datetime import datetime
                    at = datetime.fromisoformat(archived_at.replace("Z", "+00:00"))
                    archive_age_days = (now_ts - at.timestamp()) / 86400.0
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
                except Exception:
                    pass
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


def gc_run(rag_dir: Path, plan: Dict[str, Any], apply: bool = False,
           ) -> Dict[str, Any]:
    """Execute a GC plan. If apply=False, only reports. If apply=True, executes.

    Execution:
      - deprioritize: no file change (just reported; priority is derived at
        retrieval time from usage data)
      - archive: move to archive/ directory (like forget)
      - delete: unlink the file (only for archived memories past grace period)
    """
    results: List[Dict[str, Any]] = []
    archived = 0
    deleted = 0
    deprioritized = 0

    archive_dir = rag_dir / "archive"
    if apply:
        archive_dir.mkdir(exist_ok=True)

    for c in plan.get("candidates", []):
        path = Path(c["path"])
        action = c["action"]

        if action == "deprioritize":
            deprioritized += 1
            results.append({**c, "executed": apply, "result": "deprioritized (no file change)"})
            continue

        if action == "archive":
            if apply and path.exists():
                dst = archive_dir / path.name
                try:
                    path.rename(dst)
                    archived += 1
                    results.append({**c, "executed": True, "result": f"archived to {dst}"})
                except Exception as e:
                    results.append({**c, "executed": False, "result": f"error: {e}"})
            else:
                results.append({**c, "executed": False, "result": "would archive"})
            continue

        if action == "delete":
            if apply and path.exists():
                try:
                    path.unlink()
                    deleted += 1
                    results.append({**c, "executed": True, "result": "deleted"})
                except Exception as e:
                    results.append({**c, "executed": False, "result": f"error: {e}"})
            else:
                results.append({**c, "executed": False, "result": "would delete"})
            continue

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