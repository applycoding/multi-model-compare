from __future__ import annotations

import json
import re
from collections.abc import Sequence

from mmc.judge.schemas import CriterionScore


class VerdictError(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: set[str] = set()
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise VerdictError(f"duplicate JSON key: {key}")
        seen.add(key)
        result[key] = value
    return result


def _strip_fence(raw: str) -> str:
    text = raw.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*)\n?```\s*$", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def parse_verdict(
    raw: str,
    labels: set[str],
    criteria: Sequence[str],
    rationale_max: int,
) -> dict[str, dict[str, CriterionScore]]:
    text = _strip_fence(raw)
    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicates)
    except json.JSONDecodeError as exc:
        raise VerdictError(str(exc)) from exc
    if not isinstance(data, dict):
        raise VerdictError("verdict must be an object")
    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list):
        raise VerdictError("missing verdicts array")
    if len(verdicts) != len(labels):
        raise VerdictError("wrong number of verdicts")
    crit_set = set(criteria)
    result: dict[str, dict[str, CriterionScore]] = {}
    seen_labels: set[str] = set()
    for item in verdicts:
        if not isinstance(item, dict):
            raise VerdictError("verdict item must be object")
        label = item.get("label")
        if label not in labels:
            raise VerdictError(f"unexpected label {label}")
        if label in seen_labels:
            raise VerdictError(f"duplicate label {label}")
        seen_labels.add(label)
        scores_raw = item.get("scores")
        if not isinstance(scores_raw, list):
            raise VerdictError("scores must be array")
        if len(scores_raw) != len(crit_set):
            raise VerdictError("wrong criteria count")
        crit_scores: dict[str, CriterionScore] = {}
        seen_crit: set[str] = set()
        for sc in scores_raw:
            if not isinstance(sc, dict):
                raise VerdictError("score must be object")
            crit = sc.get("criterion")
            if crit not in crit_set:
                raise VerdictError(f"unexpected criterion {crit}")
            if crit in seen_crit:
                raise VerdictError(f"duplicate criterion {crit}")
            seen_crit.add(crit)
            score_val = sc.get("score")
            if not isinstance(score_val, int) or isinstance(score_val, bool):
                raise VerdictError("score must be int")
            if score_val < 1 or score_val > 5:
                raise VerdictError("score out of range")
            rationale = sc.get("rationale", "")
            if not isinstance(rationale, str):
                raise VerdictError("rationale must be string")
            rat = rationale.strip()
            if not rat:
                raise VerdictError("empty rationale")
            if len(rat) > rationale_max:
                raise VerdictError("rationale too long")
            crit_scores[str(crit)] = CriterionScore(criterion=str(crit), score=score_val, rationale=rat)
        if seen_crit != crit_set:
            raise VerdictError("missing criteria")
        result[str(label)] = crit_scores
    if seen_labels != labels:
        raise VerdictError("missing labels")
    return result
