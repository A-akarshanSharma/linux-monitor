#!/usr/bin/python3
"""Open the native dashboard, with an explicit browser option and WSL fallback."""

import argparse
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

sys.dont_write_bytecode = True
# The launcher lives in /usr/bin. Deriving /usr also allows package extraction
# tests to run without installing anything on the development host.
prefix = Path(__file__).resolve().parents[1]
private = prefix / "lib/linux-monitor"
sys.path[:0] = [str(private / "backend"), str(private / "vendor")]


def main() -> int:
    from app.config import Settings

    parser = argparse.ArgumentParser(description="Open Linux Server Monitor")
    parser.add_argument(
        "--url", action="store_true", help="Print the dashboard URL without opening it"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--browser", action="store_true", help="Open the web dashboard")
    mode.add_argument("--native", action="store_true", help="Open the native desktop window")
    args = parser.parse_args()
    settings = Settings(_env_file="/etc/linux-monitor/monitor.env")
    url = f"http://127.0.0.1:{settings.backend_port}/"
    if args.url:
        print(url)
        return 0

    # WSL can start the distribution and its systemd services on this launch.
    # Ignore HTTP proxies for requests to the user's own machine.
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 20
    while True:
        try:
            with opener.open(url + "api/health", timeout=1) as response:
                if response.status == 200:
                    break
        except (URLError, OSError):
            pass
        if time.monotonic() >= deadline:
            print(
                "The monitoring service is not ready. Check: systemctl status linux-monitor",
                file=sys.stderr,
            )
            print(f"Dashboard: {url}", file=sys.stderr)
            return 1
        time.sleep(0.5)

    use_native = args.native or (not args.browser and bool(os.environ.get("DISPLAY")))
    if use_native:
        # exec releases the settings/dependency imports before the UI starts.
        os.execv(sys.executable, [sys.executable, "-s", str(private / "native.py"), "--url", url])

    if not args.browser and not os.environ.get("WSL_DISTRO_NAME"):
        print("No graphical display. Use linux-monitor --browser or --url.", file=sys.stderr)
        return 1
    print(f"Opening {url}")
    if os.environ.get("WSL_DISTRO_NAME") and (explorer := shutil.which("explorer.exe")):
        subprocess.Popen([explorer, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    if webbrowser.open(url):
        return 0
    print(f"Open this URL in your browser: {url}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
