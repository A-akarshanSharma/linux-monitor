import logging

import pytest

from app.collectors import CollectionError
from tests.factories import FakeLiveMetrics

ENDPOINTS = ["/api/system", "/api/metrics/current", "/api/processes"]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_collection_failure_returns_503_and_is_logged(
    make_client, caplog: pytest.LogCaptureFixture, path: str
) -> None:
    error = CollectionError("memory", OSError("cannot read /proc/meminfo"))
    client = make_client(FakeLiveMetrics(error=error))

    with caplog.at_level(logging.ERROR):
        response = client.get(path)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "collection_failed",
            "message": "Failed to collect memory metrics. Try again shortly.",
        }
    }
    assert "/proc/meminfo" not in response.text  # internals stay server-side
    record = next(r for r in caplog.records if r.message == "metric_collection_failed")
    assert record.collector == "memory"
    assert record.path == path
    assert record.exc_info is not None


def test_unexpected_exception_returns_generic_500_and_is_logged(
    make_client, caplog: pytest.LogCaptureFixture
) -> None:
    client = make_client(FakeLiveMetrics(error=RuntimeError("password=hunter2 in /etc/secret")))

    with caplog.at_level(logging.ERROR):
        response = client.get("/api/metrics/current")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error."}
    }
    assert "hunter2" not in response.text
    record = next(r for r in caplog.records if r.message == "api_error")
    assert record.method == "GET"
    assert "hunter2" in "".join(str(record.exc_info[1]))  # ...but the log has the detail


def test_unknown_route_uses_standard_error_shape(client) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_method_not_allowed_keeps_allow_header(client) -> None:
    response = client.post("/api/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"]


def test_validation_error_lists_every_problem(client) -> None:
    response = client.get("/api/processes", params={"limit": "many"})

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["message"] == "Request validation failed."
    assert body["error"]["details"] == [
        {
            "field": "query.limit",
            "message": "Input should be a valid integer, unable to parse string as an integer",
        }
    ]
