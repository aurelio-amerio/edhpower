"""Pure deck statistics over (CardData, count) pairs. No I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from edhpower.scryfall import CardData

Deck = list[tuple[CardData, int]]
_SYMBOL = re.compile(r"\{([^}]+)\}")
BUCKETS = ["0", "1", "2", "3", "4", "5", "6", "7+"]


@dataclass
class CurveStats:
    buckets: dict[str, int]
    nonland_count: int
    land_count: int
    avg_cmc_nonland: float | None
    median_cmc_nonland: float | None


def mana_curve(deck: Deck) -> CurveStats:
    buckets = {b: 0 for b in BUCKETS}
    cmcs: list[float] = []
    lands = 0
    for card, n in deck:
        if card.is_land:
            lands += n
            continue
        key = "7+" if card.cmc >= 7 else str(int(card.cmc))
        buckets[key] += n
        cmcs.extend([card.cmc] * n)
    return CurveStats(
        buckets=buckets,
        nonland_count=len(cmcs),
        land_count=lands,
        avg_cmc_nonland=round(sum(cmcs) / len(cmcs), 3) if cmcs else None,
        median_cmc_nonland=float(median(cmcs)) if cmcs else None,
    )


def pip_counts(deck: Deck) -> dict[str, int]:
    counts = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0, "C": 0, "hybrid": 0}
    for card, n in deck:
        for sym in _SYMBOL.findall(card.mana_cost or ""):
            sym = sym.upper()
            if sym.endswith("/P"):
                sym = sym[:-2]
            if sym in counts:
                counts[sym] += n
            elif "/" in sym:
                counts["hybrid"] += n
    return counts


@dataclass
class PriceTotals:
    usd: float | None
    eur: float | None
    missing_usd: int
    missing_eur: int
    missing_edhrec: int


def price_totals(deck: Deck) -> PriceTotals:
    usd = eur = 0.0
    any_usd = any_eur = False
    miss_usd = miss_eur = miss_rank = 0
    for card, n in deck:
        if card.price_usd is None:
            miss_usd += 1
        else:
            usd += card.price_usd * n
            any_usd = True
        if card.price_eur is None:
            miss_eur += 1
        else:
            eur += card.price_eur * n
            any_eur = True
        if card.edhrec_rank is None:
            miss_rank += 1
    return PriceTotals(round(usd, 2) if any_usd else None, round(eur, 2) if any_eur else None, miss_usd, miss_eur, miss_rank)


def color_identity_violations(deck: Deck, commander_identity: set[str]) -> list[str]:
    return sorted(card.name for card, _ in deck if not set(card.color_identity) <= commander_identity)


def game_changers(deck: Deck) -> list[str]:
    return sorted(card.name for card, _ in deck if card.game_changer)
