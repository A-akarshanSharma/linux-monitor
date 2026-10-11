# Browser Dashboard and PWA

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
npm test           # build + polling, formatting, and app-shell checks
npm run test:pwa    # build + app-shell caching checks
```

## Desktop installation and caching

Run a production build through Docker, host nginx, or `npm run preview`, then open
the local URL in Chrome or Edge. Use **Install app** when it appears in the header,
or the browser's install option. HTTPS is required except on localhost/127.0.0.1.
See the root README for the always-on systemd + nginx setup.

`public/manifest.webmanifest` defines the standalone app and its icons.
`pwa/plugin.js` generates `dist/sw.js` with a cache version derived from the built
shell and public files. It precaches the shell, serves it immediately from that
cache, and leaves all `/api` and third-party requests to the network. Live API
requests use `cache: 'no-store'`. External Google Fonts are optional and fall back
to system fonts offline. There is no persistent metrics cache or push messaging.

New workers wait until all dashboard windows/tabs close before activating, so an
open window never mixes builds. Open online to download a deployed update, then
close all app windows/tabs and reopen. A worker is only registered in production;
use a separate port for Vite dev if you installed a production app on the same origin,
or unregister the worker and clear site data in browser developer tools first.

Icons reuse the existing favicon's colors and circles. To regenerate the PNG files:

```bash
python3 pwa/generate-icons.py
```

## Resource use

The production dashboard uses static status dots, disables chart animations, and
reuses locale date/time formatters. Charts are memoized so updates to current
readings or alerts do not redraw unchanged history. Only freshness labels tick
once per second, rather than the entire panel.

When the browser reports the page hidden (for example, a background tab or minimized
window), API polling and freshness clocks pause. Pending requests are aborted and
their results ignored. Returning to the page immediately refreshes all queries.
Slow requests cannot overlap within a query. The backend continues collecting
history even with no dashboard open.

The app still runs inside a browser: installing a PWA or the `.deb` does not remove
the browser's own memory cost. In Firefox, use `about:processes` to distinguish
the dashboard's content process from browser, graphics, and extension processes;
see [Mozilla's Process Manager guide](https://support.mozilla.org/en-US/kb/task-manager-tabs-or-extensions-are-slowing-firefox).

The header in new builds displays the frontend release baked into the bundle.
Hover over it to see the backend release from `/api/health`; differing versions
show "update pending". This distinguishes the displayed frontend from an upgraded
backend. The first 0.5.1 installer predates this label.

For high resource usage in a VM, first check `dpkg-query -W linux-monitor` and
open `/api/health` to confirm the installed and running backend releases. Then
compare Firefox with the dashboard open against a single `about:blank` tab,
closing the dashboard tab and waiting 30 seconds before reading CPU again. Keep
the monitoring backend running for both measurements. Check `about:processes`
for the browser/content/graphics breakdown. If necessary, repeat both cases in
a fresh browser session to reduce the effect of retained allocations. Record
`gnome-shell` usage as well: desktop rendering contributes to total VM CPU usage.

### Local measurements (0.5.1, 2026-10-07)

Fresh headless browser profiles, production builds, 1366×900 viewport, mocked API
responses with 180 history samples (30 minutes at 10-second collection intervals),
normal polling intervals, and a 60-second observation after loading. External fonts
were blocked. CPU is the combined browser process CPU time divided by wall time,
with 100% meaning one core. Memory is summed Linux PSS at the end of the observation
to count shared pages proportionally. These measurements include the browser runtime.

| Browser | Before CPU | 0.5.1 CPU | Before memory (MiB PSS) | 0.5.1 memory (MiB PSS) |
| --- | ---: | ---: | ---: | ---: |
| Chrome for Testing 153 (Playwright build 1243) | 37.0% | 2.5% | 405.8 | 390.4 |
| Firefox 155 (Playwright build 1543) | 41.3% | 3.5% | 478.1 | 417.1 |

Firefox summed RSS was 783.3 → 725.8 MiB; RSS totals can count shared pages more
than once. A separate real-backend run with default 10-second collection and 34
API requests over 60 seconds measured 85.2 MiB RSS and 0.7% of one core. The backend
database was initially empty. These are short local measurements, not a VirtualBox
reproduction, a long-running leak test, or a guarantee of resource use on other systems.

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
  backend alert engine stays the single source of truth for "what's wrong".
- **A panel never blanks out on a failed poll.** `usePolling` keeps the last successful
  data on screen and surfaces a small inline notice instead, since a transient 503 during
  backend startup shouldn't flash the whole dashboard to an error state.
