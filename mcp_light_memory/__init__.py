"""PyPI package wrapper for MCP Light Memory."""

from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    """Return the installed package root containing installer assets."""
    return Path(__file__).resolve().parent
