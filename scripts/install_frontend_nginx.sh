#!/usr/bin/env bash
# Build and install the local dashboard. Requires Node/npm, nginx, systemd,
# and sudo. Installs only this project's config; existing nginx sites stay intact.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/../frontend" && pwd)"
FRONTEND_PORT="${MONITOR_FRONTEND_PORT:-8080}"
BACKEND_PORT="${MONITOR_BACKEND_PORT:-8000}"

for cmd in npm nginx systemctl sudo; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "$cmd is required. Install it before running this script." >&2
        exit 1
    fi
done

for port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
    if [[ ! "$port" =~ ^[0-9]{1,5}$ ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
        echo "Ports must be integers between 1 and 65535." >&2
        exit 1
    fi
done
FRONTEND_PORT=$((10#$FRONTEND_PORT))
BACKEND_PORT=$((10#$BACKEND_PORT))
if [ "$FRONTEND_PORT" = "$BACKEND_PORT" ]; then
    echo "Frontend and backend must use different ports." >&2
    exit 1
fi

cd "$FRONTEND_DIR"
npm ci
npm run build

GENERATED_CONFIG="$(mktemp)"
trap 'rm -f "$GENERATED_CONFIG"' EXIT
sed -e "s|__FRONTEND_PORT__|$FRONTEND_PORT|g" -e "s|__BACKEND_PORT__|$BACKEND_PORT|g" \
    "$SCRIPT_DIR/nginx-host.conf.template" > "$GENERATED_CONFIG"

sudo install -d -m 755 /var/www/linux-monitor
# Keep older fingerprinted assets available to any open dashboard windows.
sudo cp -R dist/. /var/www/linux-monitor/
sudo chmod -R a+rX /var/www/linux-monitor
sudo install -m 644 "$GENERATED_CONFIG" /etc/nginx/conf.d/linux-monitor.conf
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx

echo "Dashboard installed at http://localhost:$FRONTEND_PORT"
echo "Backend must be running on 127.0.0.1:$BACKEND_PORT."
echo "Re-run this script after frontend changes to publish the new build locally."
