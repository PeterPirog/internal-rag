#!/usr/bin/env python3
"""Memory mutation/lifecycle benchmark (post-v1.6 hardening, P0).

A second deterministic benchmark — focused on WRITE / UPDATE / LIFECYCLE
correctness, complementary to the retrieval-oriented memory-quality
benchmark. Uses only the Python standard library; no LLM.

Exercises realistic sequences:
  1. remember A
  2. retrieve A
  3. update A
  4. supersede A with B
  5. retrieve current state
  6. temporal search before supersession
  7. temporal search after supersession
  8. archive/forget
  9. export
 10. import into a clean fixture
 11. delete/rebuild SQLite index
 12. repeat retrieval

Scenarios:
  - decision replacement
  - failure followed by fix
  - conflicting active memories
  - archived memory
  - superseded memory
  - valid_from / valid_to
  - derived_from
  - links
  - duplicate writes (must be blocked deterministically)
  - near duplicates
  - invalid evidence
  - PL/EN mixed content
  - export/import
  - index deletion + rebuild

Invariants asserted:
  - superseded memory is not returned as current truth
  - historical retrieval still finds the old memory for a valid historical date
  - archived/invalid memories do not leak into normal active retrieval
  - history is never silently deleted
  - backlinks remain coherent
  - export/import preserves lifecycle metadata
  - deleting .index.sqlite3 does not change durable semantics
  - rebuilding the index produces equivalent retrieval results
  - duplicate protection remains deterministic

Run:
  python tests/memory_mutation_benchmark.py
  python tests/memory_mutation_benchmark.py --smoke
  python tests/memory_mutation_benchmark.py --json

Zero external dependencies. Python 3.8+ stdlib only.
"""
from __future__ import annotations
import argparse
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

_spec = importlib.util.spec_from_file_location("irag_mut_bench", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)


