from __future__ import annotations

from datetime import date
from decimal import Decimal

from mmc.config.loader import load_app_config
from mmc.core.pricing import compute_cost, sum_costs
from mmc.core.results import TokenUsage


def _usage(inp: int, out: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=inp,
        output_tokens=out,
        reasoning_tokens=None,
        total_tokens=inp + out,
        raw={},
        input_source="provider",
        output_source="provider",
    )


def test_half_microdollar_boundary() -> None:
    config = load_app_config(None)
    # gpt-6-luna output is $0.50/M: one token -> 0.0000005 -> 0.000001
    cost_out = compute_cost("openai:gpt-6-luna", _usage(0, 1), False, config.pricing, date(2026, 10, 23))
    assert cost_out.output_usd == Decimal("0.000001")
    cost2 = compute_cost(
        "openai:gpt-6-luna",
        _usage(1, 1),
        False,
        config.pricing,
        date(2026, 10, 23),
    )
    assert cost2.input_usd == Decimal("0.000000")
    assert cost2.output_usd == Decimal("0.000001")
    assert cost2.total_usd == Decimal("0.000001")


def test_exactly_twelve_real_pricing_entries() -> None:
    config = load_app_config(None)
    real = [e for e in config.pricing.entries if not e.model_key.startswith("mock:")]
    assert len(real) == 12


def test_unknown_cost_not_zero() -> None:
    config = load_app_config(None)
    cost = compute_cost("no:such-model", _usage(10, 10), False, config.pricing, date(2026, 10, 23))
    assert cost.status == "unknown"
    assert cost.total_usd is None
    total = sum_costs([cost])
    assert total.unknown_count == 1
    assert total.subtotal_usd == Decimal(0)


def test_effective_dates_argon() -> None:
    config = load_app_config(None)
    e1 = config.pricing.lookup("google:gemini-4-argon", date(2026, 11, 30))
    e2 = config.pricing.lookup("google:gemini-4-argon", date(2026, 12, 1))
    assert e1 and e2
    assert e1.input_per_mtok == Decimal("2.00")
    assert e2.input_per_mtok == Decimal("4.00")


def test_grok_long_context_tier() -> None:
    config = load_app_config(None)
    base = compute_cost("xai:grok-4.7", _usage(200_000, 100), False, config.pricing, date(2026, 10, 23))
    high = compute_cost("xai:grok-4.7", _usage(200_001, 100), False, config.pricing, date(2026, 10, 23))
    assert base.price and base.price.tier == "base"
    assert high.price and high.price.tier == "long_context"


def test_haiku_from_basis() -> None:
    config = load_app_config(None)
    cost = compute_cost("anthropic:claude-haiku-5-5", _usage(1000, 1000), False, config.pricing, date(2026, 10, 23))
    assert cost.status == "estimated"
    assert any("from-price" in n for n in cost.notes)
