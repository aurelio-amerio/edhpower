"""Cache ages and staleness warnings derived from DeckFacts.fetched. Computes nothing else."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from edhpower.facts import DeckFacts

THRESHOLDS_DAYS: dict[str, int] = {"scryfall_cards": 7, "tags": 30}
_STAMP_KEYS = {"scryfall_cards": "scryfall_cards_oldest", "tags": "tags_oldest", "spellbook": "spellbook"}
_LABELS = {"scryfall_cards": "card cache (prices, ranks, Game Changer flags)", "tags": "tag cache", "spellbook": "Spellbook data"}


@dataclass
class Freshness:
    ages_days: dict[str, float | None]
    warnings: list[str]
    now: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse(stamp: Any) -> datetime | None:
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def assess_freshness(facts: DeckFacts, now: datetime | None = None) -> Freshness:
    now = now or datetime.now(UTC)
    ages: dict[str, float | None] = {}
    warnings: list[str] = []
    for key, stamp_key in _STAMP_KEYS.items():
        when = _parse(facts.fetched.get(stamp_key))
        age = round((now - when).total_seconds() / 86400, 3) if when else None
        ages[key] = age
        limit = THRESHOLDS_DAYS.get(key)
        if age is None:
            if key in THRESHOLDS_DAYS:
                warnings.append(f"{_LABELS[key]} has no fetch date; age unknown")
        elif limit is not None and age > limit:
            warnings.append(f"{_LABELS[key]} is {age:.1f} days old (oldest card/tag used); warning threshold is {limit} days")
    unknown = facts.fetched.get("scryfall_cards_unknown") or 0
    if isinstance(unknown, int) and unknown > 0:
        warnings.append(f"{unknown} cached card(s) carry no fetch date (cached before per-card stamping); delete their lines from cards.jsonl to refresh")
    return Freshness(ages, warnings, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
