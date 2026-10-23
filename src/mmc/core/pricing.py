from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from mmc.config.schemas import PricingTable
from mmc.core.results import Cost, CostTotal, PriceSnapshot, TokenUsage

QUANT = Decimal("0.000001")


def _q(value: Decimal) -> Decimal:
    return value.quantize(QUANT, rounding=ROUND_HALF_UP)


def compute_cost(
    model_key: str,
    usage: TokenUsage,
    billing_estimated: bool,
    table: PricingTable,
    on: date,
) -> Cost:
    entry = table.lookup(model_key, on)
    if entry is None:
        return Cost(
            status="unknown",
            notes=[f"no pricing entry for {model_key} on {on.isoformat()}"],
        )
    tier = "base"
    in_price = entry.input_per_mtok
    out_price = entry.output_per_mtok
    notes: list[str] = []
    if entry.long_context and usage.input_tokens > entry.long_context.above_input_tokens:
        tier = "long_context"
        in_price = entry.long_context.input_per_mtok
        out_price = entry.long_context.output_per_mtok
        notes.append("long-context tier (estimated for Grok >200k)")
    if entry.basis == "from":
        notes.append("from-price (tiered)")
    token_estimated = usage.input_source == "estimated" or usage.output_source == "estimated"
    if billing_estimated:
        notes.append("xai reasoning billing unverified")
    if token_estimated:
        notes.append("estimated tokens")
    status = "known"
    if token_estimated or billing_estimated or entry.basis == "from":
        status = "estimated"
    input_usd = _q(Decimal(usage.input_tokens) * in_price / Decimal(1_000_000))
    output_usd = _q(Decimal(usage.output_tokens) * out_price / Decimal(1_000_000))
    total_usd = input_usd + output_usd
    return Cost(
        status=status,
        input_usd=input_usd,
        output_usd=output_usd,
        total_usd=total_usd,
        price=PriceSnapshot(entry=entry, tier=tier, pricing_version=table.version),
        notes=notes,
    )


def sum_costs(costs: Iterable[Cost | None]) -> CostTotal:
    subtotal = Decimal(0)
    estimated = False
    unknown = 0
    for cost in costs:
        if cost is None:
            continue
        if cost.status == "unknown":
            unknown += 1
            continue
        if cost.total_usd is not None:
            subtotal += cost.total_usd
        if cost.status == "estimated":
            estimated = True
    return CostTotal(subtotal_usd=subtotal, estimated=estimated, unknown_count=unknown)
