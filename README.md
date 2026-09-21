# Linux Server Monitoring & Alerting Platform

A small, production-style monitoring platform for Linux hosts: a Python agent collects
system metrics, a FastAPI backend stores and serves them, an alert engine tracks threshold
breaches, and a React dashboard visualises everything.

> **Status: Phase 1 of 9 - metrics collector.** This README grows with each phase;
> the final version (Phase 9) will include the architecture diagram, API reference,
> screenshots and design decisions.

| Phase | Scope | Status |
|------:|-------|:------:|
| 1 | Metrics collector, config, logging, tests | done |
| 2 | FastAPI API | |
| 3 | SQLite history + scheduler | |
| 4 | Alert engine | |
| 5 | Linux service monitoring | |
| 6 | React dashboard | |
| 7 | Docker / Compose | |
| 8 | Full test suite + GitHub Actions | |
| 9 | Docs, screenshots, cleanup | |

## Phase 1: what exists

```
backend/
├── app/
│   ├── config.py            # pydantic-settings: env > .env > YAML > defaults
│   ├── logging_config.py    # structured JSON logging (stdlib only)
│   ├── models/metrics.py    # Pydantic schemas shared by every later layer
│   └── collectors/
│       ├── system_info.py   # hostname, OS, IP, uptime, WSL/container detection
│       ├── cpu.py           # utilisation, load average, core counts
│       ├── memory.py        # RAM + swap
│       ├── disk.py          # per-mount usage, pseudo-FS filtering, bind-mount dedup
│       ├── network.py       # per-interface counters + bytes/sec rates (stateful)
│       ├── processes.py     # process count, top by CPU / memory
│       ├── snapshot.py      # aggregates all collectors into one MetricsSnapshot
│       └── __main__.py      # CLI: python -m app.collectors
├── config/monitor.yaml
├── tests/                   # 58 tests, all system calls mocked (plus one real smoke test)
└── requirements*.txt, pyproject.toml
```

## Setup (Ubuntu / WSL2)

```bash
# Keep the repo inside the Linux filesystem (~/), not under /mnt/c
cd linux-monitor/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Requires Python 3.10+ (developed and tested on 3.12; Ubuntu 24.04 ships it).

## Run

```bash
cd backend

python -m app.collectors                 # one full snapshot as pretty JSON
python -m app.collectors --compact       # single-line JSON (pipe to jq)
python -m app.collectors --watch         # a snapshot every polling interval, Ctrl+C to stop
python -m app.collectors --help
```

JSON goes to **stdout**; structured logs go to **stderr**, so
`python -m app.collectors | jq .cpu` works.

## Test and lint

```bash
cd backend
pytest
ruff check .
ruff format --check .
```

## Configuration

Precedence, highest first: environment variables > `.env` > `backend/config/monitor.yaml` > defaults.
Copy `.env.example` to `.env` to override values. All variables use the `MONITOR_` prefix.

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `MONITOR_LOG_FORMAT` | `json` | `json` or human-readable `text` |
| `MONITOR_POLLING_INTERVAL_SECONDS` | `10` | Delay between snapshots in `--watch` mode (later: the collection loop) |
| `MONITOR_TOP_PROCESSES_COUNT` | `5` | Size of the top-CPU / top-memory lists |
| `MONITOR_DISK_EXCLUDE_FSTYPES` | tmpfs, overlay, squashfs, 9p, `fuse.*`, ... | Comma-separated; `*` wildcards supported |

## Notes on WSL

Metrics describe the **WSL2 virtual machine**, not Windows: uptime is the VM's uptime, RAM and
core counts are whatever `.wslconfig` allots to the VM, and `/` is the VM's virtual disk.
Windows drives (`/mnt/c`, filesystem type `9p`) are excluded from disk metrics by default.
The `system.runtime_environment` field reports `wsl`, `container` or `host` so consumers
know how to interpret the numbers.

## Design decisions so far

- **Collectors are read-only, side-effect-free modules** with no knowledge of storage or alerting.
- **Rate metrics need a baseline.** CPU % and network bytes/sec are computed relative to the
  previous poll. `SnapshotCollector.prime()` takes the baseline; the network collector is a class
  that remembers its last sample and tolerates counter resets.
- **CPU % is non-blocking**: it measures the window since the last poll instead of sleeping
  inside the collector.
- **Memory % uses *available* memory**, not *free* memory, to avoid permanent false alarms on Linux.
- **Command lines are never collected** for processes: arguments often contain secrets.
- **Fail-fast snapshots**: if any collector fails, `CollectionError` names it; the caller decides
  whether to log, retry or skip the cycle.
