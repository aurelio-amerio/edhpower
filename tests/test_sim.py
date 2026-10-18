import dataclasses
import json

from edhpower.config import load_config
from edhpower.sim import Clock, SimResult, clock_labels, deck_seed, simulate
from edhpower.sim.engine import CLOCKS

from .conftest import fixture_facts

CFG = load_config().sim
N = 300


def _reversed(facts):
    return dataclasses.replace(facts, entries=list(reversed(facts.entries)))


def test_seed_and_results_are_independent_of_decklist_order():
    facts = fixture_facts("ulalek-bracket3-v2")
    a = simulate(facts, CFG, N, tipping_target=4)
    b = simulate(_reversed(facts), CFG, N, tipping_target=4)
    assert deck_seed(facts) == deck_seed(_reversed(facts)) == a.seed
    assert a.to_dict() == b.to_dict()
    assert simulate(facts, CFG, N, tipping_target=4).to_dict() == a.to_dict()


def test_iteration_prefix_property():
    facts = fixture_facts("zhulodok-bracket3")
    short, long = simulate(facts, CFG, 50, 6), simulate(facts, CFG, 100, 6)
    # the first 50 games of the 100-game run are the 50-game run: cumulative shares can only be
    # re-weighted, so a clock reached in 0 of 50 games is reached in at most 50 of 100
    for k in CLOCKS:
        assert long.clocks[k].reached * 100 >= short.clocks[k].reached * 50 - 1e-6


def test_result_shape_and_labels():
    r = simulate(fixture_facts("precon-eldrazi-unbound"), CFG, 40, tipping_target=5)
    assert isinstance(r, SimResult) and r.status == "ok" and r.sim_version == CFG.version and r.iterations == 40 and r.max_turn == CFG.max_turn
    assert set(r.clocks) == set(CLOCKS) and all(isinstance(c, Clock) for c in r.clocks.values())
    for c in r.clocks.values():
        turns = list(c.by_turn)
        assert turns == list(range(1, CFG.max_turn + 1))
        assert all(c.by_turn[t] <= c.by_turn[t + 1] for t in turns[:-1]) and c.by_turn[CFG.max_turn] == c.reached
        assert c.median is None or 1 <= c.median <= CFG.max_turn
    assert r.clocks["tipping_target"].label == "5 mana available (closed-form tipping target)"
    assert r.clocks["mana_threshold"].label == f"{CFG.mana_threshold} mana available"
    assert clock_labels(CFG, 5)["combat"] == f"{CFG.lethal_damage} combat damage (no blockers)"
    assert set(r.mana_by_turn) == set(range(1, CFG.max_turn + 1)) and set(r.idle_by_turn) == set(range(1, CFG.max_turn + 1))
    assert r.combos_status == "ok" and r.lines_simulated == [] and r.clocks["combo"].reached == 0.0
    assert sum(r.coverage.values()) == 99 and r.coverage["land"] == 38
    json.dumps(r.to_dict())


def test_contrast_decks_goldfish_in_the_expected_direction():
    b5 = simulate(fixture_facts("ulalek-b5"), CFG, N, tipping_target=2)
    precon = simulate(fixture_facts("precon-eldrazi-unbound"), CFG, N, tipping_target=5)
    assert b5.clocks["commander"].median <= precon.clocks["commander"].median
    # The precon runs 38 lands to b5's 27, and a goldfish with no opponents rewards
    # land count for a raw "7 mana by turn 5" question: b5 trades lands for cheap
    # interaction and combo pieces this clock cannot see. Measured ~0.26 vs ~0.35.
    assert precon.clocks["mana_threshold"].by_turn[5] > b5.clocks["mana_threshold"].by_turn[5]
    assert b5.clocks["combo"].reached > 0.0 and b5.lines_simulated and precon.clocks["combo"].reached == 0.0
    assert b5.clocks["lethal_combo"].reached <= b5.clocks["combo"].reached


def test_spellbook_unavailable_leaves_combo_clocks_unevaluated():
    facts = dataclasses.replace(fixture_facts("ulalek-bracket3-v2"), combos=None, combos_unavailable_reason="Spellbook unreachable")
    r = simulate(facts, CFG, 20, 4)
    assert r.combos_status == "unavailable"
    assert r.clocks["combo"].status == "unevaluated" and r.clocks["combo"].median is None and r.clocks["combo"].reached == 0.0
    assert r.clocks["commander"].status == "ok"
    assert any("Spellbook unavailable" in n for n in r.notes)


def test_tags_down_is_declared_a_floor():
    facts = dataclasses.replace(fixture_facts("ulalek-bracket3-v2"), tags_status="skipped (--no-tags)")
    r = simulate(facts, CFG, 20, 4)
    assert any("floor" in n for n in r.notes) and r.coverage["tutor"] == 0


def test_templated_lines_are_reported_not_simulated():
    r = simulate(fixture_facts("ulalek-bracket3-v2"), CFG, 20, 4)
    assert r.lines_simulated == ["Basalt Monolith + Forsaken Monument"]
    assert [s.reason.startswith("templated") for s in r.lines_skipped] == [True]


def test_b4_combo_clock_beats_b3():
    b3 = simulate(fixture_facts("ulalek-bracket3-v2"), CFG, N, tipping_target=4)
    b4 = simulate(fixture_facts("ulalek-bracket4-v2"), CFG, N, tipping_target=4)
    assert len(b4.lines_simulated) > len(b3.lines_simulated)
    assert b4.clocks["combo"].reached > b3.clocks["combo"].reached
    assert b4.clocks["combo"].by_turn[6] > 0.0


def test_result_carries_line_statuses_and_payoffs():
    from edhpower.payoffs import detect
    facts = fixture_facts("ulalek-bracket4-v2")
    r = simulate(facts, CFG, 20, tipping_target=3)
    assert r.payoffs == detect(facts).by_category
    assert len(r.line_status) == len(r.lines_simulated)
    for row, label in zip(r.line_status, r.lines_simulated):
        assert row["label"] == label and row["status"] in ("direct", "payoff", "no_payoff", "unmapped")
        assert set(row) == {"label", "status", "resources", "categories", "candidates", "hand_ok", "fuel_only"}
        assert all(c in r.payoffs for c in row["categories"])
        assert (row["status"] == "payoff") == bool(row["candidates"])
    d = r.to_dict()
    assert d["line_status"] == r.line_status and d["payoffs"] == r.payoffs


def test_payoff_notes_reach_the_result():
    import dataclasses
    facts = dataclasses.replace(fixture_facts("precon-eldrazi-unbound"), tags_status="skipped (--no-tags)")
    r = simulate(facts, CFG, 10, tipping_target=5)
    assert any("payoff tag check skipped" in n for n in r.notes)


def test_precomputed_payoffs_give_identical_results():
    from edhpower.payoffs import detect
    facts = fixture_facts("ulalek-bracket3-v2")
    assert simulate(facts, CFG, 30, 4, payoffs=detect(facts)).to_dict() == simulate(facts, CFG, 30, 4).to_dict()
