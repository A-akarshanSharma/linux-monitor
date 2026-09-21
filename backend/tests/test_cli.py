import json

import pytest

from app.collectors import __main__ as cli
from app.collectors import snapshot


def test_cli_prints_valid_json_snapshot(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["--compact", "--sample-seconds", "0"])

    captured = capsys.readouterr()
    assert exit_code == 0
    data = json.loads(captured.out)  # stdout must contain *only* the JSON document
    assert {"system", "cpu", "memory", "disks", "network", "processes"} <= data.keys()


def test_cli_returns_1_and_logs_when_a_collector_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken() -> None:
        raise OSError("boom")

    monkeypatch.setattr(snapshot, "collect_cpu", broken)

    exit_code = cli.main(["--sample-seconds", "0"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    error_log = json.loads(captured.err.strip().splitlines()[-1])
    assert error_log["message"] == "metric_collection_failed"
    assert error_log["collector"] == "cpu"


def test_cli_rejects_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MONITOR_POLLING_INTERVAL_SECONDS", "0")

    assert cli.main([]) == 2
    assert "Invalid configuration" in capsys.readouterr().err
