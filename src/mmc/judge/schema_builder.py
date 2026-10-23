from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model


def verdict_json_schema(labels: Sequence[str], criteria: Sequence[str]) -> dict[str, Any]:
    label_enum = labels if labels else ["A"]
    crit_enum = criteria if criteria else ["correctness"]
    score_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["criterion", "score", "rationale"],
        "properties": {
            "criterion": {"type": "string", "enum": list(crit_enum)},
            "score": {"type": "integer", "minimum": 1, "maximum": 5},
            "rationale": {"type": "string", "minLength": 1},
        },
    }
    verdict_item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["label", "scores"],
        "properties": {
            "label": {"type": "string", "enum": list(label_enum)},
            "scores": {
                "type": "array",
                "minItems": len(crit_enum),
                "maxItems": len(crit_enum),
                "items": score_schema,
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdicts"],
        "properties": {
            "verdicts": {
                "type": "array",
                "minItems": len(label_enum),
                "maxItems": len(label_enum),
                "items": verdict_item,
            }
        },
    }


def verdict_model(labels: Sequence[str], criteria: Sequence[str], rationale_max: int) -> type[BaseModel]:
    crit_models: dict[str, type[BaseModel]] = {}
    for crit in criteria:
        crit_models[crit] = create_model(
            f"Score_{crit}",
            __config__=ConfigDict(extra="forbid"),
            criterion=(str, Field(pattern=r"^[a-z_]{1,32}$")),
            score=(int, Field(ge=1, le=5)),
            rationale=(str, Field(min_length=1, max_length=rationale_max)),
        )

    class VerdictItem(BaseModel):
        model_config = ConfigDict(extra="forbid")
        label: str
        scores: list[BaseModel]

    class VerdictRoot(BaseModel):
        model_config = ConfigDict(extra="forbid")
        verdicts: list[VerdictItem]

    return VerdictRoot
