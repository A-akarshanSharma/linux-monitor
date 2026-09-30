# Linux Server Monitoring & Alerting Platform

A small, production-style monitoring platform for Linux hosts: a Python agent collects
system metrics, a FastAPI backend stores and serves them, an alert engine tracks threshold
breaches, and a React dashboard visualises everything.

> **Status: Phase 6 of 9 - React dashboard.** This README grows with each phase;
> the final version (Phase 9) will include the architecture diagram, API reference,
> screenshots and design decisions.

| Phase | Scope | Status |
|------:|-------|:------:|
| 1 | Metrics collector, config, logging, tests | done |
| 2 | FastAPI API (live endpoints), error handling, tests | done |
| 3 | SQLite history, background scheduler, `/api/metrics/history` | done |
| 4 | Alert engine: rules, states, dedup, `/api/alerts` | done |
| 5 | Linux service monitoring, `/api/services`, service-down alerts | done |
| 6 | React dashboard | done |
| 7 | Docker / Compose | |
| 8 | Full test suite + GitHub Actions | |
| 9 | Docs, screenshots, cleanup | |

## What exists so far

```
backend/            # FastAPI + SQLite + alert engine + service monitor (Phases 1-5)
frontend/            # React + Vite dashboard (this phase)
├── src/
│   ├── api/client.js       # fetch wrapper matching the backend's error envelope
│   ├── config.js            # poll intervals, history window, process list size
│   ├── hooks/                # usePolling (generic) + one hook per backend endpoint
│   ├── utils/                # formatting, status-color mapping, alert cross-referencing
│   └── components/
│       ├── layout/           # Header, Panel (shared section shell), StatusDot
│       ├── metrics/           # stat cards, disk usage, CPU/memory/network charts
│       ├── processes/         # top-processes table (by CPU / by memory)
│       ├── services/          # service health list
│       └── alerts/            # active + recently resolved alerts feed
├── vite.config.js     # dev/preview server proxies /api/* to the backend (no CORS needed)
└── README.md           # frontend-specific run instructions and design notes
```

See `frontend/README.md` for how to run it and the design reasoning behind the look.

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

### Start the API

```bash
cd backend
python -m app                      # host/port from configuration (default 127.0.0.1:8000)
# equivalent: uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Open <http://localhost:8000/docs> for the interactive Swagger UI. On WSL2 this also works from a
Windows browser through WSL's localhost forwarding.

```bash
curl -s localhost:8000/api/health
curl -s localhost:8000/api/metrics/current | jq .cpu
curl -s "localhost:8000/api/processes?limit=3" | jq '.top_by_cpu[].name'
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/system` | Hostname, IP, OS, kernel, uptime, runtime environment (host / wsl / container) |
| GET | `/api/metrics/current` | CPU, memory, disks, network (with bytes/sec rates); at most 1 s old |
| GET | `/api/metrics/history?minutes=N` | Stored samples over the last N minutes, oldest first. `minutes` defaults to `metrics_history_default_minutes` and is clamped to the retention window - never a 422 for asking too far back |
| GET | `/api/processes?limit=N` | Process counts + top N by CPU and by memory (`1 <= N <= 50`, default from config) |
| GET | `/api/alerts?minutes=N` | Every currently active alert (any age) plus alerts resolved in the last N minutes, most recently updated first |
| GET | `/api/services` | Current status (RUNNING / STOPPED / UNKNOWN) of every service in `MONITOR_MONITORED_SERVICES`, via `systemctl is-active` |
| GET | `/api/health` | Liveness probe: status, version, API uptime |

All endpoints listed in the original project scope now exist.

Every error, including 404/405/422, has the same shape; server-side details are never leaked:

```json
{"error": {"code": "validation_error", "message": "Request validation failed.",
           "details": [{"field": "query.limit", "message": "Input should be less than or equal to 50"}]}}
