from sqlalchemy.exc import OperationalError

from app.db import get_session
from app.main import app


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_unreachable_database(client):
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app.dependency_overrides[get_session] = lambda: BrokenSession()
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"
