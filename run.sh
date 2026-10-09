#!/usr/bin/env bash
# Launch Foltree. Creates the virtualenv and installs dependencies the first
# time, then goes straight to the app on every later run.
#
#   ./run.sh              -> opens the app
#   ./run.sh scan . -f md -> passes arguments through to the CLI
set -euo pipefail

cd "$(dirname "$0")"

VENV=".venv"
STAMP="$VENV/.requirements-stamp"

# Tk older than 8.6 (Apple's bundled Python) opens the window as solid black,
# so skip any interpreter that has it and look for one that does not.
has_modern_tk() {
    "$1" -c 'import sys, tkinter; sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)' >/dev/null 2>&1
}

if [ -z "${PYTHON:-}" ]; then
    for candidate in python3 python3.13 python3.12 python3.11 python3.10 \
        /opt/homebrew/bin/python3 /usr/local/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
        if command -v "$candidate" >/dev/null 2>&1 && has_modern_tk "$candidate"; then
            PYTHON="$candidate"
            break
        fi
    done
fi

if [ -z "${PYTHON:-}" ] || ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "No Python 3 with Tk 8.6+ found (the default macOS Python has Tk 8.5, which shows a black window)." >&2
    echo "Install one from python.org or 'brew install python-tk', or set PYTHON=/path/to/python3" >&2
    exit 1
fi

# A venv built from an old-Tk interpreter keeps that Tk; rebuild it.
if [ -d "$VENV" ] && ! has_modern_tk "$VENV/bin/python"; then
    echo "Recreating virtual environment with $PYTHON (old Tk in the current one) ..."
    rm -rf "$VENV"
fi

if [ ! -d "$VENV" ]; then
    echo "First run: creating virtual environment in $VENV using $PYTHON ..."
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
