from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

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
