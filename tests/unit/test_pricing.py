from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from mmc.config.loader import load_app_config
from mmc.config.schemas import PricingTable
from mmc.core.pricing import compute_cost, sum_costs
from mmc.core.results import Cost, TokenUsage

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "config"
SCENARIO_P1 = "Scenario prompt for multi-step seeded session."


def _inp_tokens(prompt: str) -> int:
    return math.ceil(len(prompt) / 4)


def _load_pricing_table(name: str) -> PricingTable:
    data = yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))
    return PricingTable.model_validate(data)


def _scenario_answer_usage() -> TokenUsage:
    inp = _inp_tokens(SCENARIO_P1)
    return TokenUsage(
        input_tokens=inp,
        output_tokens=60,
        reasoning_tokens=None,
        total_tokens=inp + 60,
        raw={"input_tokens": inp, "output_tokens": 60},
        input_source="provider",
        output_source="provider",
    )


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


def test_half_microdollar_boundary(tmp_path: Path) -> None:
    import shutil
    from importlib.resources import files

    defaults = files("mmc.defaults")
    for name in ("models.yaml", "pricing.yaml", "rubric.yaml"):
        shutil.copy(defaults.joinpath(name), tmp_path / name)
    pricing = yaml.safe_load((tmp_path / "pricing.yaml").read_text(encoding="utf-8"))
    pricing["entries"].append(
        {
            "model_key": "mock:half-micro",
            "input_per_mtok": "0.50",
            "output_per_mtok": "0.50",
            "basis": "exact",
            "effective_from": "2026-01-01",
            "source_url": "https://github.com/applycoding/multi-model-compare",
            "retrieved_on": "2026-10-23",
        }
    )
    (tmp_path / "pricing.yaml").write_text(yaml.dump(pricing), encoding="utf-8")
    models = yaml.safe_load((tmp_path / "models.yaml").read_text(encoding="utf-8"))
    models["models"].append(
        {
            "key": "mock:half-micro",
            "provider": "mock",
            "vendor": "openai",
            "model_id": "half-micro",
            "display_name": "Half Micro",
            "supports_temperature": True,
            "mock": {"behavior": "ok", "output_words": 1},
        }
    )
    (tmp_path / "models.yaml").write_text(yaml.dump(models), encoding="utf-8")
    config = load_app_config(tmp_path)
    cost_out = compute_cost("openai:gpt-6-luna", _usage(0, 1), False, config.pricing, date(2026, 10, 23))
    assert cost_out.output_usd == Decimal("0.000001")
    half_in = compute_cost("mock:half-micro", _usage(1, 0), False, config.pricing, date(2026, 10, 23))
    half_out = compute_cost("mock:half-micro", _usage(0, 1), False, config.pricing, date(2026, 10, 23))
    assert half_in.input_usd == Decimal("0.000001")
    assert half_out.output_usd == Decimal("0.000001")
    combined = compute_cost("mock:half-micro", _usage(1, 1), False, config.pricing, date(2026, 10, 23))
    assert combined.total_usd == Decimal("0.000002")


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
    assert base.status == "known"
    assert high.price and high.price.tier == "long_context"
    assert high.status == "estimated"
    total = sum_costs([base, high])
    assert total.estimated is True


def test_flash_effective_boundaries() -> None:
    config = load_app_config(None)
    dec31 = config.pricing.lookup("google:gemini-3.8-flash", date(2026, 12, 31))
    jan1 = config.pricing.lookup("google:gemini-3.8-flash", date(2027, 1, 1))
    assert dec31 and jan1
    assert dec31.input_per_mtok == Decimal("0.75")
    assert jan1.input_per_mtok == Decimal("1.50")


