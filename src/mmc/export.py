from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mmc.judge.schemas import CriterionScore
from mmc.records import RunRecord


class RunExport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    exported_at: datetime
    runs: list[RunRecord]


def to_json(records: Iterable[RunRecord], now: datetime) -> str:
    payload = RunExport(exported_at=now, runs=list(records))
    return payload.model_dump_json()


def _sanitize_cell(value: str) -> str:
    out = []
    for ch in value:
        if ord(ch) < 32 and ch not in "\t\n\r":
            out.append("\ufffd")
        else:
            out.append(ch)
    result = "".join(out)
    if result and result[0] in "=+-@\t\r\n":
        result = "'" + result
    return result


def to_csv(records: Iterable[RunRecord]) -> str:
    runs = list(records)
    criteria_order: list[str] = []
    for run in runs:
        for c in run.rubric.criteria:
            if c.key not in criteria_order:
                criteria_order.append(c.key)
    header = [
        "run_id",
        "created_at",
        "prompt",
        "model_key",
        "vendor",
        "status",
        "finish_reason",
        "provider_request_id",
        "label",
        "ttft_ms",
        "total_ms",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "input_source",
        "output_source",
        "cost_status",
        "cost_usd",
        "pricing_version",
        "judge_model",
        "judged",
        "self_judged",
        "judge_exclusion_reason",
        *[f"{c}_score" for c in criteria_order],
        *[f"{c}_rationale" for c in criteria_order],
        "overall_score",
        "error_kind",
        "error_message",
    ]
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    label_lookup: dict[str, dict[str, str]] = {}
    for run in runs:
        inv = {v: k for k, v in (run.judge.label_map.items() if run.judge else {})}
        label_lookup[run.id] = inv
    for run in runs:
        judge_model = run.judge.judge.key if run.judge and run.judge.judge else ""
        for ans in run.answers:
            label = ""
            judged = "false"
            self_judged = "false"
            exclusion = ""
            crit_scores: dict[str, CriterionScore] = {}
            overall = ""
            if run.judge:
                for lbl, key in run.judge.label_map.items():
                    if key == ans.model.key:
                        label = lbl
                if ans.model.key in run.judge.excluded:
                    exclusion = run.judge.excluded[ans.model.key]
                elif ans.model.key in run.judge.scores:
                    judged = "true"
                    sc = run.judge.scores[ans.model.key]
                    self_judged = str(sc.self_judged).lower()
                    overall = str(sc.overall)
                    crit_scores = dict(sc.criteria)
            row = [
                run.id,
                run.created_at.isoformat(),
                _sanitize_cell(run.prompt),
                ans.model.key,
                ans.model.vendor,
                ans.status,
                ans.finish_reason or "",
                ans.provider_request_id or "",
                label,
                "" if ans.timing is None or ans.timing.ttft_ms is None else str(ans.timing.ttft_ms),
                "" if ans.timing is None else str(ans.timing.total_ms),
                "" if ans.usage is None else str(ans.usage.input_tokens),
                "" if ans.usage is None else str(ans.usage.output_tokens),
                "" if ans.usage is None or ans.usage.reasoning_tokens is None else str(ans.usage.reasoning_tokens),
                "" if ans.usage is None else ans.usage.input_source,
                "" if ans.usage is None else ans.usage.output_source,
                "" if ans.cost is None else ans.cost.status,
                "" if ans.cost is None or ans.cost.total_usd is None else str(ans.cost.total_usd),
                run.pricing_version,
                judge_model,
                judged,
                self_judged,
                exclusion,
            ]
            for crit_key in criteria_order:
                cs = crit_scores.get(crit_key)
                row.append("" if cs is None else str(cs.score))
            for crit_key in criteria_order:
                cs = crit_scores.get(crit_key)
                row.append("" if cs is None else _sanitize_cell(cs.rationale))
            row.append(overall)
            row.append(ans.error.kind if ans.error else "")
            row.append(_sanitize_cell(ans.error.message if ans.error else ""))
            writer.writerow(row)
    return buf.getvalue()
