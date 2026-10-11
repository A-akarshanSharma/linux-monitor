#!/usr/bin/env bash
# Install/reinstall/upgrade/remove/purge in a disposable Ubuntu container.
# Nothing from the source checkout is mounted except the .deb, read-only.
set -euo pipefail
ARTIFACT_INPUT="${1:?Usage: scripts/check_deb_install.sh path/to/package.deb}"
ARTIFACT="$(cd "$(dirname "$ARTIFACT_INPUT")" && pwd)/$(basename "$ARTIFACT_INPUT")"
TEST_IMAGE="${MONITOR_PACKAGE_TEST_IMAGE:-ubuntu:26.04}"
test -f "$ARTIFACT"

docker run --rm -i --mount "type=bind,source=$ARTIFACT,target=/tmp/linux-monitor.deb,readonly" \
    "$TEST_IMAGE" /bin/bash -se <<'CONTAINER'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends /tmp/linux-monitor.deb
test -L /etc/systemd/system/multi-user.target.wants/linux-monitor.service
test -x /usr/bin/linux-monitor
test -f /usr/share/applications/linux-monitor.desktop
test -f /usr/lib/linux-monitor/native.py
python3 -c 'import tkinter; assert tkinter.TkVersion >= 8.6'
systemd-analyze verify /usr/lib/systemd/system/linux-monitor.service
! command -v npm
python3 -c 'import importlib.util; assert importlib.util.find_spec("fastapi") is None; assert importlib.util.find_spec("pip") is None'

# Exercise a custom port and verify that it survives package updates.
sed -i 's/MONITOR_BACKEND_PORT=8765/MONITOR_BACKEND_PORT=9876/' /etc/linux-monitor/monitor.env
test "$(linux-monitor --url)" = 'http://127.0.0.1:9876/'
python3 - <<'PYTHON'
import json
import os
import pwd
import subprocess
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

environment = dict(os.environ)
for line in open('/etc/linux-monitor/monitor.env'):
    if line.startswith('MONITOR_'):
        key, value = line.strip().split('=', 1)
        environment[key] = value
environment['MONITOR_MONITORED_SERVICES'] = ''
account = pwd.getpwnam('linux-monitor')
with open('/tmp/server.log', 'w+') as log:
    process = subprocess.Popen(
        ['/usr/bin/python3', '-I', '-S', '/usr/lib/linux-monitor/server.py'],
        user=account.pw_uid, group=account.pw_gid, env=environment,
        cwd='/var/lib/linux-monitor', stdout=log, stderr=log,
    )
    try:
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 20
        while True:
            try:
                with opener.open('http://127.0.0.1:9876/api/health', timeout=1) as response:
                    assert json.load(response)['status'] == 'ok'
                break
            except (URLError, OSError):
                if process.poll() is not None or time.monotonic() > deadline:
                    log.seek(0)
                    raise RuntimeError(log.read())
                time.sleep(0.1)
        with opener.open('http://127.0.0.1:9876/') as response:
            assert 'Server Monitor' in response.read().decode()
        with opener.open('http://127.0.0.1:9876/api/metrics/current') as response:
            metrics = json.load(response)
            assert metrics['memory']['ram_total_bytes'] > 0
        with opener.open('http://127.0.0.1:9876/manifest.webmanifest') as response:
            assert json.load(response)['display'] == 'standalone'
        assert os.stat('/var/lib/linux-monitor/monitor.db').st_uid == account.pw_uid
        print('PASS: fresh install enables service; UI/API run as the dedicated user without pip or npm')
    finally:
        process.terminate()
        process.wait(timeout=10)
PYTHON

HISTORY_BEFORE="$(sha256sum /var/lib/linux-monitor/monitor.db)"
DPKG_MAINTSCRIPT_PACKAGE=linux-monitor deb-systemd-helper disable linux-monitor.service
apt-get install -y -qq --reinstall --no-install-recommends /tmp/linux-monitor.deb
grep -q '^MONITOR_BACKEND_PORT=9876$' /etc/linux-monitor/monitor.env
test "$(sha256sum /var/lib/linux-monitor/monitor.db)" = "$HISTORY_BEFORE"
test ! -L /etc/systemd/system/multi-user.target.wants/linux-monitor.service
echo 'PASS: reinstall preserves configuration, history, and an explicitly disabled service'

# Exercise a real version upgrade, including dpkg's maintainer-script arguments.
dpkg-deb --raw-extract /tmp/linux-monitor.deb /tmp/upgrade-root
sed -i 's/^Version: \(.*\)$/Version: \1+test1/' /tmp/upgrade-root/DEBIAN/control
dpkg-deb --build /tmp/upgrade-root /tmp/linux-monitor-upgrade.deb
apt-get install -y -qq --no-install-recommends /tmp/linux-monitor-upgrade.deb
grep -q '^MONITOR_BACKEND_PORT=9876$' /etc/linux-monitor/monitor.env
test "$(sha256sum /var/lib/linux-monitor/monitor.db)" = "$HISTORY_BEFORE"
test ! -L /etc/systemd/system/multi-user.target.wants/linux-monitor.service
echo 'PASS: version upgrade preserves configuration, history, and service enablement preference'

apt-get remove -y -qq linux-monitor
test -f /etc/linux-monitor/monitor.env
test -f /var/lib/linux-monitor/monitor.db
test ! -e /usr/bin/linux-monitor
apt-get purge -y -qq linux-monitor
test ! -e /etc/linux-monitor/monitor.env
test ! -L /etc/systemd/system/multi-user.target.wants/linux-monitor.service
test ! -e /usr/lib/linux-monitor
test -f /var/lib/linux-monitor/monitor.db
echo 'PASS: removal and purge preserve history; purge removes configuration and service links'
CONTAINER
