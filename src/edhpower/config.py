"""Typed loader for data/scoring.toml. The only module that reads it."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from importlib import resources
from typing import Any

COMPONENT_NAMES: tuple[str, ...] = ("fast_mana", "tutors", "interaction", "card_advantage", "combos", "curve")
PAYOFF_CATEGORIES: tuple[str, ...] = ("mana_sink", "drain", "etb_damage", "go_wide", "token_drain", "counter_win",
                                      "cast_damage", "empty_library_win", "life_drain", "landfall_payoff", "landfall_tokens")


@dataclass(frozen=True)
class CurveProfile:
    name: str
    source: str
    land: float
    reserved: float
    favor_price: float
    power_curve: tuple[float, ...]
    pop_curve: tuple[float, ...]
    price_curve: tuple[float, ...]
    bracket_curve: tuple[float, ...]
    cmc_floor: float
    cmc_ceiling: float
    efficiency_limits: tuple[float, float]
    basic_land_impact: float
    tipping_share: float


@dataclass(frozen=True)
class Part:
    cap: float
    weight: float


@dataclass(frozen=True)
class ComponentsProfile:
    name: str
    parts: dict[str, Part]
    combo_two_card_value: float
    combo_other_value: float
    curve_avg_mv_best: float
    curve_avg_mv_worst: float
    curve_ramp_cap: float
    curve_ramp_share: float
    archetype: dict[str, float]


@dataclass(frozen=True)
class TippingConfig:
    threshold: float
    fast_mana_boost: float
    fast_mana_boost_max: float
    ramp_boost: float
    ramp_boost_max: float
    ramp_boost_from_turn: int
    max_turn: int
    target_min: int
    target_max: int
    heavy_creature_mv: float
    cheat_min: int
    heavy_min: int


@dataclass(frozen=True)
class SimConfig:
    version: int
    iterations: int
    max_turn: int
    opening_hand: int
    mulligan_min_lands: int
    mulligan_max_lands: int
    mana_threshold: int
    threat_mv: int
    life_per_opponent: int
    opponents: int
    metalcraft_count: int
    max_two_card_lines: int
    max_three_card_lines: int
    mass_return_min_lands: int
    lethal_features: tuple[str, ...]
    payoff_resources: tuple[tuple[str, re.Pattern[str]], ...]
    payoff_converts: dict[str, tuple[str, ...]]
    payoff_chained: dict[str, tuple[str, ...]]
    payoff_hand_ok: frozenset[str]
    lock_only: re.Pattern[str]


@dataclass(frozen=True)
class ForgeConfig:
    commit: str
    min_interval: float


@dataclass(frozen=True)
class NarrativeConfig:
    lowest_components: int
    scorer_gap: float
    idle_share: float
    unmodelled_share: float


@dataclass(frozen=True)
class ScoringConfig:
    config_version: int
    curve: CurveProfile
    components: ComponentsProfile
    tipping: TippingConfig
    sim: SimConfig
    narrative: NarrativeConfig
    forge: ForgeConfig

    def stamp(self) -> dict[str, Any]:
        return {
            "config_version": self.config_version,
            "curve_profile": self.curve.name,
            "components_profile": self.components.name,
            "sim_version": self.sim.version,
        }


def _curve_from(name: str, raw: dict[str, Any]) -> CurveProfile:
    return CurveProfile(
        name=name,
        source=str(raw["source"]),
        land=float(raw["land"]),
        reserved=float(raw["reserved"]),
        favor_price=float(raw["favor_price"]),
        power_curve=tuple(float(x) for x in raw["power_curve"]),
        pop_curve=tuple(float(x) for x in raw["pop_curve"]),
        price_curve=tuple(float(x) for x in raw["price_curve"]),
        bracket_curve=tuple(float(x) for x in raw["bracket_curve"]),
        cmc_floor=float(raw["cmc_floor"]),
        cmc_ceiling=float(raw["cmc_ceiling"]),
        efficiency_limits=(float(raw["efficiency_limits"][0]), float(raw["efficiency_limits"][1])),
        basic_land_impact=float(raw["basic_land_impact"]),
        tipping_share=float(raw["tipping_share"]),
    )


def _components_from(name: str, raw: dict[str, Any]) -> ComponentsProfile:
    parts = {k: Part(float(v["cap"]), float(v["weight"])) for k, v in raw["parts"].items()}
    missing = set(COMPONENT_NAMES) - set(parts)
    if missing:
        raise ValueError(f"components profile '{name}' lacks parts: {sorted(missing)}")
    total = sum(p.weight for p in parts.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"components profile '{name}': weights sum to {total}, expected 1.0")
    return ComponentsProfile(
        name=name,
        parts=parts,
        combo_two_card_value=float(raw["combo_two_card_value"]),
        combo_other_value=float(raw["combo_other_value"]),
        curve_avg_mv_best=float(raw["curve_avg_mv_best"]),
        curve_avg_mv_worst=float(raw["curve_avg_mv_worst"]),
        curve_ramp_cap=float(raw["curve_ramp_cap"]),
        curve_ramp_share=float(raw["curve_ramp_share"]),
        archetype={k: float(v) for k, v in raw["archetype"].items()},
    )


def _tipping_from(raw: dict[str, Any]) -> TippingConfig:
    return TippingConfig(
        threshold=float(raw["threshold"]),
        fast_mana_boost=float(raw["fast_mana_boost"]),
        fast_mana_boost_max=float(raw["fast_mana_boost_max"]),
        ramp_boost=float(raw["ramp_boost"]),
        ramp_boost_max=float(raw["ramp_boost_max"]),
        ramp_boost_from_turn=int(raw["ramp_boost_from_turn"]),
        max_turn=int(raw["max_turn"]),
        target_min=int(raw["target_min"]),
        target_max=int(raw["target_max"]),
        heavy_creature_mv=float(raw["heavy_creature_mv"]),
        cheat_min=int(raw["cheat_min"]),
        heavy_min=int(raw["heavy_min"]),
    )


def _pattern(text: str, where: str) -> re.Pattern[str]:
    try:
        return re.compile(text, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"bad payoff pattern in {where}: {e}") from e


def _payoffs_from(raw: dict[str, Any]) -> dict[str, Any]:
    resources = tuple((str(r["resource"]), _pattern(str(r["pattern"]), f"resource '{r['resource']}'")) for r in raw["resources"])
    known = {r for r, _ in resources}
    converts: dict[str, tuple[str, ...]] = {}
    for res, cats in raw["converts"].items():
        if res not in known:
            raise ValueError(f"payoff converts: unknown resource '{res}'")
        for c in cats:
            if c not in PAYOFF_CATEGORIES:
                raise ValueError(f"payoff converts '{res}': unknown payoff category '{c}'")
        converts[str(res)] = tuple(str(c) for c in cats)
    chained: dict[str, tuple[str, ...]] = {}
    for cat, targets in raw["chained"].items():
        if cat not in PAYOFF_CATEGORIES or any(t not in PAYOFF_CATEGORIES for t in targets):
            raise ValueError(f"payoff chained '{cat}': unknown payoff category")
        chained[str(cat)] = tuple(str(t) for t in targets)
    hand_ok = frozenset(str(r) for r in raw["zones"]["hand_ok"])
    if not hand_ok <= known:
        raise ValueError(f"payoff hand_ok names unknown resources: {sorted(hand_ok - known)}")
    return {
        "payoff_resources": resources,
        "payoff_converts": converts,
        "payoff_chained": chained,
        "payoff_hand_ok": hand_ok,
        "lock_only": _pattern(str(raw["zones"]["lock_only"]), "lock_only"),
    }


def _sim_from(raw: dict[str, Any]) -> SimConfig:
    return SimConfig(
        version=int(raw["version"]),
        iterations=int(raw["iterations"]),
        max_turn=int(raw["max_turn"]),
        opening_hand=int(raw["opening_hand"]),
        mulligan_min_lands=int(raw["mulligan_min_lands"]),
        mulligan_max_lands=int(raw["mulligan_max_lands"]),
        mana_threshold=int(raw["mana_threshold"]),
        threat_mv=int(raw["threat_mv"]),
        life_per_opponent=int(raw["life_per_opponent"]),
        opponents=int(raw["opponents"]),
        metalcraft_count=int(raw["metalcraft_count"]),
        max_two_card_lines=int(raw["max_two_card_lines"]),
        max_three_card_lines=int(raw["max_three_card_lines"]),
        mass_return_min_lands=int(raw["mass_return_min_lands"]),
        lethal_features=tuple(str(f).lower() for f in raw["lethal_features"]),
        **_payoffs_from(raw["payoffs"]),
    )


def _narrative_from(raw: dict[str, Any]) -> NarrativeConfig:
    return NarrativeConfig(
        lowest_components=int(raw["lowest_components"]),
        scorer_gap=float(raw["scorer_gap"]),
        idle_share=float(raw["idle_share"]),
        unmodelled_share=float(raw["unmodelled_share"]),
    )


def _forge_from(raw: dict[str, Any]) -> ForgeConfig:
    commit = str(raw["commit"])
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"[forge] commit must be a 40-character hex sha, got '{commit}'")
    return ForgeConfig(commit=commit, min_interval=float(raw["min_interval"]))


def load_config(curve_profile: str | None = None, components_profile: str | None = None) -> ScoringConfig:
    with resources.files("edhpower.data").joinpath("scoring.toml").open("rb") as fh:
        raw = tomllib.load(fh)
    curve_name = curve_profile or raw["default_curve_profile"]
    comp_name = components_profile or raw["default_components_profile"]
    if curve_name not in raw["curve"]:
        raise ValueError(f"unknown curve profile '{curve_name}'; available: {sorted(raw['curve'])}")
    if comp_name not in raw["components"]:
        raise ValueError(f"unknown components profile '{comp_name}'; available: {sorted(raw['components'])}")
    return ScoringConfig(
        config_version=int(raw["config_version"]),
        curve=_curve_from(curve_name, raw["curve"][curve_name]),
        components=_components_from(comp_name, raw["components"][comp_name]),
        tipping=_tipping_from(raw["tipping"]),
        sim=_sim_from(raw["sim"]),
        narrative=_narrative_from(raw["narrative"]),
        forge=_forge_from(raw["forge"]),
    )