def test_overlapping_pricing_ranges_rejected(tmp_path: Path) -> None:
    import shutil
    from importlib.resources import files

    from mmc.config.yaml_loader import ConfigError

    defaults = files("mmc.defaults")
    for name in ("models.yaml", "pricing.yaml", "rubric.yaml"):
        shutil.copy(defaults.joinpath(name), tmp_path / name)
    pricing = (tmp_path / "pricing.yaml").read_text(encoding="utf-8")
    dup = pricing.replace(
        "effective_from: 2027-01-01",
        "effective_from: 2026-10-01",
        1,
    )
    (tmp_path / "pricing.yaml").write_text(dup, encoding="utf-8")
    with pytest.raises((ConfigError, ValueError), match="overlap"):
        load_app_config(tmp_path)


def test_haiku_from_basis() -> None:
    config = load_app_config(None)
    cost = compute_cost("anthropic:claude-haiku-5-5", _usage(1000, 1000), False, config.pricing, date(2026, 10, 23))
    assert cost.status == "estimated"
    assert any("from-price" in n for n in cost.notes)


def test_scenario_p1_mock_answer_cost_matches_hand_math() -> None:
    table = _load_pricing_table("pricing_v1.yaml")
    usage = _scenario_answer_usage()
    cost = compute_cost("mock:mock-claude", usage, False, table, date(2026, 10, 23))
    inp = Decimal(usage.input_tokens)
    expected = (inp * Decimal("1.00") / Decimal(1_000_000)).quantize(Decimal("0.000001")) + (
        Decimal(60) * Decimal("2.00") / Decimal(1_000_000)
    ).quantize(Decimal("0.000001"))
    assert cost.total_usd == expected
    assert cost.status == "known"


def test_pricing_v2_doubles_mock_contestant_cost_vs_v1() -> None:
    usage = _scenario_answer_usage()
    v1 = _load_pricing_table("pricing_v1.yaml")
    v2 = _load_pricing_table("pricing_v2.yaml")
    c1 = compute_cost("mock:mock-gpt", usage, False, v1, date(2026, 10, 23))
    c2 = compute_cost("mock:mock-gpt", usage, False, v2, date(2026, 10, 23))
    assert c1.total_usd is not None and c2.total_usd is not None
    assert c2.total_usd == c1.total_usd * 2


def _hand_answer_cost(prompt: str, input_per_mtok: Decimal, output_per_mtok: Decimal) -> Decimal:
    inp = _inp_tokens(prompt)
    in_cost = (Decimal(inp) * input_per_mtok / Decimal(1_000_000)).quantize(Decimal("0.000001"))
    out_cost = (Decimal(60) * output_per_mtok / Decimal(1_000_000)).quantize(Decimal("0.000001"))
    return in_cost + out_cost


def _hand_judge_attempt_cost(input_per_mtok: Decimal, output_per_mtok: Decimal) -> Decimal:
    in_cost = (Decimal(1000) * input_per_mtok / Decimal(1_000_000)).quantize(Decimal("0.000001"))
    out_cost = (Decimal(200) * output_per_mtok / Decimal(1_000_000)).quantize(Decimal("0.000001"))
    return in_cost + out_cost


def test_scenario_p1_run_subtotal_four_answers_plus_judge() -> None:
    table = _load_pricing_table("pricing_v1.yaml")
    usage = _scenario_answer_usage()
    answer_cost = compute_cost("mock:mock-claude", usage, False, table, date(2026, 10, 23))
    judge_usage = TokenUsage(
        input_tokens=1000,
        output_tokens=200,
        reasoning_tokens=None,
        total_tokens=1200,
        raw={"input_tokens": 1000, "output_tokens": 200},
        input_source="provider",
        output_source="provider",
    )
    judge_cost = compute_cost("mock:mock-judge", judge_usage, False, table, date(2026, 10, 23))
    costs: list[Cost | None] = [answer_cost] * 4 + [judge_cost]
    total = sum_costs(costs)
    expected_answer = _hand_answer_cost(SCENARIO_P1, Decimal("1.00"), Decimal("2.00"))
    expected_judge = _hand_judge_attempt_cost(Decimal("1.00"), Decimal("2.00"))
    expected_subtotal = expected_answer * 4 + expected_judge
    assert total.subtotal_usd == expected_subtotal
    assert answer_cost.total_usd == expected_answer
    assert judge_cost.total_usd == expected_judge
