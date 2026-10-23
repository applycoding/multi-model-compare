#!/usr/bin/env python3
"""Generate docs/screenshots/*.png from a local mock mmc serve instance (placeholder stub)."""

from __future__ import annotations

from pathlib import Path


def main() -> int:
    out = Path("docs/screenshots")
    out.mkdir(parents=True, exist_ok=True)
    for name in ("home.png", "run.png", "history.png"):
        path = out / name
        if not path.exists():
            path.write_bytes(b"\x89PNG\r\n\x1a\n")
    print("screenshot placeholders written to docs/screenshots/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
