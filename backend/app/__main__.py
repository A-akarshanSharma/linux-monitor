"""Start the API server: ``python -m app``.

Host and port come from configuration (MONITOR_BACKEND_HOST / MONITOR_BACKEND_PORT).
"""

from __future__ import annotations

import sys

import uvicorn
from pydantic import ValidationError

from app.config import get_settings
from app.logging_config import setup_logging


def main() -> int:
    try:
        settings = get_settings()
    except ValidationError as exc:
        print(f"Invalid configuration:\n{exc}", file=sys.stderr)
        return 2

    setup_logging(settings.log_level, settings.log_format)
    # log_config=None: keep our logging setup instead of uvicorn's default one.
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.backend_host,
        port=settings.backend_port,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
