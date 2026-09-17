#!/usr/bin/env bash
# Recreate the research virtualenv deterministically.
# The venv lives at .venv (git-ignored); requirements.txt pins exact versions
# used for stage-acceptance runs so results stay reproducible.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
.venv/bin/pip install --quiet -e . --no-deps
echo "OK: .venv ready ($( .venv/bin/python -c 'import numpy; print("numpy " + numpy.__version__)' ))"
