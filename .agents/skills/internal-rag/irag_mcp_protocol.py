#!/usr/bin/env python3
"""irag_mcp_protocol.py — shared MCP protocol helpers (v1.6.0).

Stdlib-only (Python 3.8+). No `mcp` SDK required at runtime. Used by both
`irag.py mcp` and `irag_mcp_router.py` to avoid logic duplication for the
dual-era protocol support (CEL B/C).

Eras:
  - Legacy (2024-11-05 … 2025-11-25): initialize / notifications/initialized /
    tools/list / tools/call / ping / shutdown. Backward compatible.
  - Modern (2026-07-28): server/discover (no initialize required), per-request
    `_meta`, resultType envelopes, structuredContent, ttlMs/cacheScope.
"""
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Tuple

# Supported protocol versions, newest first.
SUPPORTED_VERSIONS: List[str] = [
    "2026-07-28",      # modern: discover, no-init, _meta, resultType
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",      # legacy baseline
]
MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = SUPPORTED_VERSIONS[1:]  # everything except the modern one
DEFAULT_NEGOTIATED = "2025-11-25"  # safe default for legacy clients


def is_modern(version: str) -> bool:
    return version == MODERN_VERSION


def negotiate_version(client_version: str) -> str:
    """Return the client's version if supported, else the latest legacy
    version (NOT the modern one — legacy clients must not be force-upgraded)."""
    if client_version in SUPPORTED_VERSIONS:
        return client_version
    return DEFAULT_NEGOTIATED


def server_info(name: str, version: str) -> Dict[str, Any]:
    return {"name": name, "version": version}


def discover_result(server_name: str, server_version: str,
                    instructions: str,
                    capabilities: Optional[Dict[str, Any]] = None
                    ) -> Dict[str, Any]:
    """Build a `server/discover` result for MCP 2026-07-28.

    Includes supportedVersions, capabilities, instructions, server info,
    and ttlMs/cacheScope metadata in `_meta` per the modern spec.
    """
    return {
        "supportedVersions": SUPPORTED_VERSIONS,
        "capabilities": capabilities or {"tools": {}},
        "instructions": instructions,
        "serverInfo": server_info(server_name, server_version),
        "_meta": {
            "ttlMs": 300000,          # 5 min cache window for discover
            "cacheScope": "connection",
        },
    }


def tools_list_result(tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Modern tools/list result with resultType and cache metadata."""
    # Deterministic order: sort by name (tools/list must be deterministic).
    ordered = sorted(tools, key=lambda t: t.get("name", ""))
    return {
        "tools": ordered,
        "resultType": "complete",
        "_meta": {"ttlMs": 60000, "cacheScope": "connection"},
    }


def tool_call_result(content_text: str, is_error: bool,
                     structured: Optional[Dict[str, Any]] = None,
                     output_schema: Optional[Dict[str, Any]] = None
                     ) -> Dict[str, Any]:
    """Build a tools/call result envelope.

    - Legacy clients read `content` (TextContent) and `isError`.
    - Modern clients additionally read `structuredContent`, `outputSchema`,
      `resultType`, and `_meta`.
    """
    res: Dict[str, Any] = {
        "content": [{"type": "text", "text": content_text}],
        "isError": bool(is_error),
        "resultType": "complete",
    }
    if structured is not None:
        res["structuredContent"] = structured
    if output_schema is not None:
        res["outputSchema"] = output_schema
    res["_meta"] = {"ttlMs": 0, "cacheScope": "request"}
    return res


def parse_meta(params: Dict[str, Any]) -> Dict[str, Any]:
    """Extract per-request `_meta` from modern request params."""
    meta = params.get("_meta")
    return meta if isinstance(meta, dict) else {}


def error_envelope(code: int, message: str) -> Dict[str, Any]:
    return {"code": code, "message": message}


# Tool annotations (CEL C). These describe behavioral hints to clients.
# openWorldHint: false = this tool operates on a closed/local world (local memory),
# not the open internet.
ANNOTATIONS_READ_ONLY = {
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": False,   # search/context update usage metadata -> NOT idempotent
    "openWorldHint": False,
}
ANNOTATIONS_MUTATING = {
    "readOnlyHint": False, "destructiveHint": False,
    "idempotentHint": False, "openWorldHint": False,
}
ANNOTATIONS_PURE_READ = {
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": True, "openWorldHint": False,
}


# Output schemas (CEL C) for tools that return structured content.
OUTPUT_SCHEMA_SEARCH = {
    "type": "object",
    "properties": {
        "abstained": {"type": "boolean"},
        "retrieval_confidence": {"type": "number"},
        "confidence_kind": {"type": "string", "enum": ["heuristic", "calibrated"]},
        "reason": {"type": "string"},
        "admitted": {"type": "integer"},
        "rejected": {"type": "integer"},
        "results": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["abstained", "results"],
}

OUTPUT_SCHEMA_STATUS = {
    "type": "object",
    "properties": {
        "memories": {"type": "integer"},
        "checkpoints": {"type": "integer"},
        "last_checkpoint": {"type": "string"},
        "index_status": {"type": "string"},
    },
}

OUTPUT_SCHEMA_TASKS = {
    "type": "object",
    "properties": {
        "tasks": {"type": "array", "items": {"type": "object"}},
    },
}

OUTPUT_SCHEMA_PROJECTS = {
    "type": "object",
    "properties": {
        "projects": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "root": {"type": "string"},
                "write": {"type": "boolean"},
                "available": {"type": "boolean"},
                "reason": {"type": "string"},
            },
        }},
    },
    "required": ["projects"],
}

OUTPUT_SCHEMA_GUARD = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "fingerprint": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ok"],
}


def modern_response(rid: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a result into a JSON-RPC 2.0 response (modern envelope)."""
    return {"jsonrpc": "2.0", "id": rid, "result": result}