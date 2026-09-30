# Frontend - Server Monitor Dashboard

React + Vite dashboard for the Linux Server Monitoring & Alerting Platform. See the
[repository root README](../README.md) for the full project.

## Run

```bash
npm install
npm run dev       # http://localhost:5173, proxies /api/* to the backend
```

Requires the backend running (`cd ../backend && python -m app`, default port 8000).
`npm run dev` proxies every `/api/...` request server-side to the backend, so the
browser only ever talks to one origin and the backend needs no CORS configuration.
If your backend runs on a different port, copy `.env.example` to `.env.local` and
set `VITE_BACKEND_URL`.

```bash
npm run build      # production build -> dist/
npm run preview    # serve the built dist/ locally, same proxy behaviour as dev
npm run lint        # oxlint
```

## Structure

```
src/
├── api/client.js         # fetch wrapper matching the backend's {"error": {...}} envelope
├── config.js              # poll intervals, history window, process list size
├── hooks/                  # usePolling (generic) + one hook per backend endpoint
├── utils/
│   ├── format.js          # bytes, percent, uptime, relative/clock time
│   ├── statusColor.js      # normal/warning/critical/unknown -> CSS colors
│   └── alerts.js           # cross-references a metric/disk against active alerts
└── components/
    ├── layout/             # Header, Panel (shared section shell), StatusDot
    ├── metrics/             # stat cards, disk list, CPU/memory/network charts
    ├── processes/           # top-processes table (by CPU / by memory)
    ├── services/            # service health list
    └── alerts/              # active + recently resolved alerts feed
```

## Design notes

- **Every color communicates state.** The green/amber/red/grey status palette matches
  what `systemctl` and `journalctl` already print in a terminal - not picked for looks.
  The teal accent is reserved for the "live" indicator and chart lines; it never means
  "problem" or "fine".
- **Numbers are monospace (IBM Plex Mono); everything else is IBM Plex Sans.** This is
  functional, not decorative - fixed-width digits keep a column of percentages or PIDs
  aligned, the way `htop` or `top` read.
- **No cards-with-shadows.** Structure comes from 1px borders and background-tone steps
  (`--bg-base` / `--bg-panel` / `--bg-panel-raised`), closer to a terminal UI panel than
  a SaaS dashboard kit.
- **Alert severity is cross-referenced from the backend, not recomputed.** CPU/memory/disk
  stat cards and rows call `severityFor(alerts, ruleKey, target)` against the live
  `/api/alerts` data rather than re-implementing threshold logic in the frontend - the
  alert engine (Phase 4 of the backend) stays the single source of truth for "what's wrong".
- **A panel never blanks out on a failed poll.** `usePolling` keeps the last successful
  data on screen and surfaces a small inline notice instead, since a transient 503 during
  backend startup shouldn't flash the whole dashboard to an error state.
