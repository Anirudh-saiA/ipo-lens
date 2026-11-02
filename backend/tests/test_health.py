import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import main
from app.main import app

client = TestClient(app)


@pytest.mark.db
def test_health_ok_with_database() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_unavailable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenEngine:
        def connect(self) -> None:
            raise OperationalError("SELECT 1", {}, Exception("down"))

    monkeypatch.setattr(main, "engine", BrokenEngine())
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}


def test_disclaimer_in_api_description() -> None:
    assert "not investment advice" in app.description
