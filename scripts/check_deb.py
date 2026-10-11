#!/usr/bin/env python3
"""Smoke-test an extracted package without installing it or using a developer venv.

Usage: python3 scripts/check_deb.py dist/linux-monitor_<version>_<architecture>.deb
Starts a temporary localhost server and database; requires the matching system Python.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


def check(artifact: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="linux-monitor-check-") as temporary:
        temporary_path = Path(temporary)
        root = temporary_path / "root"
        control = temporary_path / "control"
        subprocess.run(["dpkg-deb", "--extract", str(artifact), str(root)], check=True)
        subprocess.run(["dpkg-deb", "--control", str(artifact), str(control)], check=True)
        private = root / "usr/lib/linux-monitor"
        dashboard = root / "usr/share/linux-monitor/dashboard"
        inventory = json.loads(
            (root / "usr/share/doc/linux-monitor/runtime-dependencies.json").read_text()
        )
        assert not {"pip", "pytest", "ruff", "httpx", "httpx2"} & {
            item["name"].lower() for item in inventory["dependencies"]
        }
        assert not list(root.rglob(".env"))
        assert not list(root.rglob("*.db"))
        assert (control / "conffiles").read_text().strip() == "/etc/linux-monitor/monitor.env"
        assert (
            "User=linux-monitor"
            in (root / "usr/lib/systemd/system/linux-monitor.service").read_text()
        )
        assert (root / "usr/bin/linux-monitor").stat().st_mode & 0o111
        assert (private / "native.py").is_file()
        assert "python3-tk" in (control / "control").read_text()
        for script in ("postinst", "prerm", "postrm"):
            subprocess.run(["sh", "-n", str(control / script)], check=True)

        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith("MONITOR_")
        }
        environment.update(
            {
                "MONITOR_BACKEND_PORT": str(port),
                "MONITOR_BACKEND_HOST": "127.0.0.1",
                "MONITOR_FRONTEND_DIR": str(dashboard),
                "MONITOR_DATABASE_PATH": str(temporary_path / "history.db"),
                "MONITOR_CONFIG_FILE": str(private / "backend/config/monitor.yaml"),
                "MONITOR_POLLING_INTERVAL_SECONDS": "1",
                "MONITOR_MONITORED_SERVICES": "",
            }
        )
        launcher = subprocess.check_output(
            ["/usr/bin/python3", "-I", "-S", str(root / "usr/bin/linux-monitor"), "--url"],
            env=environment,
            text=True,
        ).strip()
        assert launcher == f"http://127.0.0.1:{port}/"
        opener = build_opener(ProxyHandler({}))
        with (temporary_path / "server.log").open("w+") as log:
            # -I -S removes developer/site packages and ignores PYTHONPATH.
            process = subprocess.Popen(
                ["/usr/bin/python3", "-I", "-S", str(private / "server.py")],
                env=environment,
                cwd=temporary_path,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        with opener.open(launcher + "api/health", timeout=1) as response:
                            assert json.load(response)["status"] == "ok"
                        break
                    except (URLError, OSError):
                        if process.poll() is not None or time.monotonic() >= deadline:
                            log.seek(0)
                            raise RuntimeError(
                                "Packaged server did not start:\n" + log.read()
                            ) from None
                        time.sleep(0.1)

                def get(path: str):
                    return opener.open(launcher + path.lstrip("/"), timeout=5)

                with get("/") as response:
                    assert "Server Monitor" in response.read().decode()
                    assert response.headers["Cache-Control"] == "no-cache"
                with get("sw.js") as response:
                    source = response.read().decode()
                    assert response.headers["Cache-Control"] == "no-cache"
                shell_urls = json.loads(re.search(r"const SHELL_URLS = (\[[^\n]+\])", source)[1])
                for url in shell_urls:
                    with get(url) as response:
                        assert response.status == 200
                        assert response.read()
                        if url.startswith("/assets/"):
                            assert "immutable" in response.headers["Cache-Control"]
                with get("api/system") as response:
                    assert json.load(response)["hostname"]
                with get("api/metrics/current") as response:
                    metrics = json.load(response)
                    assert "cpu" in metrics and "memory" in metrics
                with get("api/metrics/history") as response:
                    assert "points" in json.load(response)
                with get("docs") as response:
                    assert response.status == 200
                for url in ("api/missing", "assets/missing.js", ".env"):
                    try:
                        get(url)
                    except HTTPError as error:
                        assert error.code == 404
                        assert json.load(error)["error"]["code"] == "not_found"
                    else:
                        raise AssertionError(f"Expected 404 for {url}")
                try:
                    opener.open(Request(launcher + "api/health", method="POST"), timeout=5)
                except HTTPError as error:
                    assert error.code == 405
                    assert json.load(error)["error"]["code"] == "method_not_allowed"
                else:
                    raise AssertionError("Expected API method error")
                assert (temporary_path / "history.db").is_file()
                print("PASS: package contents exclude developer tools, secrets, and runtime data")
                print("PASS: bundled dependencies work with isolated system Python (-I -S)")
                print(
                    "PASS: live metrics, database, API errors, and PWA shell files share one server"
                )
                print("PASS: launcher URL, HTTP caching, conffile, and service metadata")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    check(args.artifact.resolve())
