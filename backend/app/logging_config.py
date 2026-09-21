"""Structured logging.

Uses only the standard library. In ``json`` mode every log line is a single JSON
object, with any ``extra={...}`` fields merged in, so logs are easy to grep,
ship to a log aggregator, or read with ``jq``.

Logs go to stderr so that CLI tools can keep stdout clean for their output.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

# Attributes present on every LogRecord; anything else came from `extra=`.
_RESERVED_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys() | {"message", "asctime"}
)

# `extra` keys added by other libraries that are just noise in JSON output
# (uvicorn attaches an ANSI-coloured copy of each message as `color_message`).
_IGNORED_EXTRAS = frozenset({"color_message"})

# Marks the handler installed by setup_logging(), so repeated calls replace only our own.
_HANDLER_MARKER = "_linux_monitor_handler"

_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS | _IGNORED_EXTRAS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Configure the root logger. Safe to call more than once.

    Only the handler installed by a previous call is replaced; handlers added by
    other code (test runners, embedding applications) are left alone. Uvicorn's
    loggers are routed through the root handler so server and application logs
    share one format.
    """
    handler = logging.StreamHandler(sys.stderr)
    setattr(handler, _HANDLER_MARKER, True)
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARKER, False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
