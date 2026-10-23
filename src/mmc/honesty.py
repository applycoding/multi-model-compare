from __future__ import annotations

import json
from decimal import Decimal
from typing import Literal

from mmc.core.results import Cost, CostTotal
from mmc.judge.schemas import JudgeOutcome
from mmc.records import RunRecord

PricingDisclosure = Literal["live", "example_pricing_mock"]

EXAMPLE_PRICING_MOCK_LABEL = "example pricing (mock)"


def _zero_cost(cost: Cost | None) -> Cost | None:
    if cost is None:
        return None
    notes = list(cost.notes)
    if EXAMPLE_PRICING_MOCK_LABEL not in notes:
        notes.append(EXAMPLE_PRICING_MOCK_LABEL)
    return cost.model_copy(
        update={
            "input_usd": Decimal(0) if cost.input_usd is not None else None,
            "output_usd": Decimal(0) if cost.output_usd is not None else None,
            "total_usd": Decimal(0) if cost.total_usd is not None else None,
            "notes": notes,
        }
    )


def _mark_judge_mock(judge: JudgeOutcome | None) -> JudgeOutcome | None:
    if judge is None or judge.judge is None:
        return judge
    if judge.judge.provider != "mock":
        return judge
    return judge.model_copy(update={"scores_mock": True})


def apply_profile_honesty(record: RunRecord) -> RunRecord:
    judge = _mark_judge_mock(record.judge)
    if record.profile != "mock":
        return record.model_copy(update={"judge": judge, "pricing_disclosure": "live"})

    answers = [ans.model_copy(update={"cost": _zero_cost(ans.cost)}) if ans.cost else ans for ans in record.answers]
    if judge:
        attempts = [
            att.model_copy(update={"cost": _zero_cost(att.cost)}) if att.cost else att for att in judge.attempts
        ]
        judge = judge.model_copy(update={"attempts": attempts})

    total = CostTotal(subtotal_usd=Decimal(0), estimated=False, unknown_count=record.total.unknown_count)
    return record.model_copy(
        update={
            "answers": answers,
            "judge": judge,
            "total": total,
            "pricing_disclosure": "example_pricing_mock",
        }
    )


def honesty_summary_from_record(record: RunRecord) -> tuple[PricingDisclosure | Literal["unknown"], bool, Decimal]:
    honest = apply_profile_honesty(record)
    scores_mock = bool(honest.judge and honest.judge.scores_mock)
    return honest.pricing_disclosure, scores_mock, honest.total.subtotal_usd


def honesty_summary_from_record_json(record_json: str) -> tuple[PricingDisclosure | Literal["unknown"], bool, Decimal]:
    data = json.loads(record_json)
    if "profile" not in data:
        total_raw = data.get("total", {}).get("subtotal_usd", "0")
        return "unknown", False, Decimal(str(total_raw))
    record = RunRecord.model_validate(data)
    return honesty_summary_from_record(record)
