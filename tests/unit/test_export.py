from __future__ import annotations

import csv
import io
import json

from mmc.export import RunExport, to_csv, to_json
from tests.unit.test_repository import _minimal_record


def test_json_schema(stepping_clock, id_factory) -> None:
    rec = _minimal_record(id_factory(), stepping_clock)
    from datetime import UTC, datetime

    payload = json.loads(to_json([rec], datetime.now(UTC)))
    assert RunExport.model_validate(payload).schema_version == 1


def test_csv_formula_prefix(stepping_clock, id_factory) -> None:
    rec = _minimal_record(id_factory(), stepping_clock)
    rec = rec.model_copy(update={"prompt": "=SUM(1,2)"})
    text = to_csv([rec])
    rows = list(csv.reader(io.StringIO(text)))
    prompt_cell = rows[1][2]
    assert prompt_cell.startswith("'")
