#!/usr/bin/env python3
"""irag_distill.py — diagnostic distillation for MCP Light Memory.

Stdlib-first mechanism for extracting valuable conclusions from large tool
outputs (console, terminal, builds, lints, tests). The goal is to reduce
5000-line output to a short knowledge conclusion like:

  "Test X fails because Y. Root cause in Z. Verified fix: Q."

NOT a transcript. NOT a summary of every line. Only the actionable conclusion.

No LLM dependency required. The deterministic core uses regex patterns to
extract:
  - command/tool name
  - exit code
  - ERROR / WARNING / FAILED lines
  - exception type and message
  - relevant stack frames (file:line)
  - root cause (if unambiguous)
  - remediation/fix conclusion (if verified)
  - short evidence excerpt
  - optional content hash for provenance

If the automatic conclusion is not confident enough, the observation remains
ephemeral and no durable memory is created.
"""
from __future__ import annotations
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

# Confidence thresholds
DISTILL_CONFIDENCE_HIGH = 0.8
DISTILL_CONFIDENCE_MEDIUM = 0.5
DISTILL_CONFIDENCE_LOW = 0.2

# Patterns for extracting diagnostic information
_ERROR_PATTERNS = [
    re.compile(r"^(?:ERROR|FAILED|FATAL|CRITICAL)\b[:\s]*(.+)$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Traceback \(most recent call last\):$", re.MULTILINE),
    re.compile(r"^E\s+(.+)$", re.MULTILINE),  # pytest errors
    re.compile(r"^(.+\.py):(\d+):\s+(.+Error):(.+)$", re.MULTILINE),
    re.compile(r"Error:\s+(.+)", re.IGNORECASE),
    re.compile(r"FAILED\s+(.+)", re.IGNORECASE),
]

_WARNING_PATTERNS = [
    re.compile(r"^WARNING\b[:\s]*(.+)$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^W\s+(.+)$", re.MULTILINE),  # pytest warnings
]

_EXCEPTION_PATTERN = re.compile(
    r"(\w*(?:Error|Exception|Warning|Failure))\s*:\s*(.+)"
)

_STACK_FRAME_PATTERN = re.compile(
    r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+(\w+)'
)

_PASSED_PATTERN = re.compile(r"(\d+)\s+passed", re.IGNORECASE)
_FAILED_PATTERN = re.compile(r"(\d+)\s+failed", re.IGNORECASE)
_PASSED_PATTERN_OK = re.compile(r"^OK\b", re.MULTILINE)

_FIX_PATTERNS = [
    re.compile(r"(?:fix|fixed|resolve|resolved|resolved by)\s*[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:to fix|to resolve)\s*[:\s]+(.+)", re.IGNORECASE),
]