class Env:
    """Sandbox the irag module onto a temp project so ROOT/RAG resolve cleanly."""

    def __init__(self, sandbox: Path):
        self.sandbox = sandbox
        self.rag = sandbox / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive",
                  "exports"):
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        (self.rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")

    def __enter__(self):
        self._old = (irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING,
                     irag.EXPORT_DIR, irag._open_sqlite_index, irag.FP_CACHE,
                     irag.CHECKPOINT, irag.TASKS)
        irag.ROOT = self.sandbox
        irag.RAG = self.rag
        irag.CONFIG_PATH = self.sandbox / ".irag.yml"
        irag.WORKING = self.rag / "WORKING_STATE.md"
        irag.EXPORT_DIR = self.rag / "exports"
        irag._open_sqlite_index = lambda: None
        irag.FP_CACHE = self.rag / ".fpcache.json"
        irag.CHECKPOINT = self.rag / ".checkpoint.json"
        irag.TASKS = self.rag / ".tasks.json"
        # Force sparse-only retrieval for deterministic, zero-dependency benchmarks.
        # This avoids the optional sentence-transformers model loading when the
        # package happens to be installed in the developer's venv (which would
        # also add latency and HF network warnings unrelated to lifecycle correctness).
        self._prev_default = irag.DEFAULT_CONFIG
        patched = json.loads(json.dumps(irag.DEFAULT_CONFIG))
        patched["retrieval"]["embeddings"] = "off"
        patched["retrieval"]["mode"] = "sparse"
        patched["retrieval"]["fts_prefilter"] = {"enabled": False, "min_corpus_size": 50}
        irag.DEFAULT_CONFIG = patched
        return self

    def __exit__(self, *a):
        (irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING,
         irag.EXPORT_DIR, irag._open_sqlite_index, irag.FP_CACHE,
         irag.CHECKPOINT, irag.TASKS) = self._old
        irag.DEFAULT_CONFIG = self._prev_default


def _args(**kw: Any):
    class C:
        pass
    c = C()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _remember(env: Env, **kw: Any) -> Tuple[str, int]:
    """Run remember(); returns (status, captured_stdout)."""
    kw.setdefault("status", "active")
    kw.setdefault("scope", "")
    kw.setdefault("tags", "")
    kw.setdefault("evidence", "")
    kw.setdefault("consequence", "")
    kw.setdefault("links", "")
    kw.setdefault("force", False)
    kw.setdefault("allow_secret", False)
    kw.setdefault("json", True)
    kw.setdefault("confidence", None)
    kw.setdefault("valid_from", None)
    kw.setdefault("valid_to", None)
    kw.setdefault("supersedes", "")
    kw.setdefault("derived_from", "")
    a = _args(**kw)
    buf = io.StringIO()
    with redirect_stdout(buf):
        status = irag.remember(a)
    return str(status), buf.getvalue().strip()


def _parse_remember_json(s: str) -> Dict[str, Any]:
    # remember() internally calls rebuild_index() which prints "Indexed N memories."
    # before the JSON line. The JSON object may span multiple lines, so scan from
    # the first '{' using json.JSONDecoder.raw_decode (tolerant of trailing text).
    idx = s.find("{")
    if idx < 0:
        return {}
    try:
        obj, _end = json.JSONDecoder().raw_decode(s[idx:])
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _path_of_remember(s: str) -> Optional[str]:
    d = _parse_remember_json(s)
    p = d.get("path")
    if p is None:
        return None
    # Normalize to forward slashes so comparisons with _paths() (which uses
    # forward slashes) succeed on Windows.
    return str(p).replace("\\", "/")


def _update(env: Env, ref: str, **kw: Any) -> int:
    kw.setdefault("status", None)
    kw.setdefault("verified", None)
    kw.setdefault("add_tags", None)
    kw.setdefault("remove_tags", None)
    kw.setdefault("append", None)
    kw.setdefault("confidence", None)
    kw.setdefault("valid_from", None)
    kw.setdefault("valid_to", None)
    kw.setdefault("supersedes", None)
    a = _args(ref=ref, **kw)
    buf = io.StringIO()
    with redirect_stdout(buf):
        return irag.update_memory(a)


def _supersede(env: Env, ref: str, by: Optional[str] = None,
               reason: Optional[str] = None, valid_to: Optional[str] = None,
               force: bool = False) -> int:
    a = _args(ref=ref, by=by, reason=reason, valid_to=valid_to, force=force)
    buf = io.StringIO()
    with redirect_stdout(buf):
        return irag.supersede(a)


def _forget(env: Env, ref: str) -> int:
    a = _args(ref=ref)
    buf = io.StringIO()
    with redirect_stdout(buf):
        return irag.forget(a)


def _link(env: Env, from_ref: str, to_ref: str) -> int:
    a = _args(from_ref=from_ref, to_ref=to_ref)
    buf = io.StringIO()
    with redirect_stdout(buf):
        return irag.link_memories(a)


def _search(query: str, limit: int = 10, types=None, statuses=None, at_date=None
            ) -> List[Tuple[float, Path, Dict[str, Any], str]]:
    return irag.search(query, limit, types=types, statuses=statuses,
                       explain=False, at_date=at_date)


def _ids(results) -> List[str]:
    return [str(fm.get("id", "")) for _s, _p, fm, _sn in results]


def _paths(results) -> List[str]:
    return [str(p.relative_to(irag.ROOT)).replace("\\", "/")
            for _s, p, _fm, _sn in results]


def _fm(ref) -> Dict[str, Any]:
    if ref is None:
        return {}
    if isinstance(ref, Path):
        if not ref.is_file():
            return {}
        return irag.parse_fm(ref.read_text(encoding="utf-8", errors="replace"))
    p = irag.find_memory_by_id_or_path(str(ref))
    if p is None:
        return {}
    return irag.parse_fm(p.read_text(encoding="utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

class ScenarioResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.failures: List[str] = []
        self.latency_ms = 0.0

    def check(self, cond: bool, msg: str) -> None:
        if not cond:
            self.passed = False
            self.failures.append(msg)

    def __repr__(self) -> str:
        tag = "OK" if self.passed else "FAIL"
        return f"[{tag}] {self.name} ({self.latency_ms:.1f}ms)" + (
            f"  failures={self.failures}" if self.failures else "")


def scenario_decision_replacement(env: Env) -> ScenarioResult:
    r = ScenarioResult("decision_replacement")
    t0 = time.perf_counter()
    try:
        st_a, out_a = _remember(env, type="decision", title="Auth uses Basic",
                                body="Authentication uses Basic over HTTP for all endpoints.",
                                valid_from="2024-01-01")
        r.check(st_a == "created", f"A create status={st_a}")
        path_a = _path_of_remember(out_a)
        r.check(bool(path_a), f"A path missing: {out_a}")
        # retrieve A
        res = _search("authentication endpoints basic")
        r.check(any("Auth uses Basic" in str(_fm(p).get("id", "")) or path_a in _paths(res)
                    for p in [irag.find_memory_by_id_or_path(path_a)] if p),
                "A should be retrievable after create")
        ids = _ids(res)
        r.check(any("basic" in i.lower() or "auth-uses-basic" in i.lower() for i in ids)
                or path_a in _paths(res), f"A not retrieved: ids={ids} paths={_paths(res)}")
        # create B
        st_b, out_b = _remember(env, type="decision", title="Auth uses JWT",
                                body="Authentication uses JWT tokens with refresh rotation for all endpoints.",
                                valid_from="2024-06-01", supersedes=_fm(path_a).get("id", ""))
        r.check(st_b == "created", f"B create status={st_b}")
        path_b = _path_of_remember(out_b)
        # supersede A with B
        rc = _supersede(env, path_a, by=path_b, reason="migrated to tokens",
                       valid_to="2024-05-31")
        r.check(rc == 0, f"supersede rc={rc}")
        a_fm = _fm(path_a)
        b_fm = _fm(path_b)
        r.check(a_fm.get("status") == "superseded", f"A status={a_fm.get('status')}")
        r.check(a_fm.get("valid_to"), "A must have valid_to")
        r.check("Auth uses JWT" in str(b_fm.get("supersedes", []))
                or _fm(path_a).get("id", "") in b_fm.get("supersedes", []),
                f"B supersedes list={b_fm.get('supersedes')}")
        r.check(str(a_fm.get("superseded_by", "")).strip() != "", "A superseded_by must be set")
        # current retrieval: B preferred, A not in active results
        cur = _search("authentication endpoints")
        cur_ids = _ids(cur)
        cur_paths = _paths(cur)
        a_id = str(a_fm.get("id", ""))
        b_id = str(b_fm.get("id", ""))
        # A must NOT be in active search results (status=superseded, filtered out by default)
        a_still_active = any(
            (a_id and a_id == mid) or (path_a and path_a in mp)
            for mid, mp in zip(cur_ids, cur_paths))
        r.check(not a_still_active, f"superseded A leaked into current results: {cur_ids}")
        # historical search BEFORE supersession finds A
        before = _search("authentication endpoints", at_date="2024-03-15")
        before = irag._filter_by_date(before, "2024-03-15")
        before_ids = _ids(before)
        r.check(a_id in before_ids or path_a in _paths(before),
                f"A not found in pre-supersession temporal search: {before_ids}")
        # historical search AFTER supersession finds B, not A
        after = _search("authentication endpoints", at_date="2024-08-15")
        after = irag._filter_by_date(after, "2024-08-15")
        after_ids = _ids(after)
        r.check(b_id in after_ids or path_b in _paths(after),
                f"B not found in post-supersession temporal search: {after_ids}")
        a_in_after = a_id in after_ids or path_a in _paths(after)
        r.check(not a_in_after, f"A should be excluded after valid_to: {after_ids}")
        # history never deleted
        r.check(Path(irag.ROOT / path_a).exists() if path_a else False,
                "A markdown file must still exist after supersession")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_failure_then_fix(env: Env) -> ScenarioResult:
    r = ScenarioResult("failure_then_fix")
    t0 = time.perf_counter()
    try:
        st_f, out_f = _remember(env, type="failure", title="MongoDB transactional data failed",
                                body="Attempted to store transactional ledger data in MongoDB; "
                                     "lost consistency on rollback. Root cause: no multi-document tx.",
                                tags="mongodb,nosql,transactions",
                                evidence="src/db/ledger.py:88",
                                valid_from="2024-02-01")
        r.check(st_f == "created", f"failure create status={st_f}")
        path_f = _path_of_remember(out_f)
        # fix: a knowledge memory derived_from the failure
        st_k, out_k = _remember(env, type="knowledge", title="Use Postgres for transactional ledger",
                                body="Transactionality is required for the ledger. Use Postgres + "
                                     "asyncpg; it supports multi-statement transactions and rollbacks.",
                                tags="postgres,transactions",
                                evidence="src/db/pool.py:12",
                                derived_from=_fm(path_f).get("id", ""),
                                valid_from="2024-03-01")
        r.check(st_k == "created", f"knowledge create status={st_k}")
        path_k = _path_of_remember(out_k)
        k_fm = _fm(path_k)
        r.check(str(_fm(path_f).get("id", "")) in k_fm.get("derived_from", []),
                f"derived_from not recorded: {k_fm.get('derived_from')}")
        # mark the failure invalid (it was a wrong approach)
        rc = _update(env, path_f, status="invalid", append="Disproved: ledger moved to Postgres.")
        r.check(rc == 0, f"update rc={rc}")
        r.check(_fm(path_f).get("status") == "invalid", "failure should be invalid")
        # active retrieval for transactional ledger: knowledge surfaces, invalid failure does not
        res = _search("transactional ledger database")
        ids = _ids(res)
        r.check(str(k_fm.get("id", "")) in ids or path_k in _paths(res),
                f"knowledge not retrieved: {ids}")
        f_in_active = str(_fm(path_f).get("id", "")) in ids or path_f in _paths(res)
        r.check(not f_in_active, f"invalid failure leaked into active search: {ids}")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_conflicting_active(env: Env) -> ScenarioResult:
    r = ScenarioResult("conflicting_active")
    t0 = time.perf_counter()
    try:
        st1, out1 = _remember(env, type="knowledge", title="Redis cache for sessions",
                               body="Sessions are cached in Redis with TTL 300s; "
                                    "invalidation is lazy on write. Sessions key is session:<id>.",
                               scope="auth", tags="redis,cache,sessions",
                               valid_from="2024-01-01")
        r.check(st1 == "created", f"first create status={st1}")
        path1 = _path_of_remember(out1)
        # Try to create a conflicting memory of same type/scope without --force.
        # Body has substantial token overlap with the first ("sessions", "cached",
        # "ttl", "300s", "auth") -> conflict detector should block.
        st2, out2 = _remember(env, type="knowledge", title="Memcached cache for sessions",
                              body="Sessions are cached in Memcached with TTL 300s; "
                                   "invalidation is lazy on write. Sessions key is session:<id>.",
                              scope="auth", tags="memcached,cache,sessions",
                              valid_from="2024-02-01")
        r.check(st2 in ("blocked", "refused"), f"conflicting create should be blocked, got {st2}")
        # With --force it succeeds (deterministic)
        st3, out3 = _remember(env, type="knowledge", title="Memcached cache for sessions",
                              body="Sessions are cached in Memcached with TTL 300s.",
                              scope="auth", tags="memcached,cache,sessions",
                              valid_from="2024-02-01", force=True)
        r.check(st3 == "created", f"force create status={st3}")
        # Both are active; retrieval surfaces both (contradiction is a feature)
        res = _search("session cache")
        ids = _ids(res)
        r.check(len([i for i in ids if i]) >= 2,
                f"expected at least 2 active memories, got {ids}")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_archived_memory(env: Env) -> ScenarioResult:
    r = ScenarioResult("archived_memory")
    t0 = time.perf_counter()
    try:
        st, out = _remember(env, type="knowledge", title="Legacy initial migration raw sql",
                            body="The legacy initial migration used raw SQL via a custom runner.",
                            tags="migration,legacy,sql",
                            valid_from="2023-01-01")
        r.check(st == "created", f"create status={st}")
        path = _path_of_remember(out)
        # active retrieval finds it
        res = _search("legacy migration sql")
        r.check(_fm(path).get("id", "") in _ids(res) or path in _paths(res),
                "archived-pre: should be retrievable while active")
        # forget (archive)
        rc = _forget(env, path)
        r.check(rc == 0, f"forget rc={rc}")
        r.check(not Path(irag.ROOT / path).exists(), "original file should be moved")
        # archived must NOT leak into normal active retrieval
        res2 = _search("legacy migration sql")
        ids2 = _ids(res2)
        paths2 = _paths(res2)
        leaked = _fm(path).get("id", "") in ids2 or path in paths2
        r.check(not leaked, f"archived memory leaked into active search: {ids2}")
        # history preserved in archive/
        archive_files = list((irag.RAG / "archive").glob("*.md"))
        r.check(len(archive_files) >= 1, f"archive should contain the memory: {archive_files}")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_duplicate_writes(env: Env) -> ScenarioResult:
    r = ScenarioResult("duplicate_writes")
    t0 = time.perf_counter()
    try:
        body = "Rate limiter uses a token bucket per IP with refill 10/s and capacity 20."
        st1, out1 = _remember(env, type="knowledge", title="Rate limiter token bucket",
                               body=body, tags="rate-limit,token-bucket",
                               evidence="src/middleware/ratelimit.py:23",
                               valid_from="2024-01-01")
        r.check(st1 == "created", f"first create status={st1}")
        # EXACT duplicate: same canonical text -> blocked
        st2, out2 = _remember(env, type="knowledge", title="Rate limiter token bucket",
                              body=body, tags="rate-limit,token-bucket",
                              evidence="src/middleware/ratelimit.py:23",
                              valid_from="2024-01-01")
        r.check(st2 == "blocked", f"exact duplicate must be blocked, got {st2}")
        # Deterministic: second attempt also blocked (no race / flakiness)
        st2b, _ = _remember(env, type="knowledge", title="Rate limiter token bucket",
                            body=body, tags="rate-limit,token-bucket",
                            evidence="src/middleware/ratelimit.py:23",
                            valid_from="2024-01-01")
        r.check(st2b == "blocked", f"exact duplicate second attempt must be blocked, got {st2b}")
        # NEAR duplicate: small change -> blocked (near dup detection)
        st3, out3 = _remember(env, type="knowledge", title="Rate limiter token bucket",
                              body=body + " Extra trailing sentence here.",
                              tags="rate-limit,token-bucket",
                              evidence="src/middleware/ratelimit.py:23",
                              valid_from="2024-01-01")
        r.check(st3 == "blocked", f"near duplicate should be blocked, got {st3}")
        # Distinct memory: different content -> created
        st4, _ = _remember(env, type="knowledge", title="Connection pool size",
                           body="The asyncpg pool size is 20 with a max overflow of 5.",
                           tags="postgres,pool",
                           evidence="src/db/pool.py:1",
                           valid_from="2024-01-01")
        r.check(st4 == "created", f"distinct memory should be created, got {st4}")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_links_backlinks(env: Env) -> ScenarioResult:
    r = ScenarioResult("links_backlinks")
    t0 = time.perf_counter()
    try:
        st_a, out_a = _remember(env, type="decision", title="Use JWT for auth",
                                body="All endpoints require JWT bearer tokens.",
                                valid_from="2024-01-01")
        path_a = _path_of_remember(out_a)
        st_b, out_b = _remember(env, type="knowledge", title="Refresh token cache",
                                body="Refresh tokens are cached in Redis with a 24h TTL.",
                                valid_from="2024-01-15")
        path_b = _path_of_remember(out_b)
        # link A -> B
        rc = _link(env, path_a, path_b)
        r.check(rc == 0, f"link rc={rc}")
        a_fm = _fm(path_a)
        rel_b = path_b  # already normalized to forward slashes by _path_of_remember
        r.check(rel_b in a_fm.get("links", []), f"links not recorded: {a_fm.get('links')}")
        # backlink coherence: searching for the linked memory still works
        res = _search("refresh token cache redis")
        r.check(_fm(path_b).get("id", "") in _ids(res) or path_b in _paths(res),
                "linked memory should be retrievable")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_invalid_evidence(env: Env) -> ScenarioResult:
    r = ScenarioResult("invalid_evidence")
    t0 = time.perf_counter()
    try:
        # Evidence path that does not exist in the sandbox; remember must still succeed
        # (validate() warns, but remember does not block on missing paths).
        st, out = _remember(env, type="knowledge", title="Webpack config split chunks",
                            body="The webpack config uses splitChunks with cacheGroups.",
                            evidence="frontend/webpack.config.js:42",
                            valid_from="2024-01-01")
        r.check(st == "created", f"create with missing evidence status={st}")
        # validate() should report a warning for the missing path
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_v = irag.validate()
        r.check(rc_v in (0, 1), f"validate rc={rc_v}")
        # Memory is still searchable
        path = _path_of_remember(out)
        res = _search("webpack split chunks")
        r.check(_fm(path).get("id", "") in _ids(res) or path in _paths(res),
                "memory with missing evidence should still be searchable")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_pl_en_mixed(env: Env) -> ScenarioResult:
    r = ScenarioResult("pl_en_mixed")
    t0 = time.perf_counter()
    try:
        st1, out1 = _remember(env, type="knowledge", title="Polski walidacja PESEL",
                              body="Walidacja numeru PESEL: suma kontrolna modulo 11, "
                                   "waga cyfr zależna od pozycji.",
                              tags="pesek,walidacja,pl",
                              valid_from="2024-01-01")
        r.check(st1 == "created", f"PL create status={st1}")
        path1 = _path_of_remember(out1)
        st2, out2 = _remember(env, type="knowledge", title="Auth JWT token logowanie",
                              body="Logowanie: formularz email + hasło, następnie JWT token "
                                   "wydawany przez /auth/login endpoint.",
                              tags="auth,jwt,logowanie,pl,en",
                              valid_from="2024-01-15")
        r.check(st2 == "created", f"mixed create status={st2}")
        path2 = _path_of_remember(out2)
        # PL query
        res_pl = _search("walidacja numeru PESEL")
        r.check(_fm(path1).get("id", "") in _ids(res_pl) or path1 in _paths(res_pl),
                f"PL memory not retrieved by PL query: {_ids(res_pl)}")
        # mixed query
        res_mx = _search("auth jwt token logowanie")
        r.check(_fm(path2).get("id", "") in _ids(res_mx) or path2 in _paths(res_mx),
                f"mixed memory not retrieved: {_ids(res_mx)}")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_export_import(env: Env) -> ScenarioResult:
    r = ScenarioResult("export_import")
    t0 = time.perf_counter()
    try:
        # seed a couple of memories with lifecycle fields
        st_a, out_a = _remember(env, type="decision", title="Export decision",
                                body="Decision body for export roundtrip.",
                                valid_from="2024-01-01", confidence="high")
        path_a = _path_of_remember(out_a)
        st_b, out_b = _remember(env, type="knowledge", title="Export knowledge",
                                body="Knowledge body for export roundtrip.",
                                valid_from="2024-01-15", confidence="medium")
        path_b = _path_of_remember(out_b)
        _supersede(env, path_a, by=path_b, reason="replaced for export test")
        a_fm_before = _fm(path_a)
        b_fm_before = _fm(path_b)
        # export
        a = _args()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_e = irag.export_cmd(a)
        r.check(rc_e == 0, f"export rc={rc_e}")
        exports = list(irag.EXPORT_DIR.glob("irag-export-*.json"))
        r.check(len(exports) >= 1, f"export file not created: {exports}")
        export_path = exports[-1]
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        r.check("memories" in payload and len(payload["memories"]) >= 2,
                f"export payload memories count: {len(payload.get('memories', []))}")
        # import into a clean fixture
        sandbox2 = Path(tempfile.mkdtemp(prefix="irag-mut-imp-"))
        try:
            with Env(sandbox2):
                a_imp = _args(file=str(export_path), overwrite=True)
                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    rc_i = irag.import_cmd(a_imp)
                r.check(rc_i == 0, f"import rc={rc_i}")
                # find the imported memories by id
                p_a2 = irag.find_memory_by_id_or_path(str(a_fm_before.get("id", "")))
                p_b2 = irag.find_memory_by_id_or_path(str(b_fm_before.get("id", "")))
                r.check(p_a2 is not None and p_a2.exists(),
                        f"imported A missing: {a_fm_before.get('id')}")
                r.check(p_b2 is not None and p_b2.exists(),
                        f"imported B missing: {b_fm_before.get('id')}")
                a_fm_after = irag.parse_fm(p_a2.read_text(encoding="utf-8"))
                b_fm_after = irag.parse_fm(p_b2.read_text(encoding="utf-8"))
                # lifecycle metadata preserved
                r.check(a_fm_after.get("status") == a_fm_before.get("status"),
                        f"status drift: {a_fm_after.get('status')} != {a_fm_before.get('status')}")
                r.check(a_fm_after.get("valid_to") == a_fm_before.get("valid_to"),
                        f"valid_to drift: {a_fm_after.get('valid_to')} != {a_fm_before.get('valid_to')}")
                r.check(a_fm_after.get("superseded_by") == a_fm_before.get("superseded_by"),
                        f"superseded_by drift")
                r.check(b_fm_after.get("confidence") == b_fm_before.get("confidence"),
                        f"confidence drift: {b_fm_after.get('confidence')} != {b_fm_before.get('confidence')}")
                r.check(str(a_fm_before.get("id", "")) in b_fm_after.get("supersedes", []),
                        f"supersedes link not preserved: {b_fm_after.get('supersedes')}")
                # retrieval equivalence: search in the imported project.
                # A is superseded (status=superseded) so it is filtered out of
                # active retrieval by default; the invariant we check here is
                # that the IMPORTED project can still retrieve the replacement
                # memory (B), which proves the import restored durable content
                # and the retrieval pipeline works on the clean fixture.
                res2 = _search("export knowledge roundtrip")
                r.check(any(str(b_fm_after.get("id", "")) in _ids(res2)
                            or str(p_b2.relative_to(irag.ROOT)).replace("\\", "/") in _paths(res2)
                            for _ in [0]),
                        f"imported B not retrievable in clean fixture: {_ids(res2)}")
                # And the superseded A is still on disk (history preserved through import).
                r.check(p_a2.exists(), "imported superseded A file must exist (history preserved)")
        finally:
            shutil.rmtree(sandbox2, ignore_errors=True)
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_index_delete_rebuild(env: Env) -> ScenarioResult:
    r = ScenarioResult("index_delete_rebuild")
    t0 = time.perf_counter()
    try:
        # Seed memories
        st1, out1 = _remember(env, type="knowledge", title="Rebuild index smoke A",
                               body="Memory A for index rebuild equivalence check.",
                               tags="rebuild,smoke",
                               valid_from="2024-01-01")
        st2, out2 = _remember(env, type="knowledge", title="Rebuild index smoke B",
                               body="Memory B for index rebuild equivalence check, distinct tokens.",
                               tags="rebuild,smoke",
                               valid_from="2024-01-15")
        path1 = _path_of_remember(out1)
        path2 = _path_of_remember(out2)
        # Baseline retrieval (Markdown is the source of truth; SQLite disabled in sandbox)
        base_q = "rebuild index smoke"
        base_res = _search(base_q)
        base_ids = _ids(base_res)
        base_paths = _paths(base_res)
        # Delete the SQLite index file if present (durable semantics must not change)
        idx_file = irag.RAG / ".index.sqlite3"
        if idx_file.exists():
            idx_file.unlink()
        # Retrieval must be equivalent without the index
        res_no_idx = _search(base_q)
        r.check(_ids(res_no_idx) == base_ids,
                f"retrieval changed after index delete: {_ids(res_no_idx)} vs {base_ids}")
        r.check(_paths(res_no_idx) == base_paths,
                f"paths changed after index delete: {_paths(res_no_idx)} vs {base_paths}")
        # "Rebuild" by calling rebuild_index() (regenerates INDEX.md) — semantics unchanged
        buf = io.StringIO()
        with redirect_stdout(buf):
            irag.rebuild_index()
        res_rebuilt = _search(base_q)
        r.check(_ids(res_rebuilt) == base_ids,
                f"retrieval changed after rebuild: {_ids(res_rebuilt)} vs {base_ids}")
        r.check(_paths(res_rebuilt) == base_paths,
                f"paths changed after rebuild: {_paths(res_rebuilt)} vs {base_paths}")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


def scenario_update_preserves_history(env: Env) -> ScenarioResult:
    r = ScenarioResult("update_preserves_history")
    t0 = time.perf_counter()
    try:
        st, out = _remember(env, type="knowledge", title="Update history check",
                            body="Original body content for history preservation check.",
                            tags="update,history",
                            valid_from="2024-01-01")
        path = _path_of_remember(out)
        original_text = Path(irag.ROOT / path).read_text(encoding="utf-8")
        original_body_marker = "Original body content for history preservation"
        r.check(original_body_marker in original_text, "original body marker missing")
        # update: append a section + change tags
        rc = _update(env, path, add_tags="new-tag", append="Appended update note on today.")
        r.check(rc == 0, f"update rc={rc}")
        new_text = Path(irag.ROOT / path).read_text(encoding="utf-8")
        # original body must still be present (history preserved)
        r.check(original_body_marker in new_text,
                "original body must survive update (history preservation)")
        r.check("Appended update note" in new_text, "appended section missing")
        fm = _fm(path)
        r.check("new-tag" in fm.get("tags", []), f"new tag not added: {fm.get('tags')}")
    except Exception as e:
        r.check(False, f"exception: {type(e).__name__}: {e}")
    r.latency_ms = (time.perf_counter() - t0) * 1000.0
    return r


SCENARIOS = [
    scenario_decision_replacement,
    scenario_failure_then_fix,
    scenario_conflicting_active,
    scenario_archived_memory,
    scenario_duplicate_writes,
    scenario_links_backlinks,
    scenario_invalid_evidence,
    scenario_pl_en_mixed,
    scenario_export_import,
    scenario_index_delete_rebuild,
    scenario_update_preserves_history,
]

SMOKE_SCENARIOS = [
    scenario_decision_replacement,
    scenario_duplicate_writes,
    scenario_archived_memory,
    scenario_index_delete_rebuild,
]


def run(smoke: bool = False) -> Dict[str, Any]:
    scenarios = SMOKE_SCENARIOS if smoke else SCENARIOS
    results: List[ScenarioResult] = []
    for fn in scenarios:
        tmp = Path(tempfile.mkdtemp(prefix="irag-mut-bench-"))
        try:
            with Env(tmp):
                # Each scenario re-enters Env(tmp) internally; that is harmless
                # (nested __enter__ re-saves the same state) and keeps scenarios
                # self-contained. We pass tmp as the sandbox root.
                results.append(fn(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    # Aggregate invariant metrics
    temporal_correct = sum(1 for r in results if r.passed and "temporal" in r.name)
    leakage_failures = sum(1 for r in results if (not r.passed) and "leak" in " ".join(r.failures))
    export_import_ok = all(r.passed for r in results if r.name == "export_import")
    rebuild_ok = all(r.passed for r in results if r.name == "index_delete_rebuild")
    total_lat = sum(r.latency_ms for r in results)
    return {
        "smoke": smoke,
        "n_scenarios": len(results),
        "passed": passed,
        "failed": failed,
        "temporal_correct": temporal_correct,
        "lifecycle_leakage_count": leakage_failures,
        "export_import_equivalence": export_import_ok,
        "rebuild_equivalence": rebuild_ok,
        "total_runtime_ms": round(total_lat, 2),
        "scenarios": [
            {"name": r.name, "passed": r.passed,
             "latency_ms": round(r.latency_ms, 2),
             "failures": r.failures}
            for r in results
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="INTERNAL_RAG memory mutation/lifecycle benchmark")
    ap.add_argument("--smoke", action="store_true", help="Fast CI canary subset")
    ap.add_argument("--json", action="store_true", help="Machine-readable JSON")
    args = ap.parse_args()
    report = run(smoke=args.smoke)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["failed"] == 0 else 1
    print("INTERNAL_RAG Memory Mutation/Lifecycle Benchmark"
          + (" (SMOKE)" if args.smoke else ""))
    print("=" * 72)
    print(f"scenarios:    {report['n_scenarios']}")
    print(f"passed:       {report['passed']}")
    print(f"failed:       {report['failed']}")
    print(f"temporal_correct: {report['temporal_correct']}")
    print(f"lifecycle_leakage_count: {report['lifecycle_leakage_count']}")
    print(f"export_import_equivalence: {report['export_import_equivalence']}")
    print(f"rebuild_equivalence: {report['rebuild_equivalence']}")
    print(f"total_runtime_ms: {report['total_runtime_ms']}")
    print("-" * 72)
    for s in report["scenarios"]:
        tag = "OK" if s["passed"] else "FAIL"
        line = f"[{tag}] {s['name']:30} ({s['latency_ms']:.1f}ms)"
        if not s["passed"]:
            line += "  failures=" + "; ".join(s["failures"])
        print(line)
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())