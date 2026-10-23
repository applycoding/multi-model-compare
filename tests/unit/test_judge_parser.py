from __future__ import annotations

import json

import pytest

from mmc.judge.parser import VerdictError, parse_verdict

LABELS = {"A", "B"}
CRITERIA = ["correctness", "completeness", "clarity", "safety"]


def _valid_verdict() -> str:
    verdicts = []
    for label in sorted(LABELS):
        scores = [{"criterion": c, "score": 3, "rationale": f"ok {c}"} for c in CRITERIA]
        verdicts.append({"label": label, "scores": scores})
    return json.dumps({"verdicts": verdicts})


def test_accepts_json_fence() -> None:
    raw = "```json\n" + _valid_verdict() + "\n```"
    parse_verdict(raw, LABELS, CRITERIA, 600)


@pytest.mark.parametrize(
    "mutator,match",
    [
        (lambda r: "not json", "Expecting"),
        (lambda r: json.dumps({"verdicts": []}), "wrong number"),
        (lambda r: r.replace('"score": 3', '"score": 0', 1), "out of range"),
        (lambda r: r.replace('"score": 3', '"score": "4"', 1), "must be int"),
        (lambda r: r.replace('"rationale": "ok correctness"', '"rationale": "   "', 1), "empty rationale"),
    ],
)
def test_rejects_invalid(mutator, match: str) -> None:
    raw = _valid_verdict()
    bad = mutator(raw)
    with pytest.raises(VerdictError, match=match):
        parse_verdict(bad, LABELS, CRITERIA, 600)


def test_duplicate_json_keys() -> None:
    raw = '{"verdicts": [], "verdicts": []}'
    with pytest.raises(VerdictError, match="duplicate JSON key"):
        parse_verdict(raw, LABELS, CRITERIA, 600)
