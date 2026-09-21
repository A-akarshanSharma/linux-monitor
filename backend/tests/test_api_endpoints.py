import pytest

from app import __version__
from tests.factories import NOW, FakeLiveMetrics, make_snapshot


def test_system(client) -> None:
    response = client.get("/api/system")

    assert response.status_code == 200
    body = response.json()
    assert body["hostname"] == "test-host"
    assert body["os_name"] == "Ubuntu 24.04 LTS"
    assert body["runtime_environment"] == "host"
    assert body["uptime_seconds"] == 3600.0


def test_current_metrics_shape(client) -> None:
    response = client.get("/api/metrics/current")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"collected_at", "cpu", "memory", "disks", "network"}
    assert body["cpu"]["utilization_percent"] == 12.5
    assert body["memory"]["ram_percent"] == 37.5
    assert body["disks"][0]["mountpoint"] == "/"
    assert body["network"]["send_rate_bytes_per_sec"] == 1.5


def test_current_metrics_null_rates_are_allowed(make_client) -> None:
    snapshot = make_snapshot()
    snapshot.network.send_rate_bytes_per_sec = None
    snapshot.network.recv_rate_bytes_per_sec = None

    response = make_client(FakeLiveMetrics(snapshot)).get("/api/metrics/current")

    assert response.status_code == 200
    assert response.json()["network"]["send_rate_bytes_per_sec"] is None


def test_processes_default_limit_comes_from_settings(client, settings) -> None:
    response = client.get("/api/processes")

    body = response.json()
    assert response.status_code == 200
    assert len(body["top_by_cpu"]) == settings.top_processes_count == 5
    assert body["total_count"] == 120
    assert body["running_count"] == 2
    assert body["collected_at"].startswith(NOW.strftime("%Y-%m-%dT%H:%M:%S"))


def test_processes_limit_parameter(make_client) -> None:
    client = make_client(FakeLiveMetrics(make_snapshot(process_count=20)))

    body = client.get("/api/processes", params={"limit": 12}).json()

    assert len(body["top_by_cpu"]) == 12
    assert len(body["top_by_memory"]) == 12
    assert body["top_by_cpu"][0]["pid"] == 1  # best first, order preserved


def test_processes_limit_larger_than_available_returns_what_exists(client) -> None:
    body = client.get("/api/processes", params={"limit": 50}).json()

    assert len(body["top_by_cpu"]) == 5


@pytest.mark.parametrize("limit", ["0", "-1", "51", "abc", "1.5"])
def test_processes_rejects_invalid_limit(client, limit: str) -> None:
    response = client.get("/api/processes", params={"limit": limit})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["field"] == "query.limit"


def test_health(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["uptime_seconds"] >= 0


def test_health_does_not_touch_the_metrics_service(make_client) -> None:
    """Liveness must stay up even if metrics collection is broken."""
    client = make_client(FakeLiveMetrics(error=RuntimeError("collector down")))

    assert client.get("/api/health").status_code == 200


def test_root_redirects_to_docs(client) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_openapi_documents_all_phase2_endpoints(client) -> None:
    schema = client.get("/openapi.json").json()

    assert {"/api/system", "/api/metrics/current", "/api/processes", "/api/health"} <= set(
        schema["paths"]
    )
    assert "ErrorResponse" in schema["components"]["schemas"]
    assert client.get("/docs").status_code == 200
