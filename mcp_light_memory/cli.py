"""Console entry point for the packaged MCP Light Memory installer."""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    """Run the packaged copy of the canonical install.py script."""
    installer = Path(__file__).resolve().parent / "install.py"
    runpy.run_path(str(installer), run_name="__main__")


if __name__ == "__main__":
    main()
