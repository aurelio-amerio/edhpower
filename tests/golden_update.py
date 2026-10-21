"""Regenerate fixtures/golden.json from the frozen DeckFacts fixtures. Run after a deliberate re-baseline:
    uv run --directory edhpower python tests/golden_update.py
"""

from __future__ import annotations

import json
from pathlib import Path

from edhpower.analysis import analyse
from edhpower.config import load_config
from edhpower.facts import load_facts

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN_ITERATIONS = 500  # deterministic given the deck seed; small enough for the suite, large enough to pin medians


def golden_for(name: str) -> dict:
    a = analyse(load_facts(FIXTURES / f"{name}.facts.json"), iterations=GOLDEN_ITERATIONS)
    sim = a.sim
    assert sim is not None
    return {
        "bracket": a.bracket.minimum_bracket,
        "curve_power_level": a.curve.power_level,
        "curve_total_impact": a.curve.total_impact,
        "curve_efficiency": a.curve.efficiency,
        "curve_bracket_estimate": a.curve.bracket_estimate,
        "components_total": a.components.total,
        "components": {c.name: c.score for c in a.components.components},
        "archetype": a.components.archetype,
        "tipping_target": a.tipping.target,
        "tipping_turn": a.tipping.turn,
        "tipping_probability": a.tipping.probability,
        "partition_counts": a.facts.partition_counts,
        "sim_seed": sim.seed,
        "sim_commander_median": sim.clocks["commander"].median,
        "sim_mana_threshold_median": sim.clocks["mana_threshold"].median,
        "sim_tipping_target_median": sim.clocks["tipping_target"].median,
        "sim_threat_median": sim.clocks["threat"].median,
        "sim_combat_median": sim.clocks["combat"].median,
        "sim_combo_reached": sim.clocks["combo"].reached,
        "sim_lethal_combo_reached": sim.clocks["lethal_combo"].reached,
        "sim_win_median": sim.clocks["win"].median,
        "sim_win_fast": sim.clocks["win"].fast,
        "sim_lethal_table_median": sim.clocks["lethal_table"].median,
        "sim_max_swing_median": sim.max_swing_median,
        "sim_unmodelled_count": len(sim.unmodelled),
        "sim_idle_window": list(a.narrative.idle_window) if a.narrative.idle_window else None,
    }


if __name__ == "__main__":
    names = sorted(p.name.removesuffix(".facts.json") for p in FIXTURES.glob("*.facts.json"))
    payload = {"config": {**load_config().stamp(), "sim_iterations": GOLDEN_ITERATIONS}, "decks": {n: golden_for(n) for n in names}}
    (FIXTURES / "golden.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
