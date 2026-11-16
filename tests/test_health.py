from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from orderdesk.config import Settings
from orderdesk.main import create_app


def _settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        database_connect_timeout_seconds=1,
        _env_file=None,
    )


def test_healthz_is_ok_when_the_database_is_reachable(app_database_url: str) -> None:
    with TestClient(create_app(_settings(app_database_url))) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_is_unavailable_when_the_database_is_down(app_database_url: str) -> None:
    # Nothing listens on port 1, so the connection is refused immediately.
    unreachable = make_url(app_database_url).set(port=1).render_as_string(hide_password=False)

    with TestClient(create_app(_settings(unreachable))) as client:
        response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_interactive_api_docs_are_disabled(app_database_url: str) -> None:
    with TestClient(create_app(_settings(app_database_url))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
