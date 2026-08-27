#!/usr/bin/env python3
"""irag_mcp_protocol.py — shared MCP protocol helpers (MCP Light Memory).

Stdlib-only (Python 3.8+). No `mcp` SDK required at runtime. Used by both
`irag.py mcp` and `irag_mcp_router.py` to avoid logic duplication for the
dual-era protocol support.

Eras:
  - Legacy (2024-11-05 … 2025-11-25): initialize / notifications/initialized /
    tools/list / tools/call / ping / shutdown. Backward compatible.
  - Modern (2026-07-28): stateless, self-describing per-request metadata in
    `_meta["io.modelcontextprotocol/protocolVersion"]`; `server/discover`
    (no initialize required); `resultType` mandatory on every result;
    `ttlMs`/`cacheScope` as top-level result fields (cacheScope: "public"|"private");
    `structuredContent` as result data; `outputSchema` in the tool definition
    (not in tool/call results); serverInfo in `_meta["io.modelcontextprotocol/serverInfo"]`.

Key spec compliance (MCP 2026-07-28 final):
  - Per-request protocol version is read from `_meta["io.modelcontextprotocol/protocolVersion"]`.
  - No `conn_version` is needed for modern dispatch — each request is self-describing.
  - `server/discover` takes no body params beyond standard `_meta`.
  - `server/discover` response carries `serverInfo` in `_meta`, not as a top-level field.
  - `ttlMs` and `cacheScope` are top-level result fields (NOT in `_meta`).
  - `cacheScope` values: "public" or "private" (NOT "connection" or "request").
  - `resultType` is required on every result (legacy fallback: absent = "complete").
  - `outputSchema` is declared in the tool definition, not in tool/call results.
  - Legacy `initialize` still works (dual-era).
"""
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional

# Explicit era-separated protocol version lists (newest first).
# Modern era (per-request _meta protocolVersion + server/discover):
SUPPORTED_MODERN_VERSIONS: List[str] = [
    "2026-07-28",      # modern: discover, no-init, per-request _meta, resultType
]
# Legacy era (initialize handshake):
SUPPORTED_LEGACY_VERSIONS: List[str] = [
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",      # legacy baseline
]
# Combined list — informational only (aggregate "supported by this server").
# Era-specific checks MUST use the era-specific subsets above.
SUPPORTED_VERSIONS: List[str] = SUPPORTED_MODERN_VERSIONS + SUPPORTED_LEGACY_VERSIONS

MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = list(SUPPORTED_LEGACY_VERSIONS)  # back-compat alias
DEFAULT_LEGACY = "2025-11-25"  # safe counter-offer for legacy clients

# Namespace keys for _meta (MCP 2026-07-28)
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
META_LOG_LEVEL = "io.modelcontextprotocol/logLevel"

# Error codes (MCP 2026-07-28)
ERR_UNSUPPORTED_PROTOCOL_VERSION = -32022
ERR_MISSING_REQUIRED_CLIENT_CAPABILITY = -32021
# JSON-RPC 2.0 standard: invalid params (malformed/missing required _meta field)
ERR_INVALID_PARAMS = -32602

# Cache scope values (MCP 2026-07-28)
CACHE_PUBLIC = "public"
CACHE_PRIVATE = "private"

# Valid cacheScope values
VALID_CACHE_SCOPES = frozenset(["public", "private"])


def is_modern(version: str) -> bool:
    return version == MODERN_VERSION


def negotiate_version(client_version: str) -> str:
    """Negotiate a LEGACY initialize handshake version.

    Only SUPPORTED_LEGACY_VERSIONS are negotiable. The modern era
    (2026-07-28) is NOT negotiable via initialize — a modern revision is
    never advertised as the legacy handshake version. Unsupported or modern
    revisions fall back to the latest supported legacy version (counter-offer).
    """
    if client_version in SUPPORTED_LEGACY_VERSIONS:
        return client_version
    return DEFAULT_LEGACY


def server_info(name: str, version: str) -> Dict[str, Any]:
    return {"name": name, "version": version}


def extract_request_version(params: Dict[str, Any]) -> str:
    """Extract the per-request protocol version from modern _meta.

    Per MCP 2026-07-28, the protocol version is in
    `_meta["io.modelcontextprotocol/protocolVersion"]`.
    Returns "" if not present (legacy request).
    """
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return ""
    return str(meta.get(META_PROTOCOL_VERSION, ""))


def is_modern_request(params: Dict[str, Any]) -> bool:
    """True if the request carries modern per-request _meta with a protocol version."""
    return extract_request_version(params) == MODERN_VERSION


