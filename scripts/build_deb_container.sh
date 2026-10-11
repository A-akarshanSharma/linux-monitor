#!/usr/bin/env bash
# Build for a target Ubuntu release without modifying the host Python setup.
# The frontend must be built first. Docker and internet access are required.
set -euo pipefail
UBUNTU_RELEASE="${1:-24.04}"
if [[ ! "$UBUNTU_RELEASE" =~ ^[0-9]{2}\.[0-9]{2}$ ]]; then
    echo "Usage: scripts/build_deb_container.sh 24.04 (or another Ubuntu release)" >&2
    exit 1
fi
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$PROJECT_DIR/frontend/dist/sw.js" || {
    echo "Build the frontend first: cd frontend && npm ci && npm run build" >&2
    exit 1
}
mkdir -p "$PROJECT_DIR/dist"
OWNER_UID="$(id -u)"
OWNER_GID="$(id -g)"

docker run --rm -i \
    --mount "type=bind,source=$PROJECT_DIR,target=/source,readonly" \
    --mount "type=bind,source=$PROJECT_DIR/dist,target=/output" \
    -e "BUILD_OWNER_UID=$OWNER_UID" -e "BUILD_OWNER_GID=$OWNER_GID" \
    "ubuntu:$UBUNTU_RELEASE" /bin/bash -se <<'CONTAINER'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends python3-venv ca-certificates
python3 -m venv /tmp/build-env
/tmp/build-env/bin/pip install --quiet --disable-pip-version-check -r /source/backend/requirements.txt
/tmp/build-env/bin/python /source/scripts/build_deb.py --skip-frontend-build --output-dir /output
TARGET="$(. /etc/os-release && printf '%s%s' "$ID" "$VERSION_ID")"
ARCHITECTURE="$(dpkg --print-architecture)"
for artifact in /output/linux-monitor_*+"$TARGET"_"$ARCHITECTURE".deb; do
    chown "$BUILD_OWNER_UID:$BUILD_OWNER_GID" "$artifact"
done
CONTAINER
