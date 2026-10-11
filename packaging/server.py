"""Private entry point for the installed service (uses bundled dependencies)."""

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
sys.path[:0] = [str(root / "backend"), str(root / "vendor")]
os.environ.setdefault(
    "MONITOR_FRONTEND_DIR", str(root.parents[1] / "share/linux-monitor/dashboard")
)
os.environ.setdefault("MONITOR_DATABASE_PATH", "/var/lib/linux-monitor/monitor.db")
os.environ.setdefault("MONITOR_BACKEND_PORT", "8765")
os.environ.setdefault("MONITOR_MONITORED_SERVICES", "linux-monitor")


def main() -> int:
    from app.__main__ import main as start_server

    return start_server()


if __name__ == "__main__":
    sys.exit(main())