def distill_output(source: str, content: str,
                   command: Optional[str] = None,
                   exit_code: Optional[int] = None,
                   ) -> Dict[str, Any]:
    """Extract a distilled conclusion from a tool/command output.

    Returns a dict with:
      - source: the tool/command name
      - command: the original command (if provided)
      - exit_code: the exit code (if provided)
      - errors: list of extracted error lines
      - warnings: list of extracted warning lines
      - exception_type: the exception type (if found)
      - exception_message: the exception message (if found)
      - stack_frames: list of {file, line, function} dicts
      - root_cause: the root cause line (if unambiguous)
      - remediation: the fix conclusion (if found)
      - evidence_excerpt: a short excerpt of the relevant output
      - content_hash: SHA-256 hash of the full content (first 16 chars)
      - confidence: 0.0-1.0 confidence that this distillation is actionable
      - conclusion: the one-line conclusion string (if confidence >= LOW)
      - should_promote: True if confidence >= MEDIUM (worth promoting to durable)
    """
    result: Dict[str, Any] = {
        "source": source,
        "command": command,
        "exit_code": exit_code,
        "errors": [],
        "warnings": [],
        "exception_type": None,
        "exception_message": None,
        "stack_frames": [],
        "root_cause": None,
        "remediation": None,
        "evidence_excerpt": "",
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
        "confidence": 0.0,
        "conclusion": "",
        "should_promote": False,
    }

    # Extract errors
    for pat in _ERROR_PATTERNS:
        matches = pat.findall(content)
        if matches:
            result["errors"].extend(matches[:10])  # cap at 10

    # Extract warnings
    for pat in _WARNING_PATTERNS:
        matches = pat.findall(content)
        if matches:
            result["warnings"].extend(matches[:5])

    # Extract exception type and message
    exc_match = _EXCEPTION_PATTERN.search(content)
    if exc_match:
        result["exception_type"] = exc_match.group(1)
        result["exception_message"] = exc_match.group(2).strip()

    # Extract stack frames
    frames = _STACK_FRAME_PATTERN.findall(content)
    if frames:
        result["stack_frames"] = [
            {"file": f, "line": int(l), "function": fn}
            for f, l, fn in frames[-5:]  # last 5 frames (most specific)
        ]

    # Extract test results
    passed_m = _PASSED_PATTERN.search(content)
    failed_m = _FAILED_PATTERN.search(content)
    test_passed = int(passed_m.group(1)) if passed_m else None
    test_failed = int(failed_m.group(1)) if failed_m else None

    # Extract remediation
    for pat in _FIX_PATTERNS:
        m = pat.search(content)
        if m:
            result["remediation"] = m.group(1).strip()[:200]
            break

    # Determine root cause (if unambiguous)
    if result["exception_type"] and result["stack_frames"]:
        last_frame = result["stack_frames"][-1]
        result["root_cause"] = (
            f"{result['exception_type']}: {result['exception_message']} "
            f"at {last_frame['file']}:{last_frame['line']}"
        )
    elif result["errors"]:
        result["root_cause"] = result["errors"][0][:200]
    elif exit_code is not None and exit_code != 0 and result["errors"]:
        result["root_cause"] = result["errors"][0][:200]

    # Build evidence excerpt (short relevant snippet)
    excerpt_lines = []
    if result["errors"]:
        excerpt_lines.append(result["errors"][0][:120])
    if result["exception_type"]:
        excerpt_lines.append(f"{result['exception_type']}: {result['exception_message']}")
    if result["stack_frames"]:
        f = result["stack_frames"][-1]
        excerpt_lines.append(f"  at {f['file']}:{f['line']} in {f['function']}")
    result["evidence_excerpt"] = "\n".join(excerpt_lines)[:500]

    # Calculate confidence
    confidence = 0.0
    if result["errors"]:
        confidence += 0.3
    if result["exception_type"]:
        confidence += 0.3
    if result["stack_frames"]:
        confidence += 0.2
    if result["root_cause"]:
        confidence += 0.15
    if result["remediation"]:
        confidence += 0.15
    if exit_code is not None and exit_code == 0 and not result["errors"]:
        # Successful output with no errors — low value for durable memory
        confidence = max(confidence, 0.0)
    if test_failed is not None and test_failed == 0 and test_passed is not None:
        # All tests passed — low value
        confidence = max(confidence, 0.0)
    result["confidence"] = min(confidence, 1.0)

    # Build conclusion
    if result["confidence"] >= DISTILL_CONFIDENCE_LOW:
        parts = []
        if result["root_cause"]:
            parts.append(result["root_cause"])
        elif result["errors"]:
            parts.append(result["errors"][0][:120])
        if result["remediation"]:
            parts.append(f"Fix: {result['remediation']}")
        if test_failed and test_failed > 0:
            parts.append(f"{test_failed} test(s) failed.")
        if not parts and result["warnings"]:
            parts.append(f"Warning: {result['warnings'][0][:120]}")
        result["conclusion"] = ". ".join(parts)[:300]

    # Should this be promoted to durable memory?
    result["should_promote"] = (
        result["confidence"] >= DISTILL_CONFIDENCE_MEDIUM
        and bool(result["conclusion"])
        and bool(result["root_cause"] or result["errors"])
    )

    return result


def distill_to_memory_body(distilled: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Convert a distilled result into a (title, body) pair for durable memory.

    Returns None if the distillation is not confident enough to promote.
    """
    if not distilled.get("should_promote"):
        return None
    source = distilled.get("source", "unknown")
    root = distilled.get("root_cause", distilled.get("errors", [""])[0] if distilled.get("errors") else "")
    exc_type = distilled.get("exception_type", "")
    remediation = distilled.get("remediation", "")
    evidence = distilled.get("evidence_excerpt", "")

    title = f"Failure: {source}"
    if exc_type:
        title = f"Failure: {exc_type} in {source}"

    body_parts = [f"Root cause: {root}"]
    if remediation:
        body_parts.append(f"Verified fix: {remediation}")
    if evidence:
        body_parts.append(f"Evidence: {evidence}")
    body_parts.append(f"Source: {source}")
    if distilled.get("exit_code") is not None:
        body_parts.append(f"Exit code: {distilled['exit_code']}")

    body = "\n\n".join(body_parts)
    return title, body