from __future__ import annotations

import logging

from mmc.logging_setup import RedactingFormatter
from mmc.records import RunRecord
from mmc.redact import Redactor, redact_record
from tests.conftest import SENTINEL_OPENAI


def test_pattern_redaction() -> None:
    r = Redactor([])
    assert "[REDACTED]" in r("Bearer secret-token-here")


def test_configured_secret_first(redactor: Redactor) -> None:
    assert redactor.contains_secret(f"prefix {SENTINEL_OPENAI} suffix")
    assert SENTINEL_OPENAI not in redactor(f"leak {SENTINEL_OPENAI}")


def test_redact_record_strings(redactor: Redactor, stepping_clock) -> None:
    from mmc.config.loader import load_app_config
    from mmc.core.results import AnswerResult, CostTotal, Timing, TokenUsage

    config = load_app_config(None)
    spec = config.model("mock:mock-gpt")
    ans = AnswerResult(
        model=spec,
        status="ok",
        text=f"hello {SENTINEL_OPENAI}",
        resolved_params={},
        usage=TokenUsage(
            input_tokens=1,
            output_tokens=1,
            reasoning_tokens=None,
            total_tokens=2,
            raw={},
            input_source="provider",
            output_source="provider",
        ),
        timing=Timing(ttft_ms=1.0, total_ms=2.0),
    )
    record = RunRecord(
        id="run-0001",
        created_at=stepping_clock.now(),
        profile="mock",
        app_version="0.1.0",
        prompt=f"prompt {SENTINEL_OPENAI}",
        status="completed",
        seed=1,
        vendors_contacted=["openai"],
        judge_settings=config.judge,
        rubric=config.rubric,
        pricing_version=config.pricing.version,
        pricing_entries_used=[],
        answers=[ans],
        judge=None,
        total=CostTotal(subtotal_usd=0, estimated=False, unknown_count=0),
    )
    out = redact_record(record, redactor)
    dumped = out.model_dump_json()
    assert SENTINEL_OPENAI not in dumped


def test_redacting_formatter_exc_info(redactor: Redactor) -> None:
    fmt = RedactingFormatter(redactor)
    try:
        raise RuntimeError(SENTINEL_OPENAI)
    except RuntimeError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, "", 0, "msg", (), sys.exc_info())
    text = fmt.format(record)
    assert SENTINEL_OPENAI not in text