def validate_modern_request(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """SHARED validator for modern (2026-07-28) per-request `_meta`.

    Single source of truth for both the single-project server (irag.py)
    and the router (irag_mcp_router.py).

    Returns an error dict (code, message[, data]) if the request is
    malformed, or None if the request is valid — or if it is a legacy
    request (no modern _meta) that needs no modern validation.

    Per MCP 2026-07-28, every modern request MUST include:
      - _meta["io.modelcontextprotocol/protocolVersion"]: string
      - _meta["io.modelcontextprotocol/clientCapabilities"]: object
    `_meta["io.modelcontextprotocol/clientInfo"]` is OPTIONAL.

    Errors:
      - unsupported modern protocol version -> -32022 with
        data.supported / data.requested
      - missing or wrong-type clientCapabilities -> JSON-RPC -32602
        (invalid params; -32021 is reserved for a specific required
        capability, not for malformed required metadata)
    """
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return None  # legacy request — no modern validation needed
    pv = meta.get(META_PROTOCOL_VERSION)
    if pv is None:
        return None  # _meta without protocolVersion -> legacy dispatch
    # Unsupported modern version (legacy revisions are not modern revisions)
    if pv not in SUPPORTED_MODERN_VERSIONS:
        return {
            "code": ERR_UNSUPPORTED_PROTOCOL_VERSION,
            "message": f"Unsupported protocol version: {pv}",
            "data": {"supported": list(SUPPORTED_MODERN_VERSIONS), "requested": pv},
        }
    # Required: clientCapabilities must be an object
    cc = meta.get(META_CLIENT_CAPABILITIES)
    if cc is None:
        return {
            "code": ERR_INVALID_PARAMS,
            "message": "missing required _meta field: " + META_CLIENT_CAPABILITIES,
        }
    if not isinstance(cc, dict):
        return {
            "code": ERR_INVALID_PARAMS,
            "message": f"_meta field {META_CLIENT_CAPABILITIES!r} must be an object",
        }
    return None


def discover_result(server_name: str, server_version: str,
                    instructions: str,
                    capabilities: Optional[Dict[str, Any]] = None,
                    ) -> Dict[str, Any]:
    """Build a `server/discover` result for MCP 2026-07-28.

    Per the final spec:
    - `supportedVersions`: modern revisions only (2026-07-28 era). The
      legacy era (2024-11-05 … 2025-11-25, initialize-based) is NOT
      advertised here — those versions negotiate exclusively via initialize.
    - `capabilities`: server capabilities
    - `serverInfo` goes in `_meta["io.modelcontextprotocol/serverInfo"]` (NOT top-level)
    - `ttlMs` and `cacheScope` are top-level result fields
    - `resultType` is required
    """
    return {
        "resultType": "complete",
        "supportedVersions": list(SUPPORTED_MODERN_VERSIONS),
        "capabilities": capabilities or {"tools": {}},
        "instructions": instructions,
        "_meta": {
            META_SERVER_INFO: server_info(server_name, server_version),
        },
        "ttlMs": 300000,          # 5 min cache window for discover
        "cacheScope": CACHE_PUBLIC,
    }


# Canonical user-facing tool guidance. The executable schemas remain owned by
# irag.py / irag_mcp_router.py; this layer only improves descriptions returned
# by tools/list so every client sees consistent selection and parameter hints.
TOOL_DESCRIPTIONS: Dict[str, str] = {
    "context": (
        "Start or resume a task by retrieving the most relevant durable project "
        "memories and current working state. Use before making project changes or "
        "after a context reset; use search for a focused lookup that should not "
        "establish task context."
    ),
    "search": (
        "Search durable project memories and return ranked results with confidence "
        "and abstention metadata. Use for focused fact retrieval without starting "
        "or changing task state; use context when beginning or resuming a task."
    ),
    "checkpoint": (
        "Persist the current operational task state so work can be resumed after "
        "interruption or context loss. Use at meaningful milestones and before "
        "ending a work session; use remember for durable reusable knowledge."
    ),
    "guard": (
        "Check whether project state changed since the last checkpoint. Read-only "
        "and idempotent; use before finishing a task to detect uncheckpointed work, "
        "then checkpoint if stale."
    ),
    "remember": (
        "Store durable project knowledge that should survive across sessions. Use "
        "for stable decisions, constraints, gotchas, failures, hypotheses, or "
        "reusable knowledge; use checkpoint for temporary task progress."
    ),
    "status": (
        "Return read-only memory, checkpoint, index, and recovery status for the "
        "current project. Use for diagnostics and health checks; it does not modify "
        "memory or task state."
    ),
    "tasks": (
        "List the current task stack and resumable task state. Read-only; use before "
        "resume when you need to inspect pending work without changing the stack."
    ),
    "resume": (
        "Resume and remove the top saved task from the task stack. Use after tasks "
        "shows resumable work; use tasks instead when you only need to inspect the "
        "stack."
    ),
}

TOOL_PARAMETER_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    "context": {
        "task": (
            "Short description of the task being started or resumed; used to "
            "retrieve relevant project context."
        ),
        "limit": "Maximum number of relevant memories to include in the context packet.",
    },
    "search": {
        "query": (
            "Natural-language query describing the fact, decision, constraint, or "
            "prior work to retrieve."
        ),
        "limit": "Maximum number of ranked memories to return.",
        "types": "Optional memory types to include; omit to search all supported types.",
        "statuses": "Optional memory statuses to include; omit to use the server default.",
        "at": "Optional YYYY-MM-DD date used to filter memories by temporal validity.",
        "explain": "Include per-channel retrieval scoring details for diagnostics.",
    },
    "checkpoint": {
        "reason": "Why this checkpoint is being created.",
        "phase": "Current task phase or milestone name.",
        "completed": "Work completed since the previous checkpoint.",
        "in_progress": "Work currently underway.",
        "blockers": "Known blockers or unresolved issues.",
        "next": "Recommended next action when work resumes.",
    },
    "remember": {
        "type": "Memory category describing the kind of durable knowledge being stored.",
        "title": "Short, specific title for the memory.",
        "body": (
            "Durable content to preserve: a decision, fact, constraint, gotcha, "
            "failure, hypothesis, or reusable session knowledge."
        ),
        "tags": "Optional comma-separated tags used to organize or retrieve the memory.",
        "evidence": "Optional source or project-relative evidence reference supporting the memory.",
        "scope": "Optional scope describing where this memory applies.",
        "consequence": "Optional impact or consequence of this memory for future work.",
        "status": (
            "Memory confidence state: active for established knowledge or tentative "
            "for information that still needs confirmation."
        ),
    },
}

