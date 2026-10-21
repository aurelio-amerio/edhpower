"""CardProfile: what the scorers, tipping point and simulator know about one card.

Sources, in precedence order for mana behaviour: the explicit special_behaviours table, then the
numeric extractor, then Scryfall fields. Categorical facts come from oracle tags.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from importlib import resources
from typing import TYPE_CHECKING, Any

from edhpower.extract import OracleNumbers, extract
from edhpower.scryfall import CardData

if TYPE_CHECKING:
    from edhpower.sim.effects import Effect

FAST_MANA_MAX_MV = 2


@dataclass(frozen=True)
class SpecialBehaviour:
    name: str
    kind: str | None  # None for an effects-only entry
    mana: int
    params: dict[str, Any] = field(default_factory=dict)
    note: str = ""
    effects: tuple[Effect, ...] = ()


def special_behaviours_from(raw: dict[str, Any]) -> dict[str, SpecialBehaviour]:
    # Imported here: edhpower.sim imports facts, which imports this module.
    from edhpower.sim.effects import parse_effects_table

    table: dict[str, SpecialBehaviour] = {}
    for name, entry in raw["cards"].items():
        if "kind" not in entry and "effects" not in entry:
            raise ValueError(f"special behaviour {name!r} has neither kind nor effects")
        params = {k: v for k, v in entry.items() if k not in ("kind", "mana", "note", "effects")}
        kind = str(entry["kind"]) if "kind" in entry else None
        effects = parse_effects_table(entry.get("effects", []))
        table[name] = SpecialBehaviour(name, kind, int(entry.get("mana", 0)), params, str(entry.get("note", "")), effects)
    return table


def load_special_behaviours() -> dict[str, SpecialBehaviour]:
    with resources.files("edhpower.data").joinpath("special_behaviours.toml").open("rb") as fh:
        return special_behaviours_from(tomllib.load(fh))


@dataclass(frozen=True)
class CardProfile:
    name: str
    tags: tuple[str, ...]
    is_land: bool
    is_basic_land: bool
    is_creature: bool
    is_eldrazi: bool
    cmc: float
    mana_per_activation: int
    mana_colors: tuple[str, ...]
    repeatable_mana: bool
    board_dependent_mana: bool
    land_mana: int
    is_fast_mana: bool
    cost_reduction: int
    cost_reduction_scope: str
    draw_count: int
    enters_tapped: bool
    special: str | None
    untagged: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CardProfile:
        d = dict(d)
        d["tags"] = tuple(d.get("tags", ()))
        d["mana_colors"] = tuple(d.get("mana_colors", ()))
        return cls(**d)


def is_fast_mana(card: CardData, numbers: OracleNumbers, special: SpecialBehaviour | None) -> bool:
    if card.is_land or card.cmc > FAST_MANA_MAX_MV or numbers.enters_tapped:
        return False
    if "Creature" in card.front_type_line and "Haste" not in card.keywords:
        return False
    mana = special.mana if special is not None and special.kind == "rock" else numbers.mana_per_activation
    return mana > 0 and mana >= card.cmc


def _land_mana(card: CardData, numbers: OracleNumbers, special: SpecialBehaviour | None) -> int:
    if not card.is_land:
        return 0
    if special is not None and special.kind == "land":
        return special.mana
    if numbers.board_dependent:
        return 0
    if numbers.mana_per_activation >= 2:
        return 2
    return 1 if (numbers.mana_per_activation == 1 or card.produced_mana) else 0


def build_profile(card: CardData, tags: tuple[str, ...], special: SpecialBehaviour | None, tags_known: bool) -> CardProfile:
    numbers = extract(card.oracle_text, card.type_line)
    front = card.front_type_line
    return CardProfile(
        name=card.name,
        tags=tuple(tags),
        is_land=card.is_land,
        is_basic_land=card.is_basic_land,
        is_creature="Creature" in front,
        is_eldrazi="Eldrazi" in card.type_line,
        cmc=card.cmc,
        mana_per_activation=numbers.mana_per_activation,
        mana_colors=numbers.mana_colors,
        repeatable_mana=numbers.repeatable,
        board_dependent_mana=numbers.board_dependent,
        land_mana=_land_mana(card, numbers, special),
        is_fast_mana=is_fast_mana(card, numbers, special),
        cost_reduction=numbers.cost_reduction,
        cost_reduction_scope=numbers.cost_reduction_scope,
        draw_count=numbers.draw_count,
        enters_tapped=numbers.enters_tapped,
        special=special.kind if special is not None else None,
        untagged=bool(tags_known and not tags and not card.is_land),
    )


PARTITION_KEYS: tuple[str, ...] = (
    "lands", "fast_mana", "mana_rocks", "mana_dorks", "land_ramp", "rituals", "other_ramp", "cost_reducers",
    "tutors", "counterspells", "board_wipes", "removal", "cantrips", "card_advantage",
    "extra_turns", "mass_land_denial", "pitch_spells", "stax",
    "reanimate", "cheat_into_play", "extra_combat", "copy_spell", "creatures", "untagged",
)


def _keys_for(p: CardProfile) -> list[str]:
    t = set(p.tags)
    keys: list[str] = []
    if p.is_land:
        keys.append("lands")
    elif p.is_fast_mana:
        keys.append("fast_mana")
    elif "mana-rock" in t:
        keys.append("mana_rocks")
    elif "mana-dork" in t:
        keys.append("mana_dorks")
    elif "land-ramp" in t:
        keys.append("land_ramp")
    elif "ritual" in t:
        keys.append("rituals")
    elif "ramp" in t:
        keys.append("other_ramp")
    if "cost-reducer" in t or p.cost_reduction > 0:
        keys.append("cost_reducers")
    if "tutor" in t:
        keys.append("tutors")
    if "counterspell" in t:
        keys.append("counterspells")
    elif "board-wipe" in t:
        keys.append("board_wipes")
    elif "removal" in t:
        keys.append("removal")
    if "cantrip" in t:
        keys.append("cantrips")
    elif "card-advantage" in t:
        keys.append("card_advantage")
    for tag, key in (("extra-turn", "extra_turns"), ("mass-land-denial", "mass_land_denial"), ("pitch-spell", "pitch_spells"),
                     ("reanimate", "reanimate"), ("cheat-into-play", "cheat_into_play"), ("extra-combat", "extra_combat"), ("copy-spell", "copy_spell")):
        if tag in t:
            keys.append(key)
    if "tax" in t or "hatebear" in t:
        keys.append("stax")
    if p.is_creature:
        keys.append("creatures")
    if p.untagged:
        keys.append("untagged")
    return keys


def partition(profiles: list[tuple[CardProfile, int]]) -> tuple[dict[str, list[str]], dict[str, int]]:
    names: dict[str, list[str]] = {k: [] for k in PARTITION_KEYS}
    counts: dict[str, int] = {k: 0 for k in PARTITION_KEYS}
    for p, n in profiles:
        for key in _keys_for(p):
            names[key].append(p.name)
            counts[key] += n
    for key in names:
        names[key].sort()
    return names, counts
