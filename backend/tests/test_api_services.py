from app.models import ServiceState
from tests.factories import FakeServicesRepository, make_service_record


def test_returns_configured_services_in_repository_order(
    make_client, fake_service, fake_repository, fake_alerts_repository
) -> None:
    statuses = [
        make_service_record("nginx", ServiceState.RUNNING, "active"),
        make_service_record("ssh", ServiceState.STOPPED, "inactive"),
        make_service_record("docker", ServiceState.UNKNOWN, "no systemd"),
    ]
    client = make_client(
        fake_service, fake_repository, fake_alerts_repository, FakeServicesRepository(statuses)
    )

    response = client.get("/api/services")

    assert response.status_code == 200
    body = response.json()
    assert [s["name"] for s in body["services"]] == ["nginx", "ssh", "docker"]
    assert body["services"][0]["state"] == "RUNNING"
    assert body["services"][1]["state"] == "STOPPED"
    assert body["services"][2]["state"] == "UNKNOWN"
    assert body["services"][2]["detail"] == "no systemd"


def test_no_services_configured_returns_empty_list(
    make_client, fake_service, fake_repository, fake_alerts_repository
) -> None:
    client = make_client(
        fake_service, fake_repository, fake_alerts_repository, FakeServicesRepository([])
    )

    response = client.get("/api/services")

    assert response.status_code == 200
    assert response.json() == {"services": []}


def test_detail_can_be_null(
    make_client, fake_service, fake_repository, fake_alerts_repository
) -> None:
    statuses = [make_service_record("nginx", ServiceState.RUNNING, detail=None)]
    client = make_client(
        fake_service, fake_repository, fake_alerts_repository, FakeServicesRepository(statuses)
    )

    body = client.get("/api/services").json()

    assert body["services"][0]["detail"] is None


def test_default_client_fixture_has_no_services_configured(client) -> None:
    """The plain `client` fixture wires in an empty FakeServicesRepository by default."""
    response = client.get("/api/services")

    assert response.status_code == 200
    assert response.json() == {"services": []}


def test_repository_failure_returns_generic_500(
    make_client, fake_service, fake_repository, fake_alerts_repository
) -> None:
    class BrokenRepository:
        def get_all_statuses(self):
            raise RuntimeError("db locked")

    client = make_client(fake_service, fake_repository, fake_alerts_repository, BrokenRepository())

    response = client.get("/api/services")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error."}
    }
    assert "db locked" not in response.text
