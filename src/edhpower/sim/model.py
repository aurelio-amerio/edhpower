"""SimCard: what one game needs to know about a card. Built from CardProfile, CardData and
special_behaviours params. No card names appear in this module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from edhpower.config import SimConfig
from edhpower.facts import DeckFacts
from edhpower.profile import CardProfile, SpecialBehaviour, load_special_behaviours
from edhpower.scryfall import CardData
from edhpower.sim.mana import ANY_COLOR, COLORLESS, ManaCost, parse_cost

ROLES: tuple[str, ...] = ("land", "one_shot", "rock", "dork", "reducer", "ramp_spell", "draw_spell", "tutor",
                          "threat", "creature", "engine", "permanent", "held")


@dataclass(frozen=True)
class SimCard:
    name: str
    is_land: bool
    is_creature: bool
    is_artifact: bool
    is_eldrazi: bool
    is_colorless: bool
    is_spell: bool
    subtypes: frozenset[str]
    cmc: float
    cost: ManaCost
    power: int
    produces: frozenset[str]
    mana: int
    role: str
    reduction: int
    reduction_scope: str
    enters_tapped: bool
    special: str | None
    params: dict[str, Any]
    draw: int


@dataclass(frozen=True)
class SimDeck:
    cards: dict[str, SimCard]
    library: tuple[str, ...]
    commanders: tuple[SimCard, ...]
    commander_subtypes: frozenset[str]
    coverage: dict[str, int]
    notes: list[str] = field(default_factory=list)


def sources_of(profile_colors: tuple[str, ...], produced_mana: tuple[str, ...]) -> frozenset[str]:
    if "any" in profile_colors:
        return ANY_COLOR
    letters = frozenset(c for c in profile_colors if c in ANY_COLOR or c == "C")
    if letters:
        return letters
    produced = frozenset(c for c in produced_mana if c in ANY_COLOR or c == "C")
    return produced or COLORLESS


def _subtypes(type_line: str) -> frozenset[str]:
    front = type_line.split(" // ", 1)[0]
    if "—" not in front:
        return frozenset()
    return frozenset(front.split("—", 1)[1].split())


def _power(value: str | None) -> int:
    try:
        return max(int(value), 0) if value is not None else 0
    except ValueError:
        return 0   # "*" and friends


def _role(p: CardProfile, card: CardData, special: SpecialBehaviour | None, is_spell: bool, tags_ok: bool, cfg: SimConfig) -> str:
    tags = set(p.tags) if tags_ok else set()
    if p.is_land:
        return "land"
    if special is not None and special.kind in ("untap", "doubler"):
        return "engine"
    if special is not None and special.kind == "rock":
        return "rock"
    if p.mana_per_activation > 0 and p.repeatable_mana:
        return "dork" if p.is_creature else "rock"
    if p.mana_per_activation > 0:
        return "one_shot"
    if p.cost_reduction > 0 and not is_spell:
        return "reducer"
    if "land-ramp" in tags and is_spell:
        return "ramp_spell"
    if p.draw_count > 0 and is_spell:
        return "draw_spell"
    if "tutor" in tags and is_spell:
        return "tutor"
    if p.cmc >= cfg.threat_mv:
        return "threat"
    if p.is_creature:
        return "creature"
    if is_spell:
        return "held"
    return "permanent"


def build_card(p: CardProfile, card: CardData, special: SpecialBehaviour | None, tags_ok: bool, cfg: SimConfig) -> SimCard:
    front = card.front_type_line
    is_spell = "Instant" in front or "Sorcery" in front
    role = _role(p, card, special, is_spell, tags_ok, cfg)
    if p.is_land:
        mana, produces = p.land_mana, sources_of((), card.produced_mana)
    elif special is not None and special.kind == "rock":
        mana, produces = special.mana, sources_of(p.mana_colors, card.produced_mana)
    else:
        mana, produces = p.mana_per_activation, sources_of(p.mana_colors, card.produced_mana)
    if mana == 0 and not p.is_land and role not in ("rock", "dork", "one_shot"):
        produces = frozenset()   # lands keep produced_mana: a creature-scaled land still makes its colour
    return SimCard(
        name=p.name,
        is_land=p.is_land,
        is_creature=p.is_creature,
        is_artifact="Artifact" in front,
        is_eldrazi=p.is_eldrazi,
        is_colorless=not card.colors,
        is_spell=is_spell,
        subtypes=_subtypes(card.type_line),
        cmc=p.cmc,
        cost=parse_cost(card.mana_cost),
        power=_power(card.power),
        produces=produces,
        mana=mana,
        role=role,
        reduction=p.cost_reduction,
        reduction_scope=p.cost_reduction_scope,
        enters_tapped=p.enters_tapped,
        special=special.kind if special is not None else None,
        params=dict(special.params) if special is not None else {},
        draw=p.draw_count,
    )


def reduction_applies(scope: str, target: SimCard, commander_subtypes: frozenset[str]) -> bool:
    if target.is_land:
        return False
    s = scope.lower()
    checks = (
        ("creature", target.is_creature),
        ("eldrazi", target.is_eldrazi),
        ("colorless", target.is_colorless),
        ("artifact", target.is_artifact),
        ("chosen type", bool(target.subtypes & commander_subtypes)),
        ("instant", target.is_spell),
        ("sorcery", target.is_spell),
    )
    return all(ok for word, ok in checks if word in s)


def build_sim_deck(facts: DeckFacts, cfg: SimConfig) -> SimDeck:
    specials = load_special_behaviours()
    tags_ok = facts.tags_status == "ok"
    cards: dict[str, SimCard] = {}
    library: list[str] = []
    commanders: list[SimCard] = []
    coverage = {r: 0 for r in ROLES}
    for e in facts.entries:
        sc = build_card(facts.profiles[e.name], e.card, specials.get(e.name), tags_ok, cfg)
        cards[e.name] = sc
        if e.is_commander:
            commanders.append(sc)
        else:
            library.extend([e.name] * e.count)
            coverage[sc.role] += e.count
    subtypes: frozenset[str] = frozenset()
    for c in commanders:
        subtypes |= c.subtypes
    notes: list[str] = []
    if not tags_ok:
        notes.append(f"tags unavailable ({facts.tags_status}): tutors and land-ramp spells are not modelled, so every clock is a floor (later than reality)")
    if coverage["held"]:
        notes.append(f"{coverage['held']} instant/sorcery card(s) with no modelled effect are never cast (a goldfish has nothing to interact with)")
    # Sorted so the library's initial order — and therefore every shuffle — is independent of decklist order.
    return SimDeck(cards, tuple(sorted(library)), tuple(commanders), subtypes, coverage, notes)
