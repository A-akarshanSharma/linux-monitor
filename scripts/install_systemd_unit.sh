#!/usr/bin/env bash
# Install the backend as a systemd service, so it starts on boot and restarts on
# failure instead of needing a terminal left open. Requires scripts/run_host.sh to
# have been run at least once already (to create the virtual environment) and
# requires sudo to write into /etc/systemd/system.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../backend" && pwd)"
VENV_DIR="$BACKEND_DIR/.venv"
UNIT_NAME="linux-monitor-backend.service"
UNIT_DEST="/etc/systemd/system/$UNIT_NAME"

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "No virtual environment found at $VENV_DIR." >&2
    echo "Run scripts/run_host.sh once first (it creates the venv), then re-run this script." >&2
    exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl not found - this host doesn't appear to use systemd." >&2
    exit 1
fi

echo "Installing $UNIT_NAME (you'll be asked for sudo)..."
sed -e "s|__BACKEND_DIR__|$BACKEND_DIR|g" -e "s|__VENV_DIR__|$VENV_DIR|g" \
    "$SCRIPT_DIR/linux-monitor-backend.service.template" | sudo tee "$UNIT_DEST" > /dev/null

sudo systemctl daemon-reload

echo
echo "Installed. Start it now and enable it on boot with:"
echo "  sudo systemctl enable --now linux-monitor-backend"
echo
echo "Check on it with:"
echo "  systemctl status linux-monitor-backend"
echo "  journalctl -u linux-monitor-backend -f"
