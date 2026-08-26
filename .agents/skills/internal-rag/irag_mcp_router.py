#!/usr/bin/env python3
"""irag_mcp_router.py — multi-project MCP Light Memory router.

A single MCP stdio server (newline-delimited JSON-RPC 2.0) in front of many
MCP Light Memory (formerly INTERNAL_RAG) projects.

Design:
- registry: JSON file {"projects": {id: {"root": <path>, "write": bool}}}
- allowlist: ONLY registered project ids are routable; anything else is
  rejected with a structured error.
- write=false blocks mutating tools (remember, checkpoint, resume) BEFORE any
  child process is spawned.
- isolation: every tool call runs in a FRESH `irag.py mcp` subprocess with
  cwd=<project root>, so each project's ROOT/RAG/config resolution is
  independent and no state leaks between projects.
- `projects` tool: lists id, root, write and availability.

Zero required dependencies (Python 3.8+ stdlib only).
Protocol on stdout ONLY; logs to stderr.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROUTER_VERSION = "1.8.0"
ROUTER_NAME = "mcp-light-memory-router"
ROUTER_LEGACY_NAME = "internal-rag-router"  # deprecated alias
SUPPORTED_VERSIONS = ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

MUTATING_TOOLS = {"remember", "checkpoint", "resume"}
READ_TOOLS = ("context", "search", "guard", "status", "tasks")


def _log(msg: str) -> None:
    try:
        sys.stderr.write(f"[mcp-light-memory-router] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


# ----------------------------- registry -------------------------------------

class RegistryError(ValueError):
    pass


def _resolve_root(raw: str, registry_dir: Path) -> Path:
    p = Path(os.path.expandvars(os.path.expanduser(str(raw)))).resolve()
    if not Path(raw).is_absolute():
        p = (registry_dir / raw).resolve()
    return p


def load_registry(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load and strictly validate the project registry. Returns {id: {root, write}}.

    CEL E: `write` must be a real JSON boolean. "write": "false", 0, 1, or any
    non-bool type is a hard RegistryError (no truthy coercion). Default when
    the key is absent is False.
    """
    if not path.exists():
        raise RegistryError(f"registry file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RegistryError(f"registry is not valid JSON: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("projects"), dict):
        raise RegistryError('registry must be an object with a "projects" mapping')
    out: Dict[str, Dict[str, Any]] = {}
    for pid, entry in data["projects"].items():
        if not isinstance(pid, str) or not pid.strip():
            raise RegistryError("project id must be a non-empty string")
        pid = pid.strip()
        if not isinstance(entry, dict) or "root" not in entry:
            raise RegistryError(f"project {pid!r}: entry must be an object with a 'root'")
        if not isinstance(entry["root"], str) or not entry["root"].strip():
            raise RegistryError(f"project {pid!r}: 'root' must be a non-empty string")
        root = _resolve_root(entry["root"], path.parent)
        # CEL E: strict boolean validation for `write`.
        if "write" in entry:
            w = entry["write"]
            if not isinstance(w, bool):
                raise RegistryError(
                    f"project {pid!r}: 'write' must be a JSON boolean (true/false), "
                    f"got {type(w).__name__}: {w!r}")
            write = w
        else:
            write = False  # safe default
        out[pid] = {"root": str(root), "write": write, "raw": entry}
    if not out:
        raise RegistryError("registry lists no projects")
    return out


def project_available(pid: str, entry: Dict[str, Any]) -> Tuple[bool, str]:
    root = Path(entry["root"])
    if not root.is_dir():
        return False, f"root directory does not exist: {root}"
    if not (root / "INTERNAL_RAG").exists():
        return False, f"no INTERNAL_RAG/ under {root} (run `irag.py init` there)"
    return True, "ok"


# ----------------------------- child session --------------------------------

