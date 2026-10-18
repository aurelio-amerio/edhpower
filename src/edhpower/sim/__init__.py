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
from edhpower.sim.combos import SkippedLine, select_lines
from edhpower.sim.engine import CLOCKS, play_game
from edhpower.sim.model import build_sim_deck


@dataclass
class Clock:
    name: str
    label: str
    status: str
    median: int | None
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
    combos_status: str
    coverage: dict[str, int]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def deck_seed(facts: DeckFacts) -> int:
    key = json.dumps(sorted((e.name, e.count) for e in facts.entries), ensure_ascii=False)
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


def clock_labels(cfg: SimConfig, tipping_target: int) -> dict[str, str]:
    return {
        "commander": "commander castable",
        "mana_threshold": f"{cfg.mana_threshold} mana available",
        "tipping_target": f"{tipping_target} mana available (closed-form tipping target)",
        "threat": f"MV {cfg.threat_mv}+ spell cast from hand",
        "combat": f"{cfg.lethal_damage} combat damage (no blockers)",
        "combo": "combo line assembled",
        "lethal_combo": "lethal combo line assembled",
    }


def _clock(name: str, label: str, turns: list[int | None], max_turn: int, status: str = "ok") -> Clock:
    n = len(turns)
    if status != "ok" or n == 0:
        return Clock(name, label, status, None, 0.0, {t: 0.0 for t in range(1, max_turn + 1)})
    padded = [t if t is not None else max_turn + 1 for t in turns]
    med = statistics.median_low(padded)
    by_turn = {t: round(sum(1 for x in padded if x <= t) / n, 6) for t in range(1, max_turn + 1)}
    return Clock(name, label, status, med if med <= max_turn else None, by_turn[max_turn], by_turn)


def simulate(facts: DeckFacts, cfg: SimConfig, iterations: int, tipping_target: int) -> SimResult:
    deck = build_sim_deck(facts, cfg)
    lines, skipped = select_lines(facts, cfg)
    seed = deck_seed(facts)
    firsts: dict[str, list[int | None]] = {k: [] for k in CLOCKS}
    mana_sum = [0.0] * (cfg.max_turn + 1)
    idle_sum = [0] * (cfg.max_turn + 1)
    for i in range(iterations):
        rec = play_game(deck, lines, cfg, random.Random(seed + i), tipping_target)
        for k in CLOCKS:
            firsts[k].append(rec.clocks[k])
        for t in range(1, cfg.max_turn + 1):
            mana_sum[t] += rec.mana_by_turn[t]
            idle_sum[t] += rec.idle_by_turn[t]

    combos_ok = facts.combos is not None
    labels = clock_labels(cfg, tipping_target)
    clocks = {
        k: _clock(k, labels[k], firsts[k], cfg.max_turn, status="ok" if (combos_ok or k not in ("combo", "lethal_combo")) else "unevaluated")
        for k in CLOCKS
    }
    n = max(iterations, 1)
    notes = [
        f"on the play, {iterations} games, seed {seed}; one London mulligan when the opener holds fewer than "
        f"{cfg.mulligan_min_lands} or more than {cfg.mulligan_max_lands} lands; no opponent, no interaction; "
        "combat counts printed power only (tokens, anthems and pump excluded); colours are enforced"
    ]
    notes.extend(deck.notes)
    if not combos_ok:
        notes.append(f"Spellbook unavailable ({facts.combos_unavailable_reason}): combo clocks unevaluated")
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
        combos_status="ok" if combos_ok else "unavailable",
        coverage=dict(deck.coverage),
        notes=notes,
    )