PROJECT_PARAMETER_DESCRIPTION = "Registered project id to route this call to."


def enhance_tool_definition(tool: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with concise selection guidance and parameter descriptions.

    This is presentation-only metadata for tools/list. It intentionally leaves
    types, enums, required fields, annotations, and output schemas unchanged.
    Router tools are detected by their `project` input and receive the same core
    guidance plus an explicit routing note.
    """
    enriched = dict(tool)
    name = str(tool.get("name", ""))

    input_schema = tool.get("inputSchema")
    has_project = False
    if isinstance(input_schema, dict):
        schema = dict(input_schema)
        properties = input_schema.get("properties")
        if isinstance(properties, dict):
            has_project = "project" in properties
            parameter_descriptions = TOOL_PARAMETER_DESCRIPTIONS.get(name, {})
            new_properties: Dict[str, Any] = {}
            for parameter_name, definition in properties.items():
                if isinstance(definition, dict):
                    parameter = dict(definition)
                    description = parameter_descriptions.get(parameter_name)
                    if parameter_name == "project":
                        description = PROJECT_PARAMETER_DESCRIPTION
                    if description:
                        parameter["description"] = description
                    new_properties[parameter_name] = parameter
                else:
                    new_properties[parameter_name] = definition
            schema["properties"] = new_properties
        enriched["inputSchema"] = schema

    description = TOOL_DESCRIPTIONS.get(name)
    if description:
        if has_project:
            description += " In router mode, pass the registered project id explicitly."
        enriched["description"] = description

    return enriched


def tools_list_result(tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Modern tools/list result with resultType and cache metadata.

    Per MCP 2026-07-28:
    - `resultType` is required
    - `ttlMs` and `cacheScope` are top-level result fields
    - `outputSchema` is part of each tool definition (not the result envelope)
    - tool descriptions are enriched without changing executable schemas
    - tools are sorted deterministically by name
    """
    enriched = [enhance_tool_definition(tool) for tool in tools]
    ordered = sorted(enriched, key=lambda t: t.get("name", ""))
    return {
        "resultType": "complete",
        "tools": ordered,
        "ttlMs": 60000,
        "cacheScope": CACHE_PUBLIC,
    }


def tool_call_result(content_text: str, is_error: bool,
                     structured: Optional[Dict[str, Any]] = None,
                     ) -> Dict[str, Any]:
    """Build a tools/call result envelope.

    Per MCP 2026-07-28:
    - `resultType` is required
    - `content` is the TextContent array (for backward compat with legacy clients)
    - `structuredContent` is the structured result data (if the tool has outputSchema)
    - `outputSchema` is NOT included in the result — it's in the tool definition
    - `ttlMs`/`cacheScope` are NOT required for tools/call (only for cacheable list/read ops)
    - `isError` marks tool execution errors (vs protocol errors)
    """
    res: Dict[str, Any] = {
        "resultType": "complete",
        "content": [{"type": "text", "text": content_text}],
        "isError": bool(is_error),
    }
    if structured is not None:
        res["structuredContent"] = structured
    return res


def legacy_initialize_result(server_name: str, server_version: str,
                             instructions: str,
                             negotiated_version: str,
                             ) -> Dict[str, Any]:
    """Build a legacy `initialize` result (2024-11-05 … 2025-11-25)."""
    return {
        "protocolVersion": negotiated_version,
        "serverInfo": server_info(server_name, server_version),
        "capabilities": {"tools": {}},
        "instructions": instructions,
    }


def error_envelope(code: int, message: str,
                   data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return err


def make_response(rid: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a result into a JSON-RPC 2.0 success response."""
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def make_error_response(rid: Any, code: int, message: str,
                        data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": error_envelope(code, message, data)}


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
# Per MCP 2026-07-28, outputSchema is declared in the tool definition,
# not in the tools/call result.
OUTPUT_SCHEMA_SEARCH = {
    "type": "object",
    "properties": {
        "trust": {"type": "string", "enum": ["untrusted"]},
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
        "irag_version": {"type": "string"},
        "total_memories": {"type": "integer"},
        "total_checkpoints": {"type": "integer"},
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
