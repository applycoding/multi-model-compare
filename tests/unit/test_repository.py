from __future__ import annotations

import os
import stat

import pytest
from sqlalchemy.exc import IntegrityError

from mmc.config.loader import load_app_config
from mmc.core.results import AnswerResult, CostTotal
from mmc.honesty import apply_profile_honesty
from mmc.records import RunRecord
from mmc.storage.repository import RunRepository


def _minimal_record(run_id: str, stepping_clock) -> RunRecord:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt")
    return RunRecord(
        id=run_id,
        created_at=stepping_clock.now(),
        profile="mock",
        app_version="0.1.0",
        prompt="hello",
        status="completed",
        seed=1,
        vendors_contacted=["openai"],
        judge_settings=config.judge,
        rubric=config.rubric,
        pricing_version=config.pricing.version,
        pricing_entries_used=[],
        answers=[
            AnswerResult(model=spec, status="ok", text="hi", resolved_params={}),
        ],
        judge=None,
        total=CostTotal(subtotal_usd=0, estimated=False, unknown_count=0),
    )


def test_save_get_roundtrip(repo: RunRepository, stepping_clock, id_factory) -> None:
    rec = apply_profile_honesty(_minimal_record(id_factory(), stepping_clock))
    repo.save(rec)
    got = repo.get(rec.id)
    assert got == rec


def test_db_file_modes(tmp_db) -> None:
    from mmc.storage.db import init_db

    init_db(tmp_db)
    mode = stat.S_IMODE(os.stat(tmp_db).st_mode)
    assert mode == 0o600


def test_snapshot_immutable_after_save(repo: RunRepository, stepping_clock, id_factory) -> None:
    rec = _minimal_record(id_factory(), stepping_clock)
    repo.save(rec)
    stored = repo.get(rec.id)
    assert stored is not None
    mutated = rec.model_copy(update={"prompt": "mutated prompt must not persist"})
    with pytest.raises(IntegrityError):
        repo.save(mutated)
    after = repo.get(rec.id)
    assert after == stored
    assert after.prompt == rec.prompt


def test_delete_removes_run_and_summary(repo: RunRepository, stepping_clock, id_factory) -> None:
    rec = _minimal_record(id_factory(), stepping_clock)
    repo.save(rec)
    assert repo.delete(rec.id) is True
    assert repo.get(rec.id) is None
    assert repo.list(limit=10) == []
    assert repo.delete(rec.id) is False


def test_list_newest_first(repo: RunRepository, stepping_clock, id_factory) -> None:
    r1 = _minimal_record(id_factory(), stepping_clock)
    r2 = _minimal_record(id_factory(), stepping_clock)
    repo.save(r1)
    repo.save(r2)
    rows = repo.list(limit=10)
    assert rows[0].id == r2.id
