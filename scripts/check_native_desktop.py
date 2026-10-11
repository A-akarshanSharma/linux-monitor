#!/usr/bin/env python3
"""Exercise the native GUI and measure its process under a real/virtual X display.

Example: xvfb-run -a python3 scripts/check_native_desktop.py
Requires python3-tk; Pillow is optional, used only for a review screenshot.
--module can point at native.py extracted from or installed by the package.
"""

import argparse
import importlib.util
import json
import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--module", type=Path, default=Path(__file__).resolve().parents[1] / "packaging/native.py"
    )
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument(
        "--launcher", type=Path, help="Also exercise the installed desktop launcher"
    )
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("native", args.module)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    now = datetime.now(timezone.utc)
    processes = [
        {
            "pid": 42,
            "name": "fixture-process",
            "username": "ubuntu",
            "cpu_percent": 12.5,
            "memory_percent": 2.5,
            "memory_rss_bytes": 20000000,
        }
    ]
    fixtures = {
        "health": {"status": "ok", "version": "0.6.0"},
        "system": {
            "hostname": "native-test-host",
            "os_name": "Ubuntu",
            "kernel": "test",
            "ip_address": "127.0.0.1",
            "uptime_seconds": 3661,
        },
        "current": {
            "cpu": {"utilization_percent": 12.5, "load_avg_1m": 0.4, "logical_cores": 4},
            "memory": {
                "ram_percent": 37.5,
                "ram_used_bytes": 3 * 1024**3,
                "ram_total_bytes": 8 * 1024**3,
                "swap_percent": 0,
                "swap_used_bytes": 0,
            },
            "network": {"send_rate_bytes_per_sec": 1000, "recv_rate_bytes_per_sec": None},
            "disks": [
                {
                    "mountpoint": "/",
                    "device": "/dev/sda",
                    "used_bytes": 2 * 1024**3,
                    "total_bytes": 40 * 1024**3,
                    "percent": 5,
                }
            ],
        },
        "history": {
            "points": [
                {
                    "collected_at": (now - timedelta(seconds=(179 - i) * 10)).isoformat(),
                    "cpu_percent": 15 + math.sin(i / 10) * 10,
                    "ram_percent": 37.5,
                    "send_rate_bytes_per_sec": 1000 + math.sin(i / 12) * 700,
                    "recv_rate_bytes_per_sec": None if i == 80 else 2000 + math.sin(i / 9) * 1000,
                }
                for i in range(180)
            ]
        },
        "processes": {"top_by_cpu": processes, "top_by_memory": processes},
        "services": {"services": [{"name": "linux-monitor", "state": "RUNNING"}]},
        "alerts": {
            "alerts": [
                {
                    "state": "WARNING",
                    "rule_key": "cpu",
                    "target": "",
                    "message": "A test alert; the native UI keeps backend severity",
                }
            ]
        },
    }
    offline, requests = False, []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            name = next(
                name
                for name, endpoint in native.ENDPOINTS.items()
                if "/api/" + endpoint == self.path
            )
            self.send_response(503 if offline else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "offline"} if offline else fixtures[name]).encode()
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    root = tk.Tk()
    ui = native.Dashboard(root, url)
    # Faster polling for lifecycle checks only; the measured child uses defaults.
    ui.poller.interval = 0.2

    def wait(predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise AssertionError("Native GUI condition timed out")
            root.update()
            time.sleep(0.02)
        root.update()

    try:
        wait(lambda: ui.stats[0][0].cget("text") == "12.5%")
        assert ui.identity.cget("text") == "native-test-host"
        assert len(ui.tables["disks"].get_children()) == 1
        assert ui.tables["services"].item("0", "values")[1] == "running"
        assert ui.stats[0][0].cget("fg") == native.AMBER
        assert all(chart[0].find_all() for chart in ui.charts)
        ui.sort.set("top_by_memory")
        ui.draw_processes()
        assert ui.tables["processes"].item("0", "values")[0] == "42"
        ui.tables["alerts"].selection_set("0")
        ui.show_alert()
        assert ui.alert_detail.cget("text").startswith("A test alert")
        root.geometry("950x740")
        root.update()
        assert all(chart[0].winfo_width() > 100 for chart in ui.charts)
        # Exercise the empty-history path, including network max with no samples.
        ui.render({"history": {"points": []}}, {})
        assert all(chart[0].find_all() for chart in ui.charts)
        print("PASS: native metrics, history charts, tables, severity, selection and resizing")

        offline = True
        wait(lambda: ui.status.cget("text").startswith("Update failed"))
        assert ui.stats[0][0].cget("text") == "12.5%"
        offline = False
        fixtures["current"]["cpu"]["utilization_percent"] = 22.5
        wait(lambda: ui.stats[0][0].cget("text") == "22.5%")
        print("PASS: HTTP outage preserves readings, labels them stale and recovers")

        root.withdraw()
        root.update()
        time.sleep(0.4)
        paused_count = len(requests)
        time.sleep(0.6)
        root.update()
        assert len(requests) == paused_count
        root.deiconify()
        wait(lambda: len(requests) > paused_count)
        wait(lambda: not ui.poller.results.empty())
        root.update()
        if args.screenshot:
            from PIL import ImageGrab

            ImageGrab.grab().save(args.screenshot)
        print("PASS: hidden window pauses requests; reopening refreshes immediately")
    finally:
        ui.close()
        ui.poller.thread.join(3)
        assert not ui.poller.thread.is_alive()

    if args.launcher:
        environment = dict(os.environ, MONITOR_BACKEND_PORT=str(server.server_port))
        gui = subprocess.Popen([str(args.launcher)], env=environment)
    else:
        gui = subprocess.Popen([sys.executable, "-s", str(args.module), "--url", url])
    try:
        time.sleep(3)
        assert "native.py" in Path(f"/proc/{gui.pid}/cmdline").read_text(), (
            "Launcher must exec the native window, without a browser"
        )

        def sample():
            fields = Path(f"/proc/{gui.pid}/stat").read_text().split(") ")[-1].split()
            rollup = Path(f"/proc/{gui.pid}/smaps_rollup").read_text().splitlines()
            values = {
                line.split(":")[0]: int(line.split()[1])
                for line in rollup
                if line.startswith(("Rss:", "Pss:"))
            }
            return {
                "cpu": (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK"),
                "rssMiB": values["Rss"] / 1024,
                "pssMiB": values["Pss"] / 1024,
            }

        before = sample()
        deadline = time.monotonic() + args.seconds
        peak = before["rssMiB"]
        while time.monotonic() < deadline:
            assert gui.poll() is None, "Native window unexpectedly exited"
            peak = max(peak, sample()["rssMiB"])
            time.sleep(1)
        after = sample()
        print(
            json.dumps(
                {
                    "nativeGUI": {
                        "before": before,
                        "after": after,
                        "peakRssMiB": peak,
                        "seconds": args.seconds,
                        "cpuPercentOneCore": (after["cpu"] - before["cpu"]) / args.seconds * 100,
                    }
                },
                indent=2,
            )
        )
    finally:
        gui.terminate()
        gui.wait(timeout=5)
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
