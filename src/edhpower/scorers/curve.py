"""Curve model: a faithful port of edhpowerlevel.com's client-side score (constants in scoring.toml).

Kept on purpose, because deltas against the site must stay attributable: the interpolation helper's
unscaled intra-segment fraction and its zero at the last breakpoint; modal DFCs treated as lands;
the unclamped efficiency multiplier. Not replicated: the site's per-card override list. An unranked
card (missing `edhrec_rank`) scores 0 popularity impact on the site too — `popCurve[10] - false ==
popCurve[10]`, the top breakpoint, which `de` maps to 0 via the same last-breakpoint quirk this module
reproduces — so there is no delta to attribute there; what we add is counting and surfacing how many
cards were missing a rank, which the site does not do.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from edhpower.config import CurveProfile
from edhpower.facts import DeckFacts

BASIC_LAND_NAMES = frozenset({
    "Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp", "Snow-Covered Mountain", "Snow-Covered Forest", "Snow-Covered Wastes",
})


def interpolate(value: float | None, curve: tuple[float, ...], step: float = 1.0) -> float:
    """Port of the site's `de(t, s, o)`, quirks included (see module docstring)."""
    if not curve:
        return 0.0
    if value is None or value <= curve[0]:
        return 0.0
    if value > curve[-1]:
        return (len(curve) - 1) * step
    for i in range(len(curve) - 1):
        if curve[i] <= value < curve[i + 1]:
            return i * step + (value - curve[i]) / (curve[i + 1] - curve[i])
    return 0.0


@dataclass(frozen=True)
class CardImpact:
    name: str
    count: int
    price_usd: float | None
    edhrec_rank: int | None
    price_part: float
    pop_part: float
    impact: float
    bucket: int
    is_land: bool


@dataclass
class CurveScore:
    profile: str
    total_impact: float
    nonland_impact: float
    avg_cmc: float
    tipping_bucket: int
    tipping_share: float
    efficiency: float
    power_level: float
    bracket_estimate: int | None
    missing_price: int
    missing_rank: int
    cards: list[CardImpact]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_curve(facts: DeckFacts, prof: CurveProfile) -> CurveScore:
    cards: list[CardImpact] = []
    buckets: dict[int, float] = {}
    total = nonland_total = cmc_sum = 0.0
    nonland_n = miss_price = miss_rank = 0
    reserved_scaled = 0

    for e in facts.entries:
        c = e.card
        price = c.price_usd
        if price is None:
            miss_price += 1
        elif c.reserved:
            price = price * prof.reserved
            reserved_scaled += 1
        rank = c.edhrec_rank
        if rank is None:
            miss_rank += 1
        price_part = interpolate(price, prof.price_curve, 1 + prof.favor_price)
        pop_part = interpolate(prof.pop_curve[-1] - rank, prof.pop_curve, 1 - prof.favor_price) if rank is not None else 0.0
        impact = (price_part + pop_part) * e.count
        is_land = c.is_land or c.layout == "modal_dfc"
        if is_land:
            impact *= prof.land
            bucket = 0
        else:
            bucket = int(c.cmc)
            cmc_sum += c.cmc * e.count
            nonland_n += e.count
        if c.name in BASIC_LAND_NAMES:
            impact = prof.basic_land_impact * e.count
        total += impact
        if not is_land:
            buckets[bucket] = buckets.get(bucket, 0.0) + impact
            nonland_total += impact
        cards.append(CardImpact(c.name, e.count, c.price_usd, rank, round(price_part, 4), round(pop_part, 4), round(impact, 4), bucket, is_land))

    avg_cmc = round(cmc_sum / nonland_n, 2) if nonland_n else 0.0
    tipping_bucket = 0
    running = 0.0
    for b in sorted(buckets):
        running += buckets[b]
        if running > nonland_total * prof.tipping_share:
            tipping_bucket = b
            break
    g = (avg_cmc + tipping_bucket) / 2
    lo, hi = prof.efficiency_limits
    efficiency = lo + (hi - lo) * (prof.cmc_ceiling - g) / (prof.cmc_ceiling - prof.cmc_floor)
    power = interpolate(total * efficiency, prof.power_curve)
    bracket = max(1, math.ceil(interpolate(power, prof.bracket_curve))) if power > 0 else None

    notes = [
        "price input is Scryfall USD for the default printing; the site uses TCGplayer market prices — expect a vendor delta",
        f"modal DFCs count as lands (×{prof.land:g}, MV 0) because the site does",
        "efficiency is not clamped to the profile limits, matching the site",
        "the site's per-card override list (81 entries: free-spell MV, fetchland producers, commander impact) is not reproduced",
    ]
    if miss_price:
        notes.append(f"{miss_price} card(s) without a USD price contribute 0 price impact")
    if miss_rank:
        notes.append(
            f"{miss_rank} card(s) without an EDHREC rank contribute 0 popularity impact "
            "(the site scores them 0 too, via the same last-breakpoint quirk; it just doesn't surface the count)"
        )
    if reserved_scaled:
        notes.append(f"reserved-list card prices are scaled ×{prof.reserved:g} before the price curve, matching the site")
    if prof.bracket_curve and power >= prof.bracket_curve[-1]:
        notes.append(
            "power is at or above the last bracket breakpoint; the site's interpolation returns 0 there, "
            "so the bracket estimate reads 1 — read a power of 10 as bracket 5"
        )
    cards.sort(key=lambda ci: (-ci.impact, ci.name))
    return CurveScore(
        profile=prof.name,
        total_impact=round(total, 4),
        nonland_impact=round(nonland_total, 4),
        avg_cmc=avg_cmc,
        tipping_bucket=tipping_bucket,
        tipping_share=prof.tipping_share,
        efficiency=round(efficiency, 6),
        power_level=round(power, 4),
        bracket_estimate=bracket,
        missing_price=miss_price,
        missing_rank=miss_rank,
        cards=cards,
        notes=notes,
    )
