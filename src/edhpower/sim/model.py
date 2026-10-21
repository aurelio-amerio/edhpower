"""SimCard: what one game needs to know about a card. Built from CardProfile, CardData and
special_behaviours params. No card names appear in this module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from edhpower.config import SimConfig
from edhpower.facts import DeckFacts
from edhpower.profile import CardProfile, SpecialBehaviour, load_special_behaviours
from edhpower.scryfall import CardData
from edhpower.sim.effects import CardEffects, Effect, effects_for
from edhpower.sim.mana import ANY_COLOR, COLORLESS, ManaCost, parse_cost

ROLES: tuple[str, ...] = ("land", "one_shot", "rock", "dork", "reducer", "ramp_spell", "draw_spell", "tutor",
                          "threat", "creature", "engine", "permanent", "held", "token")


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
    effects: tuple[Effect, ...] = ()
    ramp_to_battlefield: int = 1
    ramp_to_hand: int = 0
    ramp_sacrifice_lands: int = 0


@dataclass(frozen=True)
class SimDeck:
    cards: dict[str, SimCard]
    library: tuple[str, ...]
    commanders: tuple[SimCard, ...]
    commander_subtypes: frozenset[str]
    coverage: dict[str, int]
    notes: list[str] = field(default_factory=list)
    effects_sources: dict[str, list[str]] = field(default_factory=dict)
    unmodelled: tuple[str, ...] = ()
    partial: tuple[str, ...] = ()


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


def token_card(type_: str, power: int, toughness: int) -> SimCard:
    """A creature token as a SimCard, so the engine can hold it in the same structures as any creature."""
    del toughness   # the engine only needs power; toughness is tracked on the board
    return SimCard(
        name=f"{type_} token", is_land=False, is_creature=True, is_artifact=False, is_eldrazi=False, is_colorless=False,
        is_spell=False, subtypes=frozenset(type_.split()), cmc=0.0, cost=parse_cost(""), power=power, produces=frozenset(),
        mana=0, role="token", reduction=0, reduction_scope="", enters_tapped=False, special=None, params={}, draw=0,
    )


def build_card(p: CardProfile, card: CardData, special: SpecialBehaviour | None, tags_ok: bool, cfg: SimConfig,
               script: str | None = None) -> SimCard:
    return _build_card(p, card, special, tags_ok, cfg, effects_for(card, script, special))


def _build_card(p: CardProfile, card: CardData, special: SpecialBehaviour | None, tags_ok: bool, cfg: SimConfig,
                fx: CardEffects) -> SimCard:
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
        effects=fx.effects,
        ramp_to_battlefield=fx.ramp_to_battlefield,
        ramp_to_hand=fx.ramp_to_hand,
        ramp_sacrifice_lands=fx.ramp_sacrifice_lands,
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
    sources: dict[str, list[str]] = {"table": [], "forge": [], "none": []}
    unmodelled: list[str] = []
    partial: list[str] = []
    never_cast = 0   # held spells with no `cast` effect (pump spells are cast for lethal, so not counted)
    for e in facts.entries:
        special = specials.get(e.name)
        fx = effects_for(e.card, e.forge_script, special)
        sc = _build_card(facts.profiles[e.name], e.card, special, tags_ok, cfg, fx)
        cards[e.name] = sc
        if e.is_commander:
            commanders.append(sc)
        else:
            library.extend([e.name] * e.count)
            coverage[sc.role] += e.count
            if sc.role == "held" and not any(x.on == "cast" for x in sc.effects):
                never_cast += e.count
            if not sc.is_land:
                sources[fx.source].append(e.name)
                if fx.source != "table" and not fx.effects and (fx.unread or fx.source == "none"):
                    unmodelled.append(e.name)
                if fx.effects and fx.unread:
                    partial.append(e.name)
    subtypes: frozenset[str] = frozenset()
    for c in commanders:
        subtypes |= c.subtypes
    notes: list[str] = []
    if not tags_ok:
        notes.append(f"tags unavailable ({facts.tags_status}): tutors and land-ramp spells are not modelled, so every clock is a floor (later than reality)")
    if never_cast:
        notes.append(f"{never_cast} instant/sorcery card(s) with no modelled effect are never cast (a goldfish has nothing to interact with)")
    if unmodelled:
        notes.append(f"{len(unmodelled)} nonland card(s) have script lines the model does not read: {sorted(unmodelled)[:4]}…")
    if partial:
        notes.append(f"{len(partial)} card(s) modelled in part (a mode or branch is skipped): {sorted(partial)[:4]}…")
    status = facts.fetched.get("forge_status")
    if status != "ok":
        notes.append(f"Forge scripts unavailable ({status}): effects come from the behaviours table only")
    # Sorted so the library's initial order — and therefore every shuffle — is independent of decklist order.
    return SimDeck(cards, tuple(sorted(library)), tuple(commanders), subtypes, coverage, notes,
                   {k: sorted(v) for k, v in sources.items()}, tuple(sorted(unmodelled)), tuple(sorted(partial)))
