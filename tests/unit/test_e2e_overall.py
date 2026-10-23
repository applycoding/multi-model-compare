from __future__ import annotations

import pytest

from mmc.config.loader import load_app_config
from mmc.core.request import RunRequest, resolve_request
from mmc.service import CompareService
from tests.e2e.test_smoke import EXPECTED_OVERALL


@pytest.mark.asyncio
async def test_seed_42_overall_scores_match_e2e(
    repo, registry, settings, redactor, stepping_clock, estimator, id_factory
) -> None:
    config = load_app_config(None)
    service = CompareService(config, settings, registry, repo, stepping_clock, redactor, estimator, id_factory)
    req = RunRequest(prompt="e2e smoke prompt", seed=42)
    resolved = resolve_request(req, config, settings, redactor, registry)
    record = await service.run(resolved)
    assert record.judge is not None
    label_to_overall = {
        lbl: record.judge.scores[key].overall for lbl, key in record.judge.label_map.items()
    }
    for lbl, expected in EXPECTED_OVERALL.items():
        assert label_to_overall[lbl] == expected
