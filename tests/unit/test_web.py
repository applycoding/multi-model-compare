from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mmc.settings import Settings
from mmc.web.app import create_app
from mmc.web.security import CSP


@pytest.fixture
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    settings = Settings.from_env()
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["profile"] == "mock"


def test_csp_on_index(client: TestClient) -> None:
    r = client.get("/")
    assert r.headers.get("content-security-policy") == CSP


def test_api_run_with_csrf(client: TestClient) -> None:
    token = client.get("/api/csrf").json()["csrf_token"]
    r = client.post(
        "/api/runs",
        json={"prompt": "web test", "seed": 42},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 201
    assert len(r.json()["answers"]) == 4
