# Linux Server Monitor package

The `.deb` contains a native Tk desktop window, the built React/PWA dashboard, the
Python application and its production dependencies, a systemd service, and an app-menu launcher. Recipients
do not need Node, npm, pip, nginx, Docker, or the source repository. APT installs
the matching system Python and other OS dependencies when necessary.

## Install and open

The v0.6.0 build targets are Ubuntu 24.04 amd64 (Python 3.12, glibc 2.39 or newer)
and Ubuntu 26.04 amd64 (Python 3.14, glibc 2.43 or newer). The package control
metadata pins these Python and glibc minimums. These are separate builds; choose
the artifact whose filename matches your Ubuntu release. ARM and other Ubuntu
releases are not covered by these targets.

### Verification status

| Target | v0.6.0 package | Prior project verification (reported; not a committed CI artifact) | Current audit |
| --- | --- | --- | --- |
| Ubuntu 24.04 amd64 | Fresh v0.6.0 build; Python 3.12 / glibc >= 2.39 | Prior project work reported fresh install, upgrade, package smoke, and native UI smoke as passing. | `check_deb.py` and `check_deb_install.sh` lifecycle test passed in Ubuntu 24.04; native GUI automation was unavailable because `xvfb-run` and `xauth` are not installed. |
| Ubuntu 26.04 amd64 | Fresh v0.6.0 build; Python 3.14 / glibc >= 2.43 | Prior project work reported install/upgrade and native UI checks; the project maintainer also reports Ubuntu Desktop use and the resource observations. | `check_deb.py` and `check_deb_install.sh` lifecycle test passed in Ubuntu 26.04; native GUI automation was unavailable because `xvfb-run` and `xauth` are not installed. |
| Other Ubuntu releases / ARM | No supported v0.6.0 artifact recorded | Not verified. | Not tested. |

The `.deb` files in `dist/` are local build artifacts and are ignored by Git. The
current review builds and their checksum file are under `dist/review-v0.6.0/`;
attach the two package files and `SHA256SUMS` from its `release-assets/` directory
to the GitHub release. Repeat the matching install checks if you rebuild either
artifact. A successful build or matching dependency metadata alone does not verify
installation on every compatible host.

Download the package for your Ubuntu release and CPU architecture, open a terminal
in the download folder, and run:

```bash
sudo apt install ./linux-monitor_<version>_<architecture>.deb
```

Replace the placeholder filename with the downloaded file. Installation requires
administrator permission and may need internet access for OS dependencies. The
package does not download Python dependencies or compile the frontend at install time.

Open **Linux Server Monitor** in your app menu, or run `linux-monitor`. On an Ubuntu
desktop this opens a native window with live usage, disk information, 30-minute
charts, processes sorted by CPU or memory, services, and alerts. It uses Python/Tk
widgets and no browser engine. APT installs `python3-tk` automatically.

The background `linux-monitor` service still collects metrics and stores history.
Closing the native window leaves collection running. The window refreshes every
10 seconds; requests pause while minimized. HTTP failures retain previous readings
and display a warning until the connection recovers.

The web dashboard remains available at <http://localhost:8765>. Use
`linux-monitor --browser` to open it, or install it as a PWA through Chrome/Edge.
Using the native window avoids starting Firefox/Chrome; the PWA still uses a browser.

```bash
systemctl status linux-monitor
linux-monitor --native
linux-monitor --browser
linux-monitor --url
```

The package runs as a dedicated `linux-monitor` system user, binds to localhost,
and stores history in `/var/lib/linux-monitor/monitor.db`. Process fields that
Linux denies this user permission to read may be unavailable. It monitors its own
service by default. Edit `/etc/linux-monitor/monitor.env` to change the port,
thresholds, or service names, then restart with `sudo systemctl restart linux-monitor`.
The launcher uses the configured port. The packaged defaults are independent of
any repository `.env` file or development services on ports 8000/8080.

## Windows through WSL

Install the package inside the matching Ubuntu distribution, with systemd enabled.
With WSLg/X11 available (`DISPLAY` set), `linux-monitor` opens the native window.
Without a graphical Linux display, it opens your Windows default browser instead.
Use `linux-monitor --browser` to explicitly choose the Windows browser, or open
<http://localhost:8765> manually. You can install that page as an app in Windows Edge/Chrome.

For a Windows desktop shortcut that starts WSL and opens the dashboard, create a
shortcut with this target (replace `Ubuntu` with the name shown by `wsl -l -q`):

```text
wsl.exe -d Ubuntu --exec linux-monitor
```

The launcher waits briefly for the service to start. The package enables its
Linux service; it does not configure Windows to start WSL at login. Keep WSL
running for live metrics. Systemd services alone do not keep WSL alive, as
documented by [Microsoft](https://learn.microsoft.com/en-us/windows/wsl/systemd).
This package monitors WSL/Linux, not native Windows.

## Update and remove

Install a newer matching `.deb` using the same `sudo apt install ./...deb` command.
Configuration edits are preserved by dpkg; history remains in `/var/lib/linux-monitor`.
When a PWA update is downloaded, close all dashboard app windows/tabs and reopen
to activate the new cached shell. The native window has no service-worker cache;
close it and relaunch after installing an updated package.

```bash
sudo apt remove linux-monitor
# Also remove the package's configuration:
sudo apt purge linux-monitor
```

History is deliberately retained, even on purge. The service account is retained
to preserve ownership of that history. Remove saved data separately if desired.
Uninstall any browser-installed PWA through the browser.

## Build a package (maintainers only)

Build on the Ubuntu release and architecture you intend to support, with the
backend's production dependencies installed in its virtual environment and Node
available for the frontend build:

```bash
backend/.venv/bin/python scripts/build_deb.py
```

Alternatively, build the frontend once and use disposable Ubuntu containers to
produce packages with each release's Python and libc:

```bash
cd frontend && npm ci && npm run build
cd ..
scripts/build_deb_container.sh 24.04
scripts/build_deb_container.sh 26.04
```

The container builder requires Docker and internet access. It mounts the source
read-only and writes only the resulting package to `dist/`.

The output is `dist/linux-monitor_<version>_<architecture>.deb`. The builder
includes only production dependencies, their metadata/license files, and a
`runtime-dependencies.json` inventory. It excludes development tools, virtual
environment activation scripts, repository secrets, databases, and caches.

The package declares the build Python minor version and libc requirements. A
package built on Ubuntu 26.04 with Python 3.14 is not an Ubuntu 24.04/Python 3.12
package. Build a separate artifact on each supported target; do not rename an
artifact to claim compatibility. No older-Ubuntu or ARM build is implied by an
amd64 Ubuntu 26.04 artifact.

Use `--skip-frontend-build` to package an already-built dashboard, and
`--output-dir PATH` to change the artifact directory. The builder uses installed
dependency versions and records them in the package; use a pinned build environment
when producing repeatable releases.

To check an artifact without installing it on your host:

```bash
python3 scripts/check_deb.py dist/linux-monitor_<version>_<architecture>.deb
# Fresh installation, reinstall, version upgrade, remove, and purge:
scripts/check_deb_install.sh dist/linux-monitor_<version>_<architecture>.deb
```

The extraction check uses isolated system Python and a temporary local server and
database. The container check needs Docker and internet access for Ubuntu's OS
packages; its only checkout mount is the `.deb`, read-only. It verifies service
enablement and runs the installed server as its dedicated user. It does not boot
systemd as container PID 1. Set `MONITOR_PACKAGE_TEST_IMAGE` to the matching image
when testing a package built for a different release.
