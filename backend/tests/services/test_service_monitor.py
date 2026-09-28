from unittest.mock import patch

import pytest

from app.models import ServiceState
from app.services.service_monitor import check_service, check_services


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    import subprocess

    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.mark.parametrize("output", ["active", "  active\n"])
def test_active_output_is_running(output: str) -> None:
    with patch("subprocess.run", return_value=_completed(stdout=output, returncode=0)):
        result = check_service("nginx")

    assert result.name == "nginx"
    assert result.state is ServiceState.RUNNING
    assert result.detail == "active"


@pytest.mark.parametrize("output", ["inactive", "failed", "activating", "deactivating"])
def test_recognised_non_active_outputs_are_stopped(output: str) -> None:
    with patch("subprocess.run", return_value=_completed(stdout=output, returncode=3)):
        result = check_service("nginx")

    assert result.state is ServiceState.STOPPED
    assert result.detail == output


def test_unit_not_found_is_unknown_not_stopped() -> None:
    """systemctl prints 'unknown' (not 'inactive') for a unit that doesn't exist at
    all - the platform must not report that as a definite STOPPED."""
    with patch("subprocess.run", return_value=_completed(stdout="unknown", returncode=4)):
        result = check_service("does-not-exist")

    assert result.state is ServiceState.UNKNOWN


def test_unrecognised_output_is_unknown() -> None:
    with patch("subprocess.run", return_value=_completed(stdout="something-new", returncode=0)):
        result = check_service("nginx")

    assert result.state is ServiceState.UNKNOWN


def test_empty_stdout_falls_back_to_stderr_as_detail() -> None:
    with patch(
        "subprocess.run",
        return_value=_completed(stdout="", stderr="Failed to connect to bus", returncode=1),
    ):
        result = check_service("nginx")

    assert result.state is ServiceState.UNKNOWN
    assert result.detail == "Failed to connect to bus"


def test_systemctl_not_found_is_unknown_with_a_clear_detail() -> None:
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = check_service("nginx")

    assert result.state is ServiceState.UNKNOWN
    assert "systemctl" in result.detail


def test_timeout_is_unknown() -> None:
    import subprocess

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="systemctl", timeout=5)):
        result = check_service("nginx", timeout=5)

    assert result.state is ServiceState.UNKNOWN
    assert "timed out" in result.detail


def test_other_os_error_is_unknown() -> None:
    with patch("subprocess.run", side_effect=PermissionError("denied")):
        result = check_service("nginx")

    assert result.state is ServiceState.UNKNOWN
    assert "denied" in result.detail


def test_check_service_never_raises_for_any_subprocess_failure() -> None:
    for exc in (FileNotFoundError(), PermissionError("x"), OSError("y")):
        with patch("subprocess.run", side_effect=exc):
            check_service("nginx")  # must not raise


def test_check_services_evaluates_each_name_independently() -> None:
    def fake_run(cmd, **kwargs):
        name = cmd[-1]
        if name == "broken":
            raise FileNotFoundError()
        return _completed(stdout="active" if name == "nginx" else "inactive")

    with patch("subprocess.run", side_effect=fake_run):
        results = check_services(["nginx", "broken", "ssh"])

    by_name = {r.name: r.state for r in results}
    assert by_name == {
        "nginx": ServiceState.RUNNING,
        "broken": ServiceState.UNKNOWN,
        "ssh": ServiceState.STOPPED,
    }


def test_check_services_with_no_names_returns_empty_list() -> None:
    assert check_services([]) == []


def test_checked_at_is_timezone_aware() -> None:
    with patch("subprocess.run", return_value=_completed(stdout="active")):
        result = check_service("nginx")

    assert result.checked_at.tzinfo is not None
