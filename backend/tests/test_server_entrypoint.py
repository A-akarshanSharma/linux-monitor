import pytest

from app import __main__ as entrypoint
from app.config import Settings


def test_main_starts_uvicorn_with_configured_host_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MONITOR_BACKEND_HOST", "0.0.0.0")
    monkeypatch.setenv("MONITOR_BACKEND_PORT", "9100")
    captured: dict[str, object] = {}
    monkeypatch.setattr(entrypoint.uvicorn, "run", lambda *a, **kw: captured.update(kw, args=a))

    assert entrypoint.main() == 0

    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9100
    assert captured["factory"] is True
    assert captured["args"] == ("app.main:create_app",)


def test_main_rejects_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MONITOR_BACKEND_PORT", "70000")

    assert entrypoint.main() == 2
    assert "Invalid configuration" in capsys.readouterr().err


def test_port_and_host_defaults(settings: Settings) -> None:
    assert settings.backend_host == "127.0.0.1"
    assert settings.backend_port == 8000
