"""Closed-form mana tipping point: hypergeometric over land classes with bounded deterministic boosts.

A heuristic, stated as one. The whole probability curve is returned so the definition is visible.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from edhpower.config import TippingConfig
from edhpower.facts import DeckFacts

RAMP_KEYS_NON_FAST = ("mana_rocks", "mana_dorks", "land_ramp", "rituals", "other_ramp")


def hypergeom_pmf(N: int, K: int, n: int, k: int) -> float:
    if k < 0 or k > K or n - k < 0 or n - k > N - K:
        return 0.0
    return math.comb(K, k) * math.comb(N - K, n - k) / math.comb(N, n)


def hypergeom_at_least(N: int, K: int, n: int, k: int) -> float:
    return sum(hypergeom_pmf(N, K, n, x) for x in range(max(k, 0), min(K, n) + 1))


def land_mana_probability(deck_size: int, one_mana: int, two_mana: int, seen: int, turn: int, need: float) -> float:
    """P(best `turn` lands among `seen` cards make ≥ `need` mana, with at least one land drawn)."""
    other = deck_size - one_mana - two_mana
    if seen > deck_size or other < 0:
        return 0.0
    denom = math.comb(deck_size, seen)
    p = 0.0
    for a in range(0, min(two_mana, seen) + 1):
        for b in range(0, min(one_mana, seen - a) + 1):
            rest = seen - a - b
            if rest > other or a + b == 0:
                continue
            played_two = min(a, turn)
            played_one = min(b, max(turn - played_two, 0))
            if 2 * played_two + played_one >= need:
                p += math.comb(two_mana, a) * math.comb(one_mana, b) * math.comb(other, rest) / denom
    return min(1.0, p)


@dataclass
class TippingPoint:
    target: int
    functional_avg_mv: float
    turn: int | None
    probability: float
    threshold: float
    max_turn: int
    ramp_boost_from_turn: int
    curve: dict[int, float]
    land_classes: dict[str, int]
    fast_mana: int
    ramp: int
    boosts: dict[str, float]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def tipping_point(facts: DeckFacts, cfg: TippingConfig) -> TippingPoint:
    library = facts.library_entries
    deck_size = sum(e.count for e in library)
    classes = {"one": 0, "two": 0, "utility": 0}
    mv_total = mv_n = 0.0
    heavy_total = heavy_n = 0.0
    for e in library:
        p = facts.profiles[e.name]
        if p.is_land:
            key = "two" if p.land_mana >= 2 else ("one" if p.land_mana == 1 else "utility")
            classes[key] += e.count
            continue
        mv_total += p.cmc * e.count
        mv_n += e.count
        if p.is_creature and p.cmc >= cfg.heavy_creature_mv:
            heavy_total += p.cmc * e.count
            heavy_n += e.count

    notes = ["heuristic: exact hypergeometric over land classes; fast mana and ramp are bounded deterministic boosts; mulligans ignored; enters-tapped lands count as untapped"]
    avg = mv_total / mv_n if mv_n else 3.0
    cheat = facts.partition_counts.get("cheat_into_play", 0)
    if cheat >= cfg.cheat_min and heavy_n >= cfg.heavy_min and mv_n - heavy_n > 0:
        avg = (mv_total - heavy_total) / (mv_n - heavy_n)
        notes.append(f"functional average excludes {int(heavy_n)} heavy creature(s) (MV ≥ {cfg.heavy_creature_mv:g}) because the deck has {cheat} cheat-into-play card(s)")
    target = min(max(_round_half_up(avg), cfg.target_min), cfg.target_max)

    fast = facts.partition_counts.get("fast_mana", 0)
    ramp = sum(facts.partition_counts.get(k, 0) for k in RAMP_KEYS_NON_FAST)
    fast_boost = min(fast * cfg.fast_mana_boost, cfg.fast_mana_boost_max)
    ramp_boost = min(ramp * cfg.ramp_boost, cfg.ramp_boost_max)

    curve: dict[int, float] = {}
    for t in range(1, cfg.max_turn + 1):
        boost = fast_boost + (ramp_boost if t >= cfg.ramp_boost_from_turn else 0.0)
        seen = min(6 + t, deck_size)
        curve[t] = round(land_mana_probability(deck_size, classes["one"], classes["two"], seen, t, target - boost), 6) if deck_size else 0.0
    turn = next((t for t, p in curve.items() if p >= cfg.threshold), None)
    probability = curve[turn] if turn is not None else curve.get(cfg.max_turn, 0.0)
    if turn is None:
        notes.append(f"never reaches {cfg.threshold:.0%} by turn {cfg.max_turn}; probability at turn {cfg.max_turn} reported")
    if classes["utility"]:
        notes.append(f"{classes['utility']} land(s) produce no fixed mana (utility, board-dependent or Eye of Ugin) and count as non-lands here")
    if facts.tags_status != "ok":
        notes.append(
            f"tags unavailable ({facts.tags_status}): ramp and cheat-into-play counts are 0, so this turn is a floor "
            "(later than reality); only lands and fast mana are measured"
        )
    return TippingPoint(target, round(avg, 6), turn, probability, cfg.threshold, cfg.max_turn, cfg.ramp_boost_from_turn, curve, classes, fast, ramp,
                        {"fast_mana": round(fast_boost, 3), "ramp": round(ramp_boost, 3)}, notes)
