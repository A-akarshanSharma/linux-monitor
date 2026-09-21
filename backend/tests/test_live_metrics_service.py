import threading
import time

import pytest

from app.collectors import CollectionError
from app.services import live_metrics
from app.services.live_metrics import LiveMetricsService
from tests.factories import make_snapshot


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeSource:
    def __init__(self) -> None:
        self.primed = 0
        self.collect_calls: list[int | None] = []
        self.error: Exception | None = None

    def prime(self) -> None:
        self.primed += 1

    def collect(self, top_processes: int | None = None):
        self.collect_calls.append(top_processes)
        if self.error:
            raise self.error
        return make_snapshot()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def source() -> FakeSource:
    return FakeSource()


@pytest.fixture
def service(source: FakeSource, clock: FakeClock) -> LiveMetricsService:
    return LiveMetricsService(source, min_interval_seconds=1.0, clock=clock, sleep=clock.sleep)


def test_first_reading_waits_for_the_measurement_window(
    service: LiveMetricsService, clock: FakeClock, source: FakeSource
) -> None:
    service.prime()
    clock.now += 0.25  # request arrives 250 ms after start-up

    service.get_snapshot()

    assert clock.sleeps == [pytest.approx(0.75)]
    assert len(source.collect_calls) == 1


def test_no_wait_when_window_has_already_elapsed(
    service: LiveMetricsService, clock: FakeClock
) -> None:
    service.prime()
    clock.now += 30

    service.get_snapshot()

    assert clock.sleeps == []


def test_snapshot_is_reused_within_min_interval(
    service: LiveMetricsService, clock: FakeClock, source: FakeSource
) -> None:
    service.prime()
    clock.now += 5
    first = service.get_snapshot()

    clock.now += 0.5
    second = service.get_snapshot()

    assert second is first
    assert len(source.collect_calls) == 1


def test_snapshot_is_refreshed_after_min_interval(
    service: LiveMetricsService, clock: FakeClock, source: FakeSource
) -> None:
    service.prime()
    clock.now += 5
    service.get_snapshot()

    clock.now += 1.5
    service.get_snapshot()

    assert len(source.collect_calls) == 2


def test_unprimed_service_primes_itself(service: LiveMetricsService, source: FakeSource) -> None:
    service.get_snapshot()

    assert source.primed == 1


def test_collects_the_maximum_process_list(source: FakeSource, clock: FakeClock) -> None:
    service = LiveMetricsService(
        source, max_processes=42, clock=clock, sleep=clock.sleep, min_interval_seconds=1.0
    )

    service.get_snapshot()

    assert source.collect_calls == [42]


def test_failed_collection_propagates_and_is_not_cached(
    service: LiveMetricsService, clock: FakeClock, source: FakeSource
) -> None:
    service.prime()
    clock.now += 5
    source.error = CollectionError("cpu", OSError("boom"))

    with pytest.raises(CollectionError):
        service.get_snapshot()
    with pytest.raises(CollectionError):  # retried immediately, not stuck on a cached failure
        service.get_snapshot()
    assert len(source.collect_calls) == 2

    source.error = None
    assert service.get_snapshot() is not None


def test_concurrent_requests_trigger_a_single_collection(
    source: FakeSource, clock: FakeClock
) -> None:
    original = source.collect

    def slow_collect(top_processes: int | None = None):
        time.sleep(0.05)  # widen the race window
        return original(top_processes)

    source.collect = slow_collect  # type: ignore[method-assign]
    service = LiveMetricsService(source, clock=clock, sleep=clock.sleep, min_interval_seconds=1.0)
    service.prime()
    clock.now += 5
    results: list[object] = []

    def worker() -> None:
        results.append(service.get_snapshot())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    assert len({id(r) for r in results}) == 1  # everyone got the same snapshot
    assert len(source.collect_calls) == 1


def test_system_info_failure_is_wrapped(
    monkeypatch: pytest.MonkeyPatch, service: LiveMetricsService
) -> None:
    def broken() -> None:
        raise OSError("no os-release")

    monkeypatch.setattr(live_metrics, "collect_system_info", broken)

    with pytest.raises(CollectionError) as exc_info:
        service.get_system_info()

    assert exc_info.value.collector == "system_info"
