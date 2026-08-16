#!/usr/bin/env bash
# Launch Foltree. Creates the virtualenv and installs dependencies the first
# time, then goes straight to the app on every later run.
#
#   ./run.sh              -> opens the app
#   ./run.sh scan . -f md -> passes arguments through to the CLI
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV=".venv"
STAMP="$VENV/.requirements-stamp"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python 3 not found. Install it, or set PYTHON=/path/to/python3" >&2
    exit 1
fi

if [ ! -d "$VENV" ]; then
    echo "First run: creating virtual environment in $VENV ..."
    "$PYTHON" -m venv "$VENV"
fi

# Only reinstall when requirements.txt actually changed, so start-up stays fast.
CURRENT="$(cksum requirements.txt | awk '{print $1, $2}')"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$CURRENT" ]; then
    echo "Installing dependencies ..."
    "$VENV/bin/python" -m pip install --upgrade pip --quiet
    "$VENV/bin/python" -m pip install --quiet -r requirements.txt
    echo "$CURRENT" > "$STAMP"
fi

exec "$VENV/bin/python" -m foltree "$@"