```

| Status | `code` | Meaning |
|-------:|--------|---------|
| 422 | `validation_error` | Invalid query parameter |
| 503 | `collection_failed` | A collector could not read system data; retry shortly |
| 500 | `internal_error` | Unexpected server error (logged with stack trace as `api_error`) |

### Start the dashboard

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Requires the backend running first (`cd backend && python -m app`). The dev server
proxies `/api/*` to the backend (see `frontend/vite.config.js`), so no CORS setup is
needed and the browser only ever talks to one origin.

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
| `MONITOR_BACKEND_HOST` | `127.0.0.1` | API bind address (`0.0.0.0` for all interfaces) |
| `MONITOR_BACKEND_PORT` | `8000` | API port |
| `MONITOR_DATABASE_PATH` | `data/monitor.db` | SQLite file; relative paths resolve against `backend/` |
| `MONITOR_RETENTION_DAYS` | `7` | How long samples are kept before being pruned |
| `MONITOR_METRICS_HISTORY_DEFAULT_MINUTES` | `60` | Look-back window when `/api/metrics/history` is called without `?minutes=` |
| `MONITOR_CPU_WARNING_PERCENT` / `MONITOR_CPU_CRITICAL_PERCENT` | `85` / `95` | CPU alert thresholds (%) |
| `MONITOR_CPU_SUSTAINED_SECONDS` | `60` | How long CPU must stay >= the warning threshold before the first alert fires |
| `MONITOR_MEMORY_WARNING_PERCENT` / `MONITOR_MEMORY_CRITICAL_PERCENT` | `90` / `95` | Memory alert thresholds (%) |
| `MONITOR_DISK_WARNING_PERCENT` / `MONITOR_DISK_CRITICAL_PERCENT` | `80` / `90` | Disk alert thresholds (%), per mount point |
| `MONITOR_MONITORED_SERVICES` | `nginx,ssh,docker` | Linux service names (as `systemctl` knows them) to check every cycle |
| `MONITOR_ALERTS_HISTORY_DEFAULT_MINUTES` | `1440` | Look-back window for *resolved* alerts in `/api/alerts`; active alerts are always included |
| `MONITOR_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `MONITOR_LOG_FORMAT` | `json` | `json` or human-readable `text` |
| `MONITOR_POLLING_INTERVAL_SECONDS` | `10` | Delay between snapshots in `--watch` mode (later: the background collection loop) |
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
- **A single background thread owns the one `SnapshotCollector` instance.** `MetricsScheduler`
  collects on `polling_interval_seconds`, keeps the latest reading in memory for `/api/metrics/current`
  and `/api/processes`, and persists every reading for history. The API never triggers a collection
  itself, so `/api/metrics/current` freshness is bounded by the polling interval, not by request timing.
- **Start-up does one collection synchronously** (after a short warm-up so the first CPU/network
  reading isn't a meaningless 0%) before the app finishes starting, so the very first request
  already has real data instead of a 503.
- **A storage failure never takes the live API down.** `_collect_once()` updates the in-memory
  latest snapshot before it tries to write to SQLite; if the write fails, it's logged
  (`metrics_persist_failed`) and history has a gap for that cycle, but `/api/metrics/current` keeps working.
- **`minutes` on `/api/metrics/history` is clamped, not rejected**, when it exceeds the retention
  window - since nothing older is ever kept, asking for more just returns everything there is.
- **Pruning runs after every collection cycle** rather than on a separate timer. The delete is a
  single indexed-column query, cheap at the row volumes a portfolio deployment produces; a
  separate periodic job would be the next step at real scale.
- **SQLite runs in WAL mode with a busy_timeout**, so the scheduler's writes and API's reads don't
  block each other. `collected_at` is stored and always read back as UTC - SQLite has no native
  timezone-aware type, so a naive value from the database is explicitly re-labelled UTC rather than
  risking it being read as local time.
- **Sync endpoints, not `async def`**: psutil calls block, and FastAPI runs plain `def` routes on a
  thread pool so they cannot stall the event loop.
- **One error contract**: handlers for validation, HTTP and unexpected errors all emit the same JSON
  shape; 5xx responses are generic and the detail goes to the structured log.
- **`/api/health` is a pure liveness probe** and stays green even if metric collection is failing;
  it does not check the database or the scheduler, only that the process is answering requests.
- **Alert states, concretely: WARNING, CRITICAL, RESOLVED - never NORMAL.** NORMAL is the absence
  of an alert row, not a value that gets written. An alert is created as WARNING or CRITICAL, may
  escalate or de-escalate on that same row while it stays open, and is marked RESOLVED (not deleted)
  once the condition clears - so alert history is preserved rather than lost.
- **One open alert per (rule, target)** is "duplicate alert prevention": `AlertsRepository.upsert_open_alert`
  updates the existing row on a repeated breach instead of inserting a new one, enforced in
  application logic *and* by a SQLite partial unique index (`WHERE resolved_at IS NULL`) as a second
  line of defence - verified with a test that inserts around the repository layer and confirms the
  database itself rejects a duplicate.
- **Only CPU has a sustained-duration requirement** (`cpu_sustained_seconds`, default 60s), matching
  the "CPU > 85% for at least 60 seconds" spec. Memory and disk alert on the very next collection
  cycle. The breach timer is tracked in memory by `AlertEngine`, not the database, so it resets to
  zero on restart - a brief spike right after a restart needs to hold for the full duration again.
  It also resets on any single reading that dips back under the threshold, verified live: a demo run
  showed CPU readings bouncing 1.0% / 0.0% / 4.0% on an idle sandbox, correctly preventing a
  low-enough threshold from ever accumulating a full sustained breach.
- **The service-down rule was built inert in Phase 4** (`evaluate_services()` takes a
  `dict[str, bool]` of service name -> is running, but nothing supplied real data yet) **and is now
  live in Phase 5** - the scheduler calls `check_services()`, persists the results, and passes
  running/stopped state into the same `alert_engine.evaluate()` call, with no changes needed to the
  rule or its dedup/resolve behaviour.
- **Known limitation:** if a rule's target stops being observed entirely (a disk unmounted, a
  service dropped from the monitored list) rather than merely returning to normal, any alert already
  open for it is never automatically resolved, since no further evaluation is produced for that
  target to trigger the resolve path. Documented in `AlertEngine`'s docstring rather than solved,
  since reconciling "keys that used to exist" against "keys still open" would add a query and real
  complexity for an edge case.
- **Service state has three values, not two: RUNNING, STOPPED, UNKNOWN - and UNKNOWN is never
  treated as down.** `systemctl` frequently can't answer at all: not installed, no systemd to talk
  to (the normal case inside a Docker container without special setup, or WSL with systemd
  disabled), the unit name doesn't exist, or the call times out. `service_monitor.py` collapses
  every one of those cases to UNKNOWN with a `detail` string explaining why, rather than guessing.
  The scheduler then leaves UNKNOWN services out of what it hands the alert engine entirely, so they
  can never trigger a false "service down" alert - verified live on this project's own sandbox,
  which has `systemctl` installed but no real systemd running (a containerized environment), and
  correctly reports all three default services as UNKNOWN with zero alerts.
- **Service status has no history table**, unlike metrics and alerts: `service_status` holds one row
  per service, updated in place every cycle. `last_changed_at` (separate from `last_checked_at`)
  already answers "how long has it been like this" without needing a time series, and only updates
  when the state actually differs from what's stored - verified with a repository test and a
  mutation check that removing that condition breaks it.
- **Service names are case-sensitive** (`MONITOR_MONITORED_SERVICES`), unlike the filesystem-type
  exclusion list: systemd unit names can be mixed case, so the config parser only trims whitespace
  and never lowercases them.
- **The frontend polls; it doesn't push.** Each section fetches on a plain interval
  (`frontend/src/config.js`), matching how the backend itself already works (a background
  scheduler on a fixed interval, not push notifications) and how real tools like Grafana
  poll their datasources by default. Simpler to reason about and explain than SSE/WebSockets,
  with no new transport layer for a backend that's already stable.
- **The frontend never recomputes alert thresholds.** Stat cards and the disk/service lists
  color themselves by cross-referencing the live `/api/alerts` response
  (`frontend/src/utils/alerts.js`), not by re-implementing the Phase 4 threshold logic in
  JavaScript - one source of truth for "what's wrong".
- **A panel never blanks out on a failed poll**; the last successful reading stays on
  screen with a small inline notice, since a transient 503 during backend startup
  shouldn't flash the whole dashboard to an error state.
- **Service checking runs every cycle independent of the alert engine** - `/api/services` needs
  current data even if alerting were ever disabled. (This was a real bug caught during Phase 5
  testing: an early version only checked services inside the `if alert_engine is not None` branch,
  which a mutation test and a dedicated regression test both now guard against.)
- **Fail-fast snapshots**: if any collector fails, `CollectionError` names it; the caller decides
  whether to log, retry or skip the cycle.
