#!/usr/bin/env python3
"""Maintainer-only: record provider HTTP fixtures with live API keys (not run in CI)."""

from __future__ import annotations

import sys


def main() -> int:
    print("record_fixtures: stub — run locally with live keys per PLAN.md §7", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
