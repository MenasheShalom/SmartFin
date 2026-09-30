import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.config import Settings, get_settings
from app.main import app

LEUMI = {
    "id": "0b6f0c1e-1111-4222-8333-944445555666",
    "company": "leumi",
    "hint": "•••456",
    "added_at": "2026-09-30T10:00:00Z",
    "sync": "running",
    "last_sync": None,
}
ISRACARD = {
    "id": "file-0",
    "company": "isracard",
    "hint": "•••789",
    "added_at": None,
    "sync": None,
    "last_sync": {"ok": False, "error_type": "INVALID_PASSWORD", "finished_at": "2026-09-30T03:01:00Z"},
}


class FakeScraper(BaseHTTPRequestHandler):
    """Answers like the scraper's API and records what it was sent."""

    requests: list = []

    def _reply(self, status, body=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if body is not None:
            self.wfile.write(json.dumps(body).encode())

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        FakeScraper.requests.append(
            (self.command, self.path, self.headers.get("Authorization"), body)
        )
        if self.headers.get("Authorization") != "Bearer tok":
            return self._reply(401, {"detail": "Unauthorized"})
        route = (self.command, self.path)
        if route == ("GET", "/companies"):
            return self._reply(
                200,
                [
                    {"id": "leumi", "login_fields": ["username", "password"]},
                    {"id": "isracard", "login_fields": ["id", "card6Digits", "password"]},
                ],
            )
        if route == ("GET", "/accounts"):
            return self._reply(200, [LEUMI, ISRACARD])
        if route == ("POST", "/accounts"):
            if "password" not in body["credentials"]:
                return self._reply(422, {"detail": "accounts[0] (leumi) is missing credentials: password"})
            return self._reply(201, {**LEUMI, "sync": "queued"})
        if route == ("PUT", f"/accounts/{LEUMI['id']}"):
            return self._reply(200, LEUMI)
        if route == ("DELETE", f"/accounts/{LEUMI['id']}"):
            return self._reply(204)
        if route == ("POST", "/sync"):
            return self._reply(202, [LEUMI])
        if route == ("POST", "/accounts/file-0/sync"):
            return self._reply(500, {"detail": "Internal error"})
        return self._reply(404, {"detail": "Not found"})

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def log_message(self, *args):
        pass


@pytest.fixture
def scraper():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeScraper)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    FakeScraper.requests = []
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def api(client, scraper):
    app.dependency_overrides[get_settings] = lambda: Settings(ingest_token="tok", scraper_url=scraper)
    return client


def test_lists_connections_and_companies_with_hebrew_names(api):
    data = api.get("/api/connections").json()
    assert [c["label"] for c in data["connections"]] == ["בנק לאומי", "ישראכרט"]
    assert [c["kind"] for c in data["connections"]] == ["bank", "card"]
    assert data["connections"][1]["last_sync"]["error_type"] == "INVALID_PASSWORD"
    isracard = next(c for c in data["companies"] if c["id"] == "isracard")
    assert isracard == {
        "id": "isracard",
        "label": "ישראכרט",
        "kind": "card",
        "login_fields": ["id", "card6Digits", "password"],
    }
    assert all(auth == "Bearer tok" for _, _, auth, _ in FakeScraper.requests)


def test_add_passes_the_login_through(api):
    body = {"company": "leumi", "credentials": {"username": "me", "password": "pw"}}
    response = api.post("/api/connections", json=body)
    assert response.status_code == 201
    assert response.json()["sync"] == "queued"
    assert "pw" not in response.text
    assert FakeScraper.requests[-1][3] == body


def test_scraper_validation_errors_come_through(api):
    response = api.post("/api/connections", json={"company": "leumi", "credentials": {"username": "me"}})
    assert response.status_code == 422
    assert "missing credentials: password" in response.json()["detail"]


def test_update_delete_and_sync(api):
    lid = LEUMI["id"]
    assert api.put(f"/api/connections/{lid}", json={"credentials": {"username": "a", "password": "b"}}).status_code == 200
    assert api.delete(f"/api/connections/{lid}").status_code == 204
    assert api.post("/api/connections/sync").status_code == 202
    assert api.put("/api/connections/nope", json={"credentials": {"password": "b"}}).status_code == 404
    assert api.post("/api/connections/file-0/sync").status_code == 502


def test_bad_ids_and_oversized_logins_never_reach_the_scraper(api):
    assert api.delete("/api/connections/..%2F..%2Fsync").status_code in (404, 422)
    too_long = {"company": "leumi", "credentials": {"username": "x" * 201, "password": "p"}}
    assert api.post("/api/connections", json=too_long).status_code == 422
    not_strings = {"company": "leumi", "credentials": {"username": 5, "password": "p"}}
    assert api.post("/api/connections", json=not_strings).status_code == 422
    assert FakeScraper.requests == []


def test_scraper_down(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        ingest_token="tok", scraper_url="http://127.0.0.1:9"
    )
    response = client.get("/api/connections")
    assert response.status_code == 503
    assert response.json()["detail"] == "The scraper is not reachable"


def test_no_token(client):
    app.dependency_overrides[get_settings] = lambda: Settings(ingest_token=None)
    assert client.get("/api/connections").status_code == 503
