#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: smoke.py BASE_URL", file=sys.stderr)
        return 2
    base = sys.argv[1].rstrip("/")

    def get(path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        req = urllib.request.Request(base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    code, _ = get("/")
    if code != 200:
        return 1
    for path, _ctype in (
        ("/static/app.css", "text/css"),
        ("/static/app.js", "application/javascript"),
    ):
        c, _ = get(path)
        if c != 200:
            return 1
    if get("/", headers={"Host": "evil.example"})[0] != 400:
        return 1
    if get("/api/runs", headers={"Content-Type": "application/json"})[0] != 405:
        pass
    _, body = get("/api/csrf")
    token = json.loads(body.decode())["csrf_token"]
    req = urllib.request.Request(
        base + "/api/runs",
        data=json.dumps({"prompt": "ci smoke", "seed": 1}).encode(),
        headers={"Content-Type": "application/json", "X-CSRF-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 201:
            return 1
        data = json.loads(resp.read().decode())
    if len([a for a in data["answers"] if a["status"] == "ok"]) != 4:
        return 1
    if data.get("judge", {}).get("status") != "ok":
        return 1
    run_id = data["id"]
    if get(f"/runs/{run_id}")[0] != 200:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
