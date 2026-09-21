import json
import logging
import sys

import pytest

from app.logging_config import JsonFormatter, setup_logging


def _record(**kwargs: object) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


def test_json_formatter_includes_core_fields_and_extras() -> None:
    line = JsonFormatter().format(_record(mountpoint="/var", attempt=2))
    data = json.loads(line)

    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert data["logger"] == "app.test"
    assert data["mountpoint"] == "/var"
    assert data["attempt"] == 2
    assert data["timestamp"].endswith("+00:00")


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record()
        record.exc_info = sys.exc_info()

    data = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in data["exception"]


def test_setup_logging_is_idempotent_and_writes_json(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging("INFO", "json")
    setup_logging("INFO", "json")  # must not duplicate handlers

    logging.getLogger("app.test").info("started", extra={"port": 8000})

    lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(lines) == 1
    assert json.loads(lines[0])["port"] == 8000


def test_setup_logging_keeps_handlers_it_did_not_install() -> None:
    foreign = logging.NullHandler()
    root = logging.getLogger()
    root.addHandler(foreign)

    setup_logging("INFO", "json")

    assert foreign in root.handlers


def test_uvicorn_loggers_are_routed_through_the_root_handler() -> None:
    uvicorn_logger = logging.getLogger("uvicorn.error")
    uvicorn_logger.addHandler(logging.NullHandler())
    uvicorn_logger.propagate = False

    setup_logging("INFO", "json")

    assert uvicorn_logger.handlers == []
    assert uvicorn_logger.propagate is True


def test_json_formatter_drops_uvicorn_color_message() -> None:
    data = json.loads(JsonFormatter().format(_record(color_message="\x1b[36mhi\x1b[0m")))

    assert "color_message" not in data
