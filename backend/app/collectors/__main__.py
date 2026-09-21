"""Command-line entry point: ``python -m app.collectors``.

Prints a full metrics snapshot as JSON on stdout (logs go to stderr).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from pydantic import ValidationError

from app.collectors.snapshot import CollectionError, SnapshotCollector
from app.config import get_settings
from app.logging_config import setup_logging

logger = logging.getLogger("app.collectors.cli")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.collectors",
        description="Collect and print a system metrics snapshot as JSON.",
    )
    parser.add_argument(
        "--sample-seconds",
        type=float,
        default=1.0,
        help="Wait between the baseline and the reading so CPU %% and network rates "
        "are meaningful (default: 1.0).",
    )
    parser.add_argument("--compact", action="store_true", help="Print single-line JSON.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep printing a snapshot every MONITOR_POLLING_INTERVAL_SECONDS until Ctrl+C.",
    )
    args = parser.parse_args(argv)

    try:
        settings = get_settings()
    except ValidationError as exc:
        print(f"Invalid configuration:\n{exc}", file=sys.stderr)
        return 2

    setup_logging(settings.log_level, settings.log_format)
    collector = SnapshotCollector(settings)
    collector.prime()

    delay = args.sample_seconds
    try:
        while True:
            time.sleep(delay)
            snapshot = collector.collect()
            print(snapshot.model_dump_json(indent=None if args.compact else 2), flush=True)
            if not args.watch:
                return 0
            delay = settings.polling_interval_seconds
    except CollectionError as exc:
        logger.error(
            "metric_collection_failed", extra={"collector": exc.collector, "error": str(exc)}
        )
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
