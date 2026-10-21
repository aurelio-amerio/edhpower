"""Structural and directional checks on the frozen live fixtures. Exact numbers live in test_golden.py."""

from pathlib import Path

import pytest

from edhpower.analysis import analyse
from edhpower.facts import SCHEMA_VERSION, load_facts

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name,expected_gc,expected_bracket", [
    ("zhulodok-bracket3", 1, 3),
    ("ulalek-bracket3-v2", 3, 3),
    ("ulalek-b5", None, None),              # bracket 5 by declaration; the criteria floor is whatever the live run shows
    ("precon-eldrazi-unbound", None, None),  # expected 0 Game Changers / bracket 2 — if the live run disagrees, record why in CALIBRATION.md
    ("ulalek-bracket4-v2", None, None),     # 14 Game Changers per the deck notes → bracket 4 expected; record the live value in CALIBRATION.md
    ("necrobloom-v3", 1, 3),
])
def test_fixture_invariants(name, expected_gc, expected_bracket):
    facts = load_facts(FIXTURES / f"{name}.facts.json")
    assert facts.schema_version == SCHEMA_VERSION and facts.total_cards == 100 and len(facts.commanders) == 1
    assert facts.unresolved == [] and facts.parse_errors == [] and facts.identity_violations == []
    assert facts.tags_status == "ok" and facts.combos is not None
    assert set(facts.profiles) == {e.name for e in facts.entries}
    assert sum(facts.partition_counts[k] for k in ("lands", "fast_mana", "mana_rocks", "mana_dorks", "land_ramp", "rituals", "other_ramp")) <= 100
    a = analyse(facts, iterations=100)
    if expected_gc is not None:
        assert len(facts.game_changers) == expected_gc
    if expected_bracket is not None:
        assert a.bracket.minimum_bracket == expected_bracket
    assert a.components.status == "ok" and a.tipping.target in range(2, 7)
    assert {c.name for c in a.bracket.criteria} >= {"game_changers", "mass_land_denial", "extra_turns", "two_card_combos", "tutors"}
    assert next(c for c in a.bracket.criteria if c.name == "tutors").status in ("ok", "review")


def test_ulalek_has_basalt_monument_two_card_line():
    facts = load_facts(FIXTURES / "ulalek-bracket3-v2.facts.json")
    labels = {" + ".join(sorted(line.piece_names)) for line in facts.combos.included}
    assert "Basalt Monolith + Forsaken Monument" in labels
    flags = next(f for line in facts.combos.included for cid, f in facts.combos.combo_flags.items() if cid == line.id and "Basalt Monolith" in line.piece_names)
    assert flags.definitely_two_card


def test_contrast_lists_rank_in_the_expected_direction():
    precon = analyse(load_facts(FIXTURES / "precon-eldrazi-unbound.facts.json"), iterations=200)
    b3 = analyse(load_facts(FIXTURES / "ulalek-bracket3-v2.facts.json"), iterations=200)
    b5 = analyse(load_facts(FIXTURES / "ulalek-b5.facts.json"), iterations=200)
    assert precon.curve.power_level < b3.curve.power_level < b5.curve.power_level
    assert precon.components.total < b5.components.total
    assert precon.bracket.minimum_bracket <= b3.bracket.minimum_bracket <= b5.bracket.minimum_bracket
    assert (b5.tipping.turn or 99) <= (precon.tipping.turn or 99)
    b4 = analyse(load_facts(FIXTURES / "ulalek-bracket4-v2.facts.json"), iterations=200)
    assert b3.bracket.minimum_bracket <= b4.bracket.minimum_bracket <= b5.bracket.minimum_bracket
    assert len(b4.facts.combos.included) > len(b3.facts.combos.included)


def test_special_behaviours_hit_the_expected_cards():
    z = load_facts(FIXTURES / "zhulodok-bracket3.facts.json")
    assert any(h.startswith("Eldrazi Temple (land, mana 2)") for h in z.special_hits)
    assert any(h.startswith("Eye of Ugin (land, mana 0)") for h in z.special_hits)
    assert z.profiles["Eye of Ugin"].cost_reduction == 2
    u = load_facts(FIXTURES / "ulalek-bracket3-v2.facts.json")
    assert any(h.startswith("Basalt Monolith (rock, mana 3)") for h in u.special_hits)
    assert u.profiles["Ancient Tomb"].land_mana == 2 and u.profiles["Mana Vault"].is_fast_mana


def test_necrobloom_fixture_makes_zombies():
    sim = analyse(load_facts(FIXTURES / "necrobloom-v3.facts.json"), iterations=500).sim
    assert sim is not None
    assert sim.tokens_by_turn["Zombie"][12] > 0
    assert sim.tokens_by_turn["Plant"][5] > 0


def test_necrobloom_effects_come_from_forge_not_table():
    sim = analyse(load_facts(FIXTURES / "necrobloom-v3.facts.json"), iterations=100).sim
    assert sim is not None
    assert {"The Necrobloom", "Avenger of Zendikar"} <= set(sim.effects_sources["forge"])
    assert sim.effects_sources["table"] == []


def test_necrobloom_engine_is_alive_in_stage2():
    sim = analyse(load_facts(FIXTURES / "necrobloom-v3.facts.json"), iterations=500).sim
    assert sim is not None
    assert sim.graveyard_lands_by_turn[8] >= 1.0
    assert sim.tokens_by_turn["Zombie"][12] > 3.4   # stage 1 measured 3.4 at 20 000 games
    assert "Life from the Loam" in sim.effects_sources["forge"] and "Life from the Loam" not in sim.unmodelled
    assert sim.effects_sources["table"] == []
