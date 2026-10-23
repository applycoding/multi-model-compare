from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mmc.settings import Settings
from mmc.web.app import create_app


@pytest.fixture
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    with TestClient(create_app(Settings.from_env()), base_url="http://127.0.0.1") as c:
        yield c


def test_forged_host(client: TestClient) -> None:
    reg = client.app.state.registry
    before = reg.call_count
    r = client.get("/", headers={"Host": "evil.example"})
    assert r.status_code == 400
    assert reg.call_count == before


def test_cross_site_post(client: TestClient) -> None:
    reg = client.app.state.registry
    before = reg.call_count
    r = client.post(
        "/api/runs",
        json={"prompt": "x"},
        headers={"Origin": "http://evil.example"},
    )
    assert r.status_code == 403
    assert reg.call_count == before
