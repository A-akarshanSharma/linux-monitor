# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Metrics collected from inside this container describe the CONTAINER, not the
# host machine it's running on - different hostname, network namespace, and
# (unless docker-compose.host.yml's overrides are used) a different /proc view
# of CPU/memory. See the root README's Docker caveats and host-metrics overlay.
WORKDIR /app

# A dedicated non-root user: nothing this process does needs root, and running
# as one is an unnecessary risk for a network-facing service.
RUN groupadd --system app && useradd --system --gid app --home /app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config

# SQLite lives here; docker-compose.yml mounts a named volume at this path so
# history and alert state survive a container restart.
RUN mkdir -p /app/data && chown -R app:app /app

USER app

ENV MONITOR_DATABASE_PATH=data/monitor.db \
    MONITOR_BACKEND_HOST=0.0.0.0 \
    MONITOR_BACKEND_PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)"]

CMD ["python", "-m", "app"]
