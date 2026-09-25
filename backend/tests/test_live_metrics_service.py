import pytest

from app.collectors import CollectionError
from app.services import live_metrics
from app.services.live_metrics import LiveMetricsService
from tests.factories import make_snapshot


def test_get_snapshot_returns_whatever_the_source_provides() -> None:
    snapshot = make_snapshot()
    service = LiveMetricsService(lambda: snapshot)

    assert service.get_snapshot() is snapshot


def test_get_snapshot_propagates_source_errors() -> None:
    error = CollectionError("scheduler", RuntimeError("no metrics collected yet"))

    def source():
        raise error

    service = LiveMetricsService(source)

    with pytest.raises(CollectionError) as exc_info:
        service.get_snapshot()
    assert exc_info.value is error


def test_get_system_info_is_always_collected_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_collect():
        nonlocal calls
        calls += 1
        return make_snapshot().system

    monkeypatch.setattr(live_metrics, "collect_system_info", fake_collect)
    service = LiveMetricsService(lambda: make_snapshot())

    service.get_system_info()
    service.get_system_info()

    assert calls == 2  # never cached, unlike get_snapshot()


def test_get_system_info_wraps_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken():
        raise OSError("no os-release")

    monkeypatch.setattr(live_metrics, "collect_system_info", broken)
    service = LiveMetricsService(lambda: make_snapshot())

    with pytest.raises(CollectionError) as exc_info:
        service.get_system_info()

    assert exc_info.value.collector == "system_info"
