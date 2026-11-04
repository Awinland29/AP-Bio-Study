#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python start.py
elif command -v python3 >/dev/null 2>&1; then
  exec python3 start.py
else
  echo "Python 3 is required. Install Python from https://www.python.org/downloads/"
  exit 1
fi
