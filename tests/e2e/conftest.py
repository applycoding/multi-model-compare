from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run Playwright e2e after asyncio unit/contract tests to avoid event-loop pollution."""
    e2e = [item for item in items if "/e2e/" in str(item.path)]
    rest = [item for item in items if item not in e2e]
    items[:] = rest + e2e