def _child_call(root: str, irag_path: str, tool: str,
                args: Dict[str, Any], timeout: float) -> Tuple[str, bool]:
    """Run one tool call in a fresh `irag.py mcp` subprocess rooted at `root`.

    Returns (text, is_error). Isolation guarantee: the child resolves ROOT
    from cwd, so it can only see this project's INTERNAL_RAG.
    """
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18",
                    "clientInfo": {"name": "irag-router", "version": ROUTER_VERSION}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": tool, "arguments": args}},
        {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
    ]
    stdin_data = "\n".join(json.dumps(r, ensure_ascii=False) for r in requests) + "\n"
    try:
        proc = subprocess.run(
            [sys.executable, irag_path, "mcp"],
            input=stdin_data,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"error: project server timed out after {timeout:.0f}s", True
    except Exception as e:
        return f"error: failed to start project server: {e}", True

    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("id") != 2:
            continue
        if "error" in obj:
            err = obj["error"] or {}
            return str(err.get("message", "error")), True
        res = obj.get("result") or {}
        content = res.get("content") or []
        text = "".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
        return (text, bool(res.get("isError")))
    tail = [l for l in (proc.stderr or "").strip().splitlines() if l.strip()][-3:]
    detail = f"; stderr: {' | '.join(tail)}" if tail else ""
    return f"error: no response from project server (exit={proc.returncode}){detail}", True


# ----------------------------- router dispatch ------------------------------

def _tool_prop(name: str, desc: str) -> Dict[str, Any]:
    return {"name": name, "description": f"[project-scoped] {desc}",
            "inputSchema": {"type": "object",
                            "properties": {"project": {"type": "string", "description": "Registered project id"}},
                            "required": ["project"]}}


def build_tools() -> List[Dict[str, Any]]:
    schemas = {
        "context": {"task": {"type": "string", "description": "Current task description"},
                    "limit": {"type": "integer"}},
        "search": {"query": {"type": "string"}, "limit": {"type": "integer"},
                   "types": {"type": "array", "items": {"type": "string"}},
                   "statuses": {"type": "array", "items": {"type": "string"}}},
        "checkpoint": {"reason": {"type": "string"}, "phase": {"type": "string"},
                       "completed": {"type": "string"}, "in_progress": {"type": "string"},
                       "blockers": {"type": "string"}, "next": {"type": "string"}},
        "guard": {},
        "remember": {"type": {"type": "string"}, "title": {"type": "string"},
                     "body": {"type": "string"}, "tags": {"type": "string"},
                     "evidence": {"type": "string"}, "scope": {"type": "string"},
                     "consequence": {"type": "string"}, "status": {"type": "string"}},
        "status": {},
        "tasks": {},
        "resume": {},
    }
    descriptions = {
        "context": "Start/resume a task with INTERNAL_RAG context packet.",
        "search": "Search durable memories. Returns structured JSON.",
        "checkpoint": "Persist current operational state (mutating).",
        "guard": "Verify no uncheckpointed changes.",
        "remember": "Store durable memory (mutating).",
        "status": "Memory and checkpoint status (JSON).",
        "tasks": "Show task stack (JSON).",
        "resume": "Pop and resume the top task (mutating).",
    }
    tools: List[Dict[str, Any]] = []
    for name in ("context", "search", "checkpoint", "guard", "remember", "status", "tasks", "resume"):
        props = {"project": {"type": "string", "description": "Registered project id"}}
        props.update(schemas[name])
        required = ["project"] + (["query"] if name == "search" else
                                  ["task"] if name == "context" else
                                  ["reason"] if name == "checkpoint" else
                                  ["type", "title", "body"] if name == "remember" else [])
        tools.append({"name": name,
                      "description": f"INTERNAL_RAG: {descriptions[name]} Requires the `project` parameter.",
                      "inputSchema": {"type": "object", "properties": props, "required": required}})
    tools.append({
        "name": "projects",
        "description": "List registered INTERNAL_RAG projects with availability and write policy.",
        "inputSchema": {"type": "object", "properties": {}},
    })
    return tools


def _dispatch(registry: Dict[str, Dict[str, Any]], irag_path: str, timeout: float,
              name: str, args: Dict[str, Any]) -> Tuple[str, bool]:
    if name == "projects":
        rows = []
        for pid, entry in registry.items():
            ok, reason = project_available(pid, entry)
            rows.append({"id": pid, "root": entry["root"], "write": entry["write"],
                         "available": ok, "reason": reason})
        return json.dumps({"projects": rows}, ensure_ascii=False, indent=2), False

    pid = str(args.get("project", "")).strip()
    if pid not in registry:
        allowed = ", ".join(sorted(registry)) or "(none)"
        return f"unknown project: {pid!r}. Registered projects: {allowed}", True
    entry = registry[pid]
    if name in MUTATING_TOOLS and not entry["write"]:
        return (f"project {pid!r} is read-only (write=false); "
                f"tool {name!r} is blocked. Enable write for this project in the registry to allow it."), True
    ok, reason = project_available(pid, entry)
    if not ok:
        return f"project {pid!r} unavailable: {reason}", True
    forwarded = {k: v for k, v in args.items() if k != "project"}
    text, is_error = _child_call(entry["root"], irag_path, name, forwarded, timeout)
    return text, is_error


# ----------------------------- stdio server ---------------------------------

def serve(registry: Dict[str, Dict[str, Any]], irag_path: str, timeout: float) -> int:
    real_stdout = sys.stdout
    sys.stdout = sys.stderr  # any leakage from imports goes to stderr

    # Load shared protocol helpers (CEL B)
    try:
        import importlib.util as _ilu
        _pp = Path(__file__).resolve().parent / "irag_mcp_protocol.py"
        _spec = _ilu.spec_from_file_location("irag_mcp_proto_r", str(_pp))
        _proto = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_proto)
    except Exception:
        _proto = None

    def _send(obj: Dict[str, Any]) -> None:
        real_stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        real_stdout.flush()

    def _err(rid, code: int, message: str) -> None:
        _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})

    conn_version = ""
    _META_PV = getattr(_proto, "META_PROTOCOL_VERSION", "io.modelcontextprotocol/protocolVersion") if _proto else "io.modelcontextprotocol/protocolVersion"
    _META_SI = getattr(_proto, "META_SERVER_INFO", "io.modelcontextprotocol/serverInfo") if _proto else "io.modelcontextprotocol/serverInfo"
    _ERR_UNSUP = getattr(_proto, "ERR_UNSUPPORTED_PROTOCOL_VERSION", -32022) if _proto else -32022

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            _err(None, -32700, "Parse error")
            continue
        method = req.get("method", "")
        rid = req.get("id")
        is_notification = "id" not in req
        params = req.get("params", {}) or {}

        if method == "server/discover":
            # Modern: read protocol version from _meta (not params.protocolVersion)
            meta = params.get("_meta", {})
            client_v = str(meta.get(_META_PV, ""))
            if client_v and client_v not in SUPPORTED_VERSIONS:
                _err(rid, _ERR_UNSUP, f"Unsupported protocol version: {client_v}",
                     {"supported": SUPPORTED_VERSIONS, "requested": client_v})
                continue
            if _proto:
                result = _proto.discover_result(
                    "mcp-light-memory-router", ROUTER_VERSION,
                    "Multi-project MCP Light Memory router. Pass the `project` parameter "
                    "(see the `projects` tool) on every project-scoped call.",
                    {"tools": {}})
            else:
                result = {
                    "resultType": "complete",
                    "supportedVersions": SUPPORTED_VERSIONS,
                    "capabilities": {"tools": {}},
                    "instructions": "Multi-project MCP Light Memory router.",
                    "_meta": {_META_SI: {"name": "mcp-light-memory-router", "version": ROUTER_VERSION}},
                    "ttlMs": 300000,
                    "cacheScope": "public",
                }
            _send({"jsonrpc": "2.0", "id": rid, "result": result})
            continue
        if method == "initialize":
            client_v = str(params.get("protocolVersion", ""))
            if _proto:
                negotiated = _proto.negotiate_version(client_v)
            else:
                negotiated = client_v if client_v in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[1]
            conn_version = negotiated
            if _proto:
                result = _proto.legacy_initialize_result(
                    "mcp-light-memory-router", ROUTER_VERSION,
                    "Multi-project MCP Light Memory router. Pass the `project` "
                    "parameter (see the `projects` tool) on every project-scoped call.",
                    negotiated)
            else:
                result = {
                    "protocolVersion": negotiated,
                    "serverInfo": {"name": "mcp-light-memory-router", "version": ROUTER_VERSION},
                    "capabilities": {"tools": {}},
                    "instructions": "Multi-project MCP Light Memory router.",
                }
            _send({"jsonrpc": "2.0", "id": rid, "result": result})
            continue
        if method == "notifications/initialized":
            continue
        if method == "ping":
            if not is_notification:
                _send({"jsonrpc": "2.0", "id": rid, "result": {}})
            continue
        if method == "tools/list":
            if _proto:
                result = _proto.tools_list_result(build_tools())
            else:
                result = {
                    "resultType": "complete",
                    "tools": sorted(build_tools(), key=lambda t: t.get("name", "")),
                    "ttlMs": 60000,
                    "cacheScope": "public",
                }
            _send({"jsonrpc": "2.0", "id": rid, "result": result})
            continue
        if method == "tools/call":
            name = str(params.get("name", ""))
            args_d = params.get("arguments", {}) or {}
            if not isinstance(args_d, dict):
                _err(rid, -32602, "invalid arguments")
                continue
            text, is_error = _dispatch(registry, irag_path, timeout, name, args_d)
            structured = None
            if name == "projects":
                try:
                    structured = json.loads(text)
                except Exception:
                    pass
            if _proto:
                result = _proto.tool_call_result(text, is_error, structured)
            else:
                result = {"content": [{"type": "text", "text": text}], "isError": bool(is_error),
                          "resultType": "complete"}
                if structured is not None:
                    result["structuredContent"] = structured
            _send({"jsonrpc": "2.0", "id": rid, "result": result})
            continue
        if method == "shutdown":
            if rid is not None:
                _send({"jsonrpc": "2.0", "id": rid, "result": {}})
            sys.stdout = real_stdout
            break
        if is_notification:
            continue
        _err(rid, -32601, "Method not found")

    sys.stdout = real_stdout
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="mlm-router",
                                 description="Multi-project MCP Light Memory router (stdio).  (formerly internal-rag-router)")
    ap.add_argument("--registry", required=True,
                    help="Path to the registry JSON (see examples/projects.example.json).")
    ap.add_argument("--irag", default=None,
                    help="Path to irag.py (default: the irag.py next to this file).")
    ap.add_argument("--timeout", type=float, default=60.0,
                    help="Per-call child timeout in seconds (default 60).")
    a = ap.parse_args()

    registry_path = Path(a.registry).resolve()
    try:
        registry = load_registry(registry_path)
    except RegistryError as e:
        _log(f"registry error: {e}")
        return 2

    irag_path = a.irag or str(Path(__file__).resolve().parent / "irag.py")
    if not Path(irag_path).exists():
        _log(f"irag.py not found at {irag_path}")
        return 2

    _log(f"router ready: {len(registry)} project(s) "
         f"({', '.join(pid for pid, e in registry.items() if e['write']) or 'no write access'})")
    return serve(registry, irag_path, a.timeout)


if __name__ == "__main__":
    sys.exit(main())
