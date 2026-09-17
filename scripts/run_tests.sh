#!/usr/bin/env bash
# Run the full test suite for the current stage.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo ".venv missing — run scripts/setup_env.sh first" >&2
  exit 1
fi
.venv/bin/python -m pytest tests -v "$@"
