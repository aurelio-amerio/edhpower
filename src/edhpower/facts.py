"""DeckFacts: the single cacheable product of parsing, resolving, tagging and fetching."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from edhpower import __version__
from edhpower.decklist import ParsedDeck
from edhpower.profile import CardProfile, build_profile, load_special_behaviours, partition
from edhpower.scryfall import CardData, Resolution
from edhpower.spellbook import ComboData
from edhpower.stats import CurveStats, PriceTotals, color_identity_violations, game_changers, mana_curve, pip_counts, price_totals
from edhpower.tags import TAG_TABLE, TagCache

SCHEMA_VERSION = 3


@dataclass
class FactEntry:
    name: str
    count: int
    is_commander: bool
    as_written: str
    card: CardData
    forge_script: str | None = None


@dataclass
class DeckFacts:
    schema_version: int
    tool_version: str
    source_path: str
    commanders: list[str]
    entries: list[FactEntry]
    unresolved: list[str]
    parse_warnings: list[str]
    parse_errors: list[str]
    curve: CurveStats
    pips: dict[str, int]
    prices: PriceTotals
    game_changers: list[str]
    identity_violations: list[str]
    commander_identity: list[str]
    combos: ComboData | None
    combos_unavailable_reason: str | None
    profiles: dict[str, CardProfile]
    partition: dict[str, list[str]]
    partition_counts: dict[str, int]
    special_hits: list[str]
    untagged: list[str]
    tags_status: str
    fetched: dict[str, str | int | None] = field(default_factory=dict)

    @property
    def total_cards(self) -> int:
        return sum(e.count for e in self.entries)

    @property
    def deck(self) -> list[tuple[CardData, int]]:
        return [(e.card, e.count) for e in self.entries]

    @property
    def library_entries(self) -> list[FactEntry]:
        """Entries that start in the library (everything but the commanders)."""
        return [e for e in self.entries if not e.is_commander]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["combos"] = self.combos.to_dict() if self.combos else None
        d["profiles"] = {k: v.to_dict() for k, v in self.profiles.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeckFacts:
        return cls(
            schema_version=d["schema_version"],
            tool_version=d["tool_version"],
            source_path=d["source_path"],
            commanders=list(d["commanders"]),
            entries=[FactEntry(e["name"], e["count"], e["is_commander"], e["as_written"], CardData.from_dict(e["card"]), e.get("forge_script")) for e in d["entries"]],
            unresolved=list(d["unresolved"]),
            parse_warnings=list(d["parse_warnings"]),
            parse_errors=list(d["parse_errors"]),
            curve=CurveStats(**d["curve"]),
            pips=dict(d["pips"]),
            prices=PriceTotals(**d["prices"]),
            game_changers=list(d["game_changers"]),
            identity_violations=list(d["identity_violations"]),
            commander_identity=list(d["commander_identity"]),
            combos=ComboData.from_dict(d["combos"]) if d.get("combos") else None,
            combos_unavailable_reason=d.get("combos_unavailable_reason"),
            profiles={k: CardProfile.from_dict(v) for k, v in d["profiles"].items()},
            partition={k: list(v) for k, v in d["partition"].items()},
            partition_counts=dict(d["partition_counts"]),
            special_hits=list(d["special_hits"]),
            untagged=list(d["untagged"]),
            tags_status=d["tags_status"],
            fetched=dict(d.get("fetched", {})),
        )


def build_facts(
    parsed: ParsedDeck,
    resolution: Resolution,
    combos: ComboData | None,
    combos_unavailable_reason: str | None,
    source_path: str,
    tag_cache: TagCache | None = None,
    tags_unavailable_reason: str | None = None,
    forge_scripts: dict[str, str | None] | None = None,
    forge_commit: str | None = None,
    forge_unavailable_reason: str | None = None,
) -> DeckFacts:
    entries: list[FactEntry] = []
    for e in parsed.entries:
        card = resolution.cards.get(e.name)
        if card is None:
            continue
        entries.append(FactEntry(card.name, e.count, e.is_commander, e.raw, card, (forge_scripts or {}).get(card.name)))

    commanders = [e.name for e in entries if e.is_commander]
    deck = [(e.card, e.count) for e in entries]
    if commanders:
        identity: set[str] = set()
        for e in entries:
            if e.is_commander:
                identity |= set(e.card.color_identity)
        violations = color_identity_violations(deck, identity)
    else:
        identity = set()
        for card, _ in deck:
            identity |= set(card.color_identity)
        violations = []

    tags_ok = tag_cache is not None and tag_cache.complete and tags_unavailable_reason is None
    if tags_ok:
        tags_status = "ok"
    else:
        tags_status = tags_unavailable_reason or ("tag cache incomplete" if tag_cache is not None else "tags not requested")
    specials = load_special_behaviours()
    profiles: dict[str, CardProfile] = {}
    hits: list[str] = []
    for e in entries:
        tags = tag_cache.tags_for(e.name) if tags_ok else ()
        special = specials.get(e.name)
        profiles[e.name] = build_profile(e.card, tags, special, tags_known=tags_ok)
        if special is not None:
            hits.append(f"{e.name} (effects)" if special.kind is None else f"{e.name} ({special.kind}, mana {special.mana})")
    names, counts = partition([(profiles[e.name], e.count) for e in entries])
    tags_oldest, tags_newest = tag_cache.fetched_range() if tags_ok else (None, None)

    fetched: dict[str, str | int | None] = {
        "scryfall_cards_oldest": resolution.fetched_oldest,
        "scryfall_cards_newest": resolution.fetched_newest,
        "scryfall_cards_unknown": resolution.fetched_unknown,
        "spellbook": combos.fetched_at if combos else None,
        "spellbook_api_version": combos.api_version if combos else None,
        "tags_oldest": tags_oldest,
        "tags_newest": tags_newest,
    }
    forge_ok = forge_scripts is not None and forge_unavailable_reason is None
    fetched["forge_commit"] = forge_commit if forge_ok else None
    fetched["forge_status"] = "ok" if forge_ok else (forge_unavailable_reason or "forge not requested")
    if forge_ok:
        fetched["forge_missing"] = ",".join(e.name for e in entries if e.forge_script is None)
    if tags_ok:
        fetched["tag_table"] = ",".join(sorted(TAG_TABLE))

    return DeckFacts(
        schema_version=SCHEMA_VERSION,
        tool_version=__version__,
        source_path=source_path,
        commanders=commanders,
        entries=entries,
        unresolved=list(resolution.unresolved),
        parse_warnings=list(parsed.warnings),
        parse_errors=list(parsed.errors),
        curve=mana_curve(deck),
        pips=pip_counts(deck),
        prices=price_totals(deck),
        game_changers=game_changers(deck),
        identity_violations=violations,
        commander_identity=sorted(identity),
        combos=combos,
        combos_unavailable_reason=combos_unavailable_reason,
        profiles=profiles,
        partition=names,
        partition_counts=counts,
        special_hits=sorted(hits),
        untagged=sorted(names["untagged"]),
        tags_status=tags_status,
        fetched=fetched,
    )


def save_facts(facts: DeckFacts, path: Path) -> None:
    Path(path).write_text(json.dumps(facts.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_facts(path: Path) -> DeckFacts:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    version = d.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"facts schema {version} is not supported by edhpower {__version__} (expected {SCHEMA_VERSION}); regenerate the file with --facts-json")
    return DeckFacts.from_dict(d)
