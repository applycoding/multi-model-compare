#!/usr/bin/env python3
"""Capture docs/screenshots/*.png from a local mock mmc serve instance."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(base: str, timeout_s: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/healthz", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"mmc serve did not become healthy at {base}")


def main() -> int:
    from playwright.sync_api import sync_playwright

    root = Path(__file__).resolve().parents[1]
    out_dir = root / "docs" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    port = _free_port()
    env = os.environ.copy()
    env.setdefault("MMC_PROFILE", "mock")
    env.setdefault("OTEL_SDK_DISABLED", "true")
    env.setdefault("MMC_TOKEN_ESTIMATOR", "chars")
    tmp_db = root / ".screenshot-mmc.sqlite3"
    env["MMC_DB_PATH"] = str(tmp_db)
    if tmp_db.exists():
        tmp_db.unlink()

    mmc_bin = Path(sys.executable).parent / "mmc"
    proc = subprocess.Popen(
        [str(mmc_bin), "serve", "--port", str(port)],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_health(base)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(f"{base}/")
            page.wait_for_selector('textarea[name="prompt"]')
            page.screenshot(path=str(out_dir / "home.png"), full_page=True)

            page.fill('textarea[name="prompt"]', "Screenshot demo prompt")
            page.fill('input[name="seed"]', "42")
            page.click('button[type="submit"]')
            page.wait_for_url("**/runs/*")
            page.wait_for_selector("table.results")
            page.screenshot(path=str(out_dir / "run.png"), full_page=True)

            page.goto(f"{base}/history")
            page.wait_for_selector("ul li")
            page.screenshot(path=str(out_dir / "history.png"), full_page=True)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        if tmp_db.exists():
            tmp_db.unlink()

    print(f"Wrote screenshots to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
