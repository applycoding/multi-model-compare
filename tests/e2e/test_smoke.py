from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from playwright.sync_api import Page, Route, expect

EXPECTED_OVERALL: dict[str, Decimal] = {
    "A": Decimal("2.60"),
    "B": Decimal("2.35"),
    "C": Decimal("3.25"),
    "D": Decimal("4.25"),
}

_SCRUB_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_BASE_URL",
    "OPENAI_BASE_URL",
    "GOOGLE_GEMINI_BASE_URL",
    "GEMINI_BASE_URL",
    "XAI_API_HOST",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return cast(int, s.getsockname()[1])


@pytest.fixture(scope="session")
def mmc_server(tmp_path_factory) -> Iterator[str]:
    tmp = tmp_path_factory.mktemp("e2e")
    db = tmp / "e2e.sqlite3"
    port = _free_port()
    env = os.environ.copy()
    env["MMC_PROFILE"] = "mock"
    env["MMC_DB_PATH"] = str(db)
    env["MMC_TOKEN_ESTIMATOR"] = "chars"
    env["OTEL_SDK_DISABLED"] = "true"
    for key in _SCRUB_KEYS:
        env.pop(key, None)
    mmc_bin = Path(sys.executable).parent / "mmc"
    proc = subprocess.Popen(
        [str(mmc_bin), "serve", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(40):
        try:
            import urllib.request

            with urllib.request.urlopen(f"{base}/healthz", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("server failed to start")
    yield base
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def aborted_nonlocal() -> list[str]:
    return []


@pytest.fixture
def page_with_guard(page: Page, aborted_nonlocal: list[str]) -> Page:
    def handler(route: Route) -> None:
        host = route.request.url.split("/")[2].split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            aborted_nonlocal.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    page.route("**/*", handler)
    return page


def test_smoke_flow(page_with_guard: Page, mmc_server: str, aborted_nonlocal: list[str]) -> None:
    page = page_with_guard
    page.goto(f"{mmc_server}/")
    expect(page.locator("#vendor-disclosure")).to_contain_text("Mock mode: nothing is sent to any provider")
    page.fill('textarea[name="prompt"]', "e2e smoke prompt")
    page.fill('input[name="seed"]', "42")
    page.click('button[type="submit"]')
    page.wait_for_url("**/runs/*")
    status_cells = page.locator("table.results tbody tr td:nth-child(3)")
    ok_count = sum(1 for i in range(status_cells.count()) if status_cells.nth(i).inner_text().strip().startswith("ok"))
    assert ok_count == 4
    scores: dict[str, Decimal] = {}
    labels_seen: list[str] = []
    for row in page.locator("table.results tbody tr").all():
        cells = row.locator("td")
        if cells.count() < 5:
            continue
        lbl = cells.nth(0).inner_text().strip()
        if lbl not in ("A", "B", "C", "D"):
            continue
        labels_seen.append(lbl)
        overall = cells.nth(-1).inner_text().strip()
        if overall:
            scores[lbl] = Decimal(overall)
    assert sorted(labels_seen) == ["A", "B", "C", "D"]
    for lbl, expected in EXPECTED_OVERALL.items():
        assert scores[lbl] == expected
    expect(page.locator(".pricing-disclosure")).to_contain_text("example pricing (mock)")
    expect(page.locator(".badge-mock-scores")).to_contain_text("mock scores")
    cost_cells = page.locator("table.results tbody tr td:nth-child(8)")
    for i in range(4):
        text = cost_cells.nth(i).inner_text()
        assert text.strip().startswith("$0")
        assert "example pricing (mock)" in text
    page.goto(f"{mmc_server}/history")
    expect(page.locator("ul li")).to_have_count(1, timeout=5000)
    href = page.locator("ul li a").first.get_attribute("href")
    assert href is not None
    run_id = href.split("/")[-1]
    export_resp = page.request.get(f"{mmc_server}/export/runs.json")
    assert export_resp.ok
    payload = export_resp.json()
    assert payload["schema_version"] == 1
    assert any(r["id"] == run_id for r in payload["runs"])
    page.goto(f"{mmc_server}/runs/{run_id}")
    csrf = page.request.get(f"{mmc_server}/api/csrf").json()["csrf_token"]
    delete_resp = page.request.delete(
        f"{mmc_server}/api/runs/{run_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert delete_resp.status == 204
    page.goto(f"{mmc_server}/history")
    expect(page.locator("ul li")).to_have_count(0, timeout=5000)
    assert aborted_nonlocal == []
