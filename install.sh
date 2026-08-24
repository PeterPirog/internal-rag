#!/usr/bin/env bash
set -euo pipefail
D="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required."; exit 1; }
python3 "$D/install.py" "${1:-$PWD}" "${@:2}"
