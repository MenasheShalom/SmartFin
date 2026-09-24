import importlib

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import get_settings


@pytest.fixture
def spa_client(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>SmartFin</title>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "manifest.webmanifest").write_text("{}")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    get_settings.cache_clear()
    module = importlib.reload(main_module)
    yield TestClient(module.app)
    monkeypatch.delenv("STATIC_DIR")
    get_settings.cache_clear()
    importlib.reload(main_module)


def test_app_routes_get_index_html_with_security_headers(spa_client):
    for path in ("/", "/weekly", "/settings/rules"):
        response = spa_client.get(path)
        assert response.status_code == 200
        assert "SmartFin" in response.text
        assert response.headers["cache-control"] == "no-cache"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_hashed_assets_are_cached_for_a_year(spa_client):
    response = spa_client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


def test_unknown_api_paths_stay_404(spa_client):
    assert spa_client.get("/api/nope").status_code == 404
    assert spa_client.get("/health").status_code in (200, 503)
