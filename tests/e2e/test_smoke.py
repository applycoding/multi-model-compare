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
    for key in list(env):
        if key.endswith("_API_KEY") or "PROXY" in key:
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
    expect(page.locator("#vendor-disclosure")).to_contain_text("anthropic")
    expect(page.locator("#vendor-disclosure")).to_contain_text("openai")
    expect(page.locator("#vendor-disclosure")).to_contain_text("google")
    expect(page.locator("#vendor-disclosure")).to_contain_text("xai")
    expect(page.locator("#vendor-disclosure")).to_contain_text("mock")
    page.fill('textarea[name="prompt"]', "e2e smoke prompt")
    page.fill('input[name="seed"]', "42")
    page.click('button[type="submit"]')
    page.wait_for_url("**/runs/*")
    page.locator("table.results tbody tr")
    status_cells = page.locator("table.results tbody tr td:nth-child(3)")
    ok_count = sum(1 for i in range(status_cells.count()) if "ok" in status_cells.nth(i).inner_text())
    assert ok_count >= 4
    cost_cells = page.locator("table.results tbody tr td:nth-child(8)")
    import re

    for i in range(min(4, cost_cells.count())):
        text = cost_cells.nth(i).inner_text()
        assert re.match(r"^\$\d+\.\d{6}", text.strip().split()[0])
    page.goto(f"{mmc_server}/history")
    expect(page.locator("ul li")).to_have_count(1, timeout=5000)
    assert aborted_nonlocal == []
