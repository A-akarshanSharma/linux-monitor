from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def dashboard_client(tmp_path: Path) -> TestClient:
    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    (dashboard / "index.html").write_text("<html><title>Packaged dashboard</title></html>")
    (dashboard / "sw.js").write_text("// worker")
    (dashboard / "manifest.webmanifest").write_text('{"name":"Server Monitor"}')
    (dashboard / "assets").mkdir()
    (dashboard / "assets/app-abc123.js").write_text("// built application")
    (dashboard / "api").mkdir()
    (dashboard / "api" / "missing").write_text("must not shadow the API")
    (tmp_path / "private.env").write_text("SECRET=not-public")
    settings = Settings(_env_file=None, frontend_dir=str(dashboard))
    return TestClient(create_app(settings), raise_server_exceptions=False)


def test_dashboard_and_api_share_one_origin(dashboard_client: TestClient) -> None:
    response = dashboard_client.get("/")
    assert response.status_code == 200
    assert "Packaged dashboard" in response.text
    assert response.headers["cache-control"] == "no-cache"
    assert dashboard_client.get("/api/health").json()["status"] == "ok"
    assert dashboard_client.get("/docs").status_code == 200
    assert "/api/health" in dashboard_client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("path", ["/index.html", "/sw.js", "/manifest.webmanifest"])
def test_shell_metadata_is_revalidated(dashboard_client: TestClient, path: str) -> None:
    response = dashboard_client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_fingerprinted_assets_can_be_cached(dashboard_client: TestClient) -> None:
    response = dashboard_client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


@pytest.mark.parametrize(
    "path", ["/api", "/api/missing", "/assets/missing.js", "/private.env", "/%2e%2e/private.env"]
)
def test_missing_files_and_api_routes_never_return_the_app_shell(
    dashboard_client: TestClient,
    path: str,
) -> None:
    response = dashboard_client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "not-public" not in response.text


def test_api_method_errors_still_have_their_json_envelope(dashboard_client: TestClient) -> None:
    response = dashboard_client.post("/api/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
