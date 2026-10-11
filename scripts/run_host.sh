#!/usr/bin/env bash
# Run the backend directly on this Linux host - no Docker.
#
# This is the only mode that gives both fully accurate host metrics AND working
# systemctl service monitoring; Docker alone can't do both at once (see the
# README's "Docker and WSL limitations" section). Creates a virtual environment
# on first run, reuses it after that.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../backend" && pwd)"
VENV_DIR="$BACKEND_DIR/.venv"

cd "$BACKEND_DIR"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing/updating dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r requirements.txt

echo "Starting the backend on http://${MONITOR_BACKEND_HOST:-127.0.0.1}:${MONITOR_BACKEND_PORT:-8000} (Ctrl+C to stop)..."
exec "$VENV_DIR/bin/python" -m app
