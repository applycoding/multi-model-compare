from __future__ import annotations

import json

from mmc.config.loader import load_app_config
from mmc.judge.payload import build_judge_request
from mmc.judge.schema_builder import verdict_json_schema, verdict_model
from mmc.providers.base import OutputSchema


def test_judge_request_json() -> None:
    config = load_app_config(None)
    judge = config.model("openai:gpt-6.1-sol")
    labels = {"A": "answer one", "B": "answer two"}
    criteria = [c.key for c in config.rubric.criteria]
    schema = OutputSchema(
        name="judge_verdict",
        json_schema=verdict_json_schema(sorted(labels), criteria),
        model=verdict_model(sorted(labels), criteria, 600),
    )
    req = build_judge_request(
        "user prompt",
        labels,
        config.rubric,
        judge,
        config.judge,
        "run-0001/judge/0",
        1024,
        schema,
    )
    data = json.loads(req.user)
    assert set(data["answers"].keys()) == {"A", "B"}
    assert req.temperature == 0.0
    claude = config.model("anthropic:claude-sonnet-5-5")
    req2 = build_judge_request(
        "p",
        labels,
        config.rubric,
        claude,
        config.judge,
        "tag",
        512,
        schema,
    )
    assert req2.temperature is None
