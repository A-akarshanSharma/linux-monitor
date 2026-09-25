from app.alerts.rules import evaluate_cpu, evaluate_disks, evaluate_memory, evaluate_services
from app.config import Settings
from tests.factories import make_snapshot


def test_cpu_below_warning_does_not_breach(settings: Settings) -> None:
    snapshot = make_snapshot()
    snapshot.cpu.utilization_percent = settings.cpu_warning_percent - 0.1

    evaluation = evaluate_cpu(snapshot, settings)

    assert evaluation.breaching is False
    assert evaluation.rule_key == "cpu"
    assert evaluation.target == ""
    assert evaluation.min_duration_seconds == settings.cpu_sustained_seconds


def test_cpu_exactly_at_warning_threshold_breaches(settings: Settings) -> None:
    snapshot = make_snapshot()
    snapshot.cpu.utilization_percent = settings.cpu_warning_percent

    assert evaluate_cpu(snapshot, settings).breaching is True


def test_memory_uses_ram_percent_with_no_duration(settings: Settings) -> None:
    snapshot = make_snapshot()
    snapshot.memory.ram_percent = settings.memory_warning_percent

    evaluation = evaluate_memory(snapshot, settings)

    assert evaluation.breaching is True
    assert evaluation.min_duration_seconds == 0
    assert evaluation.warning_threshold == settings.memory_warning_percent
    assert evaluation.critical_threshold == settings.memory_critical_percent


def test_memory_below_warning_does_not_breach(settings: Settings) -> None:
    snapshot = make_snapshot()
    snapshot.memory.ram_percent = settings.memory_warning_percent - 5

    assert evaluate_memory(snapshot, settings).breaching is False


def test_disks_produce_one_evaluation_per_mount(settings: Settings) -> None:
    snapshot = make_snapshot()  # ships with one disk mounted at "/"
    snapshot.disks[0].percent = settings.disk_warning_percent + 5

    evaluations = evaluate_disks(snapshot, settings)

    assert len(evaluations) == 1
    assert evaluations[0].rule_key == "disk"
    assert evaluations[0].target == "/"
    assert evaluations[0].breaching is True
    assert evaluations[0].min_duration_seconds == 0


def test_no_disks_produces_no_evaluations(settings: Settings) -> None:
    snapshot = make_snapshot()
    snapshot.disks = []

    assert evaluate_disks(snapshot, settings) == []


def test_services_empty_mapping_produces_no_evaluations() -> None:
    assert evaluate_services({}) == []


def test_services_stopped_service_breaches_as_critical() -> None:
    evaluations = evaluate_services({"nginx": False})

    assert len(evaluations) == 1
    evaluation = evaluations[0]
    assert evaluation.rule_key == "service"
    assert evaluation.target == "nginx"
    assert evaluation.breaching is True
    assert evaluation.value >= evaluation.critical_threshold
    assert evaluation.min_duration_seconds == 0


def test_services_running_service_does_not_breach() -> None:
    evaluations = evaluate_services({"nginx": True})

    assert evaluations[0].breaching is False


def test_services_multiple_services_are_evaluated_independently() -> None:
    evaluations = evaluate_services({"nginx": True, "docker": False, "ssh": True})

    by_target = {e.target: e.breaching for e in evaluations}
    assert by_target == {"nginx": False, "docker": True, "ssh": False}
