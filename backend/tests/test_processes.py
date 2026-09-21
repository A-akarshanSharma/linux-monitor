from types import SimpleNamespace

import pytest

from app.collectors import processes


def _proc(pid: int, name: str, cpu: float, rss: int, status: str = "sleeping", **overrides):
    info = {
        "pid": pid,
        "name": name,
        "username": "root",
        "status": status,
        "cpu_percent": cpu,
        "memory_percent": rss / 1_000_000,
        "memory_info": SimpleNamespace(rss=rss),
    }
    info.update(overrides)
    return SimpleNamespace(info=info)


@pytest.fixture
def fake_processes(monkeypatch: pytest.MonkeyPatch):
    def install(procs: list[SimpleNamespace]) -> list[list[str]]:
        requested: list[list[str]] = []

        def fake_iter(attrs: list[str]):
            requested.append(list(attrs))
            return iter(procs)

        monkeypatch.setattr(processes.psutil, "process_iter", fake_iter)
        return requested

    return install


def test_top_processes_are_sorted_and_limited(fake_processes) -> None:
    fake_processes(
        [
            _proc(1, "init", 0.1, 1_000),
            _proc(2, "db", 50.0, 900_000),
            _proc(3, "web", 75.5, 200_000),
            _proc(4, "cron", 0.0, 5_000),
        ]
    )

    result = processes.collect_processes(top_n=2)

    assert result.total_count == 4
    assert [p.name for p in result.top_by_cpu] == ["web", "db"]
    assert [p.name for p in result.top_by_memory] == ["db", "web"]


def test_running_count_only_counts_running_state(fake_processes) -> None:
    fake_processes(
        [
            _proc(1, "a", 1.0, 10, status="running"),
            _proc(2, "b", 1.0, 10, status="sleeping"),
            _proc(3, "c", 1.0, 10, status="running"),
            _proc(4, "d", 1.0, 10, status="zombie"),
        ]
    )

    result = processes.collect_processes()

    assert result.total_count == 4
    assert result.running_count == 2


def test_access_denied_fields_fall_back_to_safe_values(fake_processes) -> None:
    fake_processes(
        [
            _proc(
                7,
                None,
                None,
                0,
                username=None,
                status=None,
                cpu_percent=None,
                memory_percent=None,
                memory_info=None,
            )
        ]
    )

    result = processes.collect_processes()
    proc = result.top_by_cpu[0]

    assert proc.name == "unknown"
    assert proc.username is None
    assert proc.status == "unknown"
    assert proc.cpu_percent == 0.0
    assert proc.memory_rss_bytes == 0


def test_fewer_processes_than_top_n(fake_processes) -> None:
    fake_processes([_proc(1, "only", 1.0, 10)])

    assert len(processes.collect_processes(top_n=10).top_by_cpu) == 1


def test_command_lines_are_never_collected(fake_processes) -> None:
    """Command lines often contain secrets passed as arguments."""
    requested = fake_processes([_proc(1, "a", 1.0, 10)])

    processes.collect_processes()

    assert "cmdline" not in requested[0]
    assert "environ" not in requested[0]


def test_prime_iterates_processes_once(fake_processes) -> None:
    requested = fake_processes([_proc(1, "a", 1.0, 10)])

    processes.prime_process_cpu()

    assert requested == [["cpu_percent"]]
