"""Seeded Monte Carlo goldfish simulator driven by CardProfile (Plan C).

simulate(facts, cfg, iterations, tipping_target) is a pure function of DeckFacts and the [sim]
config: the seed is derived from the resolved decklist, every game seeds its own PRNG from
seed + i, and the result carries every number the report prints.
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from dataclasses import asdict, dataclass
from typing import Any

from edhpower.config import SimConfig
from edhpower.facts import DeckFacts
from edhpower.payoffs import DeckPayoffs, detect
from edhpower.sim.combos import SkippedLine, select_lines
from edhpower.sim.engine import CLOCKS, play_game
from edhpower.sim.model import build_sim_deck

# Interactions this stage of the engine does not play (spec: "a `not modelled:` line per stage").
NOT_MODELLED: tuple[str, ...] = ("fetch then dredge in one turn (Gitrog loop)", "Sylvan Library dredges",
                                 "Field of the Dead counting lands that enter with it", "Saga chapters", "attack triggers",
                                 "life as a resource", "Room cards", "blockers/interaction")


@dataclass
class Clock:
    name: str
    label: str
    status: str
    median: int | None
    fast: int | None
    reached: float
    by_turn: dict[int, float]


@dataclass
class SimResult:
    status: str
    sim_version: int
    seed: int
    iterations: int
    max_turn: int
    clocks: dict[str, Clock]
    mana_by_turn: dict[int, float]
    idle_by_turn: dict[int, float]
    lines_simulated: list[str]
    lines_skipped: list[SkippedLine]
    line_status: list[dict[str, Any]]
    payoffs: dict[str, list[str]]
    combos_status: str
    coverage: dict[str, int]
    notes: list[str]
    damage_by_turn: dict[int, float]
    board_power_by_turn: dict[int, float]
    lands_by_turn: dict[int, float]
    landfall_by_turn: dict[int, float]
    graveyard_lands_by_turn: dict[int, float]
    distinct_lands_by_turn: dict[int, float]
    tokens_by_turn: dict[str, dict[int, float]]
    max_swing_median: int
    win_route: dict[str, float]
    effects_sources: dict[str, list[str]]
    unmodelled: list[str]
    partial: list[str]
    nonland_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def deck_seed(facts: DeckFacts) -> int:
    key = json.dumps(sorted((e.name, e.count) for e in facts.entries), ensure_ascii=False)
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


def clock_labels(cfg: SimConfig, tipping_target: int) -> dict[str, str]:
    life = cfg.life_per_opponent
    return {
        "win": "win (table lethal or lethal combo)",
        "lethal_table": f"lethal to the table ({cfg.opponents} \u00d7 {life}, combat and drain)",
        "first_opponent": f"first opponent dead ({life} life, combat and drain)",
        "commander": "commander castable",
        "mana_threshold": f"{cfg.mana_threshold} mana available",
        "tipping_target": f"{tipping_target} mana available (closed-form tipping target)",
        "threat": f"MV {cfg.threat_mv}+ spell cast from hand",
        "combat": f"{life} combat damage to one opponent (no blockers)",
        "combo": "combo line assembled",
        "lethal_combo": "lethal combo line assembled",
        "reanimate": "creature returned from the graveyard to the battlefield",
    }


def _clock(name: str, label: str, turns: list[int | None], max_turn: int, status: str = "ok") -> Clock:
    n = len(turns)
    if status != "ok" or n == 0:
        return Clock(name, label, status, None, None, 0.0, {t: 0.0 for t in range(1, max_turn + 1)})
    padded = [t if t is not None else max_turn + 1 for t in turns]
    med = statistics.median_low(padded)
    by_turn = {t: round(sum(1 for x in padded if x <= t) / n, 6) for t in range(1, max_turn + 1)}
    fast = sorted(padded)[(n + 19) // 20 - 1]   # first turn reached by 5% of games
    return Clock(name, label, status, med if med <= max_turn else None, fast if fast <= max_turn else None, by_turn[max_turn], by_turn)


def _fuel_only(resources: tuple[str, ...], cfg: SimConfig, payoffs: DeckPayoffs) -> list[dict[str, Any]]:
    """Chained (fuel) categories the deck has cards for, whose finisher categories are all empty."""
    out: list[dict[str, Any]] = []
    for r in resources:
        for category in cfg.payoff_converts.get(r, ()):
            targets = cfg.payoff_chained.get(category)
            cards = payoffs.by_category.get(category, [])
            if targets and cards and not payoffs.cards_for(targets):
                out.append({"category": category, "cards": list(cards), "needs": list(targets)})
    return out


def simulate(facts: DeckFacts, cfg: SimConfig, iterations: int, tipping_target: int, payoffs: DeckPayoffs | None = None) -> SimResult:
    payoffs = payoffs if payoffs is not None else detect(facts)
    deck = build_sim_deck(facts, cfg)
    lines, skipped = select_lines(facts, cfg, payoffs)
    seed = deck_seed(facts)
    firsts: dict[str, list[int | None]] = {k: [] for k in CLOCKS}
    mana_sum = [0.0] * (cfg.max_turn + 1)
    idle_sum = [0] * (cfg.max_turn + 1)
    turns = range(1, cfg.max_turn + 1)
    dmg_sum, power_sum, lands_sum, landfall_sum, gy_lands_sum, distinct_sum = ([0] * (cfg.max_turn + 1) for _ in range(6))
    token_sum: dict[str, list[int]] = {}
    swings: list[int] = []
    routes = {"combat": 0, "combo": 0, "none": 0}
    for i in range(iterations):
        rec = play_game(deck, lines, cfg, random.Random(seed + i), tipping_target)
        for k in CLOCKS:
            firsts[k].append(rec.clocks[k])
        for t in range(1, cfg.max_turn + 1):
            mana_sum[t] += rec.mana_by_turn[t]
            idle_sum[t] += rec.idle_by_turn[t]
            dmg_sum[t] += rec.damage_by_turn[t]
            power_sum[t] += rec.board_power_by_turn[t]
            lands_sum[t] += rec.lands_by_turn[t]
            landfall_sum[t] += rec.landfall_by_turn[t]
            gy_lands_sum[t] += rec.graveyard_lands_by_turn[t]
            distinct_sum[t] += rec.distinct_lands_by_turn[t]
        for type_, per_turn in rec.tokens_by_turn.items():
            acc = token_sum.setdefault(type_, [0] * (cfg.max_turn + 1))
            for t in turns:
                acc[t] += per_turn[t]
        swings.append(rec.max_swing)
        lt, lc = rec.clocks["lethal_table"], rec.clocks["lethal_combo"]
        if rec.clocks["win"] is None:
            routes["none"] += 1
        elif lt is not None and (lc is None or lt <= lc):
            routes["combat"] += 1
        else:
            routes["combo"] += 1

    combos_ok = facts.combos is not None
    labels = clock_labels(cfg, tipping_target)
    clocks = {
        k: _clock(k, labels[k], firsts[k], cfg.max_turn, status="ok" if (combos_ok or k not in ("combo", "lethal_combo")) else "unevaluated")
        for k in labels if k in CLOCKS
    }
    n = max(iterations, 1)
    notes = [
        f"on the play, {iterations} games, seed {seed}; one London mulligan when the opener holds fewer than "
        f"{cfg.mulligan_min_lands} or more than {cfg.mulligan_max_lands} lands; no opponent, no interaction; "
        "combat counts printed power, counters, anthems and pumps cast for lethal; tokens attack from the turn after they enter; no haste, no blockers; colours are enforced",
        "tokens entering do not fire token-making creature-enters effects, and token-created triggers do not make more tokens",
        "lands fetched by ramp spells enter tapped",
        "attackers are assigned greedily to the opponent with the most life, not optimally",
        "at most one pump spell is cast per turn, and only when it kills an opponent",
        "a pump spell cast for another role (a threat, a draw tag) does not apply its pump",
        "lands returned from the graveyard enter tapped, one at a time",
        "fetch lands find a 1-mana land, tapped; free fetches are cracked the turn they enter",
        "dredge replaces the draw only when the hand lacks a land for this turn's drops, never the opening hand",
        f"mass land return is cast with {cfg.mass_return_min_lands}+ lands in the graveyard and a landfall source out, or on the last two turns",
        "activated abilities are paid from mana left after the main phase",
        "an activated ability on a mana source is used only with mana left after the main phase, so lands and rocks that tap for mana rarely activate",
        "a draw granted by a trigger is a plain draw, never a dredge",
        f"reanimation targets the highest-MV eligible card; a reanimation spell is cast only for a creature with MV "
        f"{cfg.threat_mv}+ or power {cfg.reanimate_min_power}+",
        "a sacrifice cost takes a creature whose death returns lands, else a token, else the smallest creature",
        "no maximum hand size",
    ]
    notes.extend(deck.notes)
    notes.extend(payoffs.notes)
    if not combos_ok:
        notes.append(f"Spellbook unavailable ({facts.combos_unavailable_reason}): combo clocks unevaluated; win is lethal_table alone")
    elif skipped:
        notes.append(f"{len(lines)} of {len(lines) + len(skipped)} Spellbook line(s) simulated; the rest are listed as not simulated, not assumed free")
    return SimResult(
        status="ok",
        sim_version=cfg.version,
        seed=seed,
        iterations=iterations,
        max_turn=cfg.max_turn,
        clocks=clocks,
        mana_by_turn={t: round(mana_sum[t] / n, 3) for t in range(1, cfg.max_turn + 1)},
        idle_by_turn={t: round(idle_sum[t] / n, 6) for t in range(1, cfg.max_turn + 1)},
        lines_simulated=[l.label for l in lines],
        lines_skipped=skipped,
        line_status=[{
            "label": l.label,
            "status": l.status,
            "resources": list(l.resources),
            "categories": list(dict.fromkeys(c for r in l.resources for c in cfg.payoff_converts.get(r, ()))),
            "candidates": sorted(l.payoff.candidates) if l.payoff else [],
            "hand_ok": bool(l.payoff.hand_ok) if l.payoff else False,
            "fuel_only": _fuel_only(l.resources, cfg, payoffs) if l.status == "no_payoff" else [],
        } for l in lines],
        payoffs={k: list(v) for k, v in payoffs.by_category.items()},
        combos_status="ok" if combos_ok else "unavailable",
        coverage=dict(deck.coverage),
        notes=notes,
        damage_by_turn={t: round(dmg_sum[t] / n, 3) for t in turns},
        board_power_by_turn={t: round(power_sum[t] / n, 3) for t in turns},
        lands_by_turn={t: round(lands_sum[t] / n, 3) for t in turns},
        landfall_by_turn={t: round(landfall_sum[t] / n, 3) for t in turns},
        graveyard_lands_by_turn={t: round(gy_lands_sum[t] / n, 3) for t in turns},
        distinct_lands_by_turn={t: round(distinct_sum[t] / n, 3) for t in turns},
        tokens_by_turn={k: {t: round(v[t] / n, 3) for t in turns} for k, v in sorted(token_sum.items())},
        max_swing_median=int(statistics.median_low(swings)) if swings else 0,
        win_route={k: round(v / n, 6) for k, v in routes.items()},
        effects_sources={k: list(v) for k, v in deck.effects_sources.items()},
        unmodelled=list(deck.unmodelled),
        partial=list(deck.partial),
        nonland_count=sum(deck.coverage.values()) - deck.coverage["land"],
    )
