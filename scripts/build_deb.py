#!/usr/bin/env python3
"""Build a .deb with the dashboard and the current Python's production dependencies.

Run with the backend environment: backend/.venv/bin/python scripts/build_deb.py
Recipients need neither pip nor Node. Build once per Ubuntu release/architecture,
since compiled Python extensions must match the target Python ABI and libc.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
except ImportError:
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent


def production_distributions(requirements_file: Path) -> list[metadata.Distribution]:
    """Resolve only installed production requirements, including requested extras."""
    pending = [
        Requirement(line.strip())
        for line in requirements_file.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    resolved: dict[str, metadata.Distribution] = {}
    extras: dict[str, set[str]] = {}
    environment = default_environment()
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        distribution = metadata.distribution(name)
        if not requirement.specifier.contains(distribution.version, prereleases=True):
            raise RuntimeError(
                f"Installed {name}=={distribution.version} does not satisfy {requirement}"
            )
        requested = set(requirement.extras) | {""}
        previous = extras.get(name, set())
        if name in resolved and requested <= previous:
            continue
        extras[name] = previous | requested
        resolved[name] = distribution
        for raw in distribution.requires or []:
            dependency = Requirement(raw)
            if dependency.marker is None or any(
                dependency.marker.evaluate({**environment, "extra": extra})
                for extra in extras[name]
            ):
                pending.append(dependency)
    return [resolved[name] for name in sorted(resolved)]


def bundle_dependencies(distributions: list[metadata.Distribution], destination: Path) -> None:
    for distribution in distributions:
        if distribution.files is None:
            raise RuntimeError(
                f"No file manifest for {distribution.metadata['Name']}; use a regular pip install"
            )
        for relative in distribution.files:
            # Wheel RECORDs may include console scripts outside site-packages.
            # Our entry point calls Python directly, so those scripts are unnecessary.
            if relative.is_absolute() or ".." in relative.parts:
                continue
            if "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pyo"}:
                continue
            source = distribution.locate_file(relative)
            if not source.is_file():
                raise RuntimeError(f"Missing installed dependency file: {source}")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o644)


def application_version() -> str:
    for statement in ast.parse((ROOT / "backend/app/__init__.py").read_text()).body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in statement.targets
        ):
            return str(ast.literal_eval(statement.value))
    raise RuntimeError("Application version not found")


def copy_file(stage: Path, source: Path, target: str, mode: int = 0o644) -> None:
    destination = stage / target.lstrip("/")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(mode)


def build(output: Path, skip_frontend_build: bool) -> Path:
    if sys.platform != "linux":
        raise RuntimeError("Build the Linux package on the target Ubuntu/Linux release")
    if not shutil.which("dpkg-deb"):
        raise RuntimeError("dpkg-deb is required (install the dpkg package)")
    distributions = production_distributions(ROOT / "backend/requirements.txt")
    if not skip_frontend_build:
        if not (ROOT / "frontend/node_modules").is_dir():
            subprocess.run(["npm", "ci"], cwd=ROOT / "frontend", check=True)
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)
    dashboard = ROOT / "frontend/dist"
    if not all(
        (dashboard / name).is_file() for name in ("index.html", "sw.js", "manifest.webmanifest")
    ):
        raise RuntimeError("Missing production dashboard/PWA. Run npm run build in frontend first")

    release = platform.freedesktop_os_release()
    target = release["ID"] + release["VERSION_ID"]
    architecture = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    python_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    next_minor = f"{sys.version_info.major}.{sys.version_info.minor + 1}"
    libc_name, libc_version = platform.libc_ver()
    if libc_name != "glibc" or not libc_version:
        raise RuntimeError("The .deb builder requires a glibc-based Linux distribution")
    version = f"{application_version()}-1+{target}"
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / f"linux-monitor_{version}_{architecture}.deb"

    with tempfile.TemporaryDirectory(prefix="linux-monitor-deb-") as temporary:
        stage = Path(temporary) / "root"
        private = stage / "usr/lib/linux-monitor"
        private.mkdir(parents=True)
        shutil.copytree(
            ROOT / "backend/app",
            private / "backend/app",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(ROOT / "backend/config", private / "backend/config")
        shutil.copytree(dashboard, stage / "usr/share/linux-monitor/dashboard")
        bundle_dependencies(distributions, private / "vendor")
        files = {
            "server.py": ("usr/lib/linux-monitor/server.py", 0o644),
            "native.py": ("usr/lib/linux-monitor/native.py", 0o644),
            "launcher.py": ("usr/bin/linux-monitor", 0o755),
            "linux-monitor.desktop": ("usr/share/applications/linux-monitor.desktop", 0o644),
            "linux-monitor.service": ("usr/lib/systemd/system/linux-monitor.service", 0o644),
            "monitor.env": ("etc/linux-monitor/monitor.env", 0o644),
            "README.md": ("usr/share/doc/linux-monitor/README.md", 0o644),
        }
        for source, (destination, mode) in files.items():
            copy_file(stage, ROOT / "packaging" / source, destination, mode)
        copy_file(
            stage,
            ROOT / "frontend/public/icons/icon-512.png",
            "usr/share/icons/hicolor/512x512/apps/linux-monitor.png",
        )
        runtime = {
            "target": target,
            "architecture": architecture,
            "python": python_minor,
            "libc": libc_version,
            "dependencies": [
                {"name": d.metadata["Name"], "version": d.version} for d in distributions
            ],
        }
        (stage / "usr/share/doc/linux-monitor/runtime-dependencies.json").write_text(
            json.dumps(runtime, indent=2) + "\n"
        )
        for directory, _, filenames in os.walk(stage):
            Path(directory).chmod(0o755)
            for filename in filenames:
                file = Path(directory) / filename
                if file.name != "linux-monitor":
                    file.chmod(0o644)
        size = sum(file.stat().st_size for file in stage.rglob("*") if file.is_file()) // 1024 + 1
        control = stage / "DEBIAN"
        control.mkdir()
        (control / "control").write_text(
            f"Package: linux-monitor\nVersion: {version}\nSection: admin\nPriority: optional\n"
            f"Architecture: {architecture}\nInstalled-Size: {size}\n"
            "Maintainer: Linux Monitor contributors <aakarshansharmadeep@gmail.com>\n"
            f"Depends: python3 (>= {python_minor}), python3 (<< {next_minor}), "
            f"libc6 (>= {libc_version}), libgcc-s1, libstdc++6, adduser, "
            "systemd, init-system-helpers (>= 1.60), python3-tk\n"
            "Recommends: xdg-utils\n"
            "Description: Local Linux monitoring dashboard and background service\n"
            " Includes the built dashboard and private Python dependencies.\n"
            " Collects host metrics locally with native desktop and web interfaces.\n"
        )
        (control / "conffiles").write_text("/etc/linux-monitor/monitor.env\n")
        for script in ("postinst", "prerm", "postrm"):
            copy_file(stage, ROOT / "packaging" / script, f"DEBIAN/{script}", 0o755)
        subprocess.run(
            ["dpkg-deb", "--root-owner-group", "--build", str(stage), str(artifact)], check=True
        )
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--skip-frontend-build", action="store_true", help="Use an existing frontend/dist build"
    )
    args = parser.parse_args()
    try:
        artifact = build(args.output_dir.resolve(), args.skip_frontend_build)
    except (RuntimeError, metadata.PackageNotFoundError, subprocess.CalledProcessError) as error:
        print(f"Package build failed: {error}", file=sys.stderr)
        return 1
    print(f"Built: {artifact}")
    print(f"Install on the matching Ubuntu/Linux release: sudo apt install ./{artifact.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
