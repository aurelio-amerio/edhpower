from math import comb

import pytest

from edhpower.config import load_config
from edhpower.decklist import parse_decklist
from edhpower.facts import build_facts
from edhpower.scryfall import CardData, Resolution
from edhpower.tipping import TippingPoint, hypergeom_at_least, hypergeom_pmf, land_mana_probability, tipping_point

from .conftest import full_tag_cache, make_card

CFG = load_config().tipping


def test_hypergeometric_against_known_values():
    # 99-card library, 37 lands, 7-card hand: P(exactly 3 lands)
    assert hypergeom_pmf(99, 37, 7, 3) == pytest.approx(comb(37, 3) * comb(62, 4) / comb(99, 7))
    assert hypergeom_at_least(99, 37, 7, 0) == pytest.approx(1.0)
    assert hypergeom_at_least(99, 37, 7, 8) == 0.0
    assert hypergeom_at_least(99, 37, 7, 2) == pytest.approx(1 - hypergeom_pmf(99, 37, 7, 0) - hypergeom_pmf(99, 37, 7, 1))
    assert hypergeom_pmf(10, 3, 4, 5) == 0.0


def test_land_mana_probability_reduces_to_hypergeometric_with_one_class():
    # only 1-mana lands, need 3 mana by turn 3 (9 cards seen): P(≥3 lands among 9)
    assert land_mana_probability(99, 37, 0, 9, 3, 3.0) == pytest.approx(hypergeom_at_least(99, 37, 9, 3))
    # two-mana lands count double but only T lands can be played
    assert land_mana_probability(99, 0, 37, 9, 1, 2.0) == pytest.approx(hypergeom_at_least(99, 37, 9, 1))
    assert land_mana_probability(99, 0, 37, 9, 1, 3.0) == 0.0
    # at least one land is always required
    assert land_mana_probability(99, 37, 0, 9, 3, 0.0) == pytest.approx(hypergeom_at_least(99, 37, 9, 1))


def _facts(land_one=36, land_two=0, fast=0, rocks=0, spells_mv=(3.0,), heavy=0, cheat=0):
    lines = ["1 Commander", ""]
    cards = {"Commander": make_card("Commander", cmc=4.0, type_line="Legendary Creature")}
    members: dict[str, list[str]] = {"mana-rock": [], "ramp": [], "cheat-into-play": []}
    if land_one:
        lines.append(f"{land_one} Forest")
        cards["Forest"] = make_card("Forest", cmc=0.0, type_line="Basic Land — Forest", oracle_text="({T}: Add {G}.)")
    if land_two:
        lines.append(f"{land_two} Ancient Tomb")
        cards["Ancient Tomb"] = make_card("Ancient Tomb", cmc=0.0, type_line="Land", oracle_text="{T}: Add {C}{C}.")
    for i in range(fast):
        n = f"Fast {i}"
        lines.append(f"1 {n}")
        cards[n] = make_card(n, cmc=1.0, oracle_text="{T}: Add {C}{C}.")
        members["mana-rock"].append(n); members["ramp"].append(n)
    for i in range(rocks):
        n = f"Rock {i}"
        lines.append(f"1 {n}")
        cards[n] = make_card(n, cmc=2.0, oracle_text="{T}: Add {C}.")
        members["mana-rock"].append(n); members["ramp"].append(n)
    for i, mv in enumerate(spells_mv):
        n = f"Spell {i}"
        lines.append(f"1 {n}")
        cards[n] = make_card(n, cmc=mv, type_line="Sorcery")
    for i in range(heavy):
        n = f"Heavy {i}"
        lines.append(f"1 {n}")
        cards[n] = make_card(n, cmc=8.0, type_line="Creature — Eldrazi")
    for i in range(cheat):
        n = f"Cheat {i}"
        lines.append(f"1 {n}")
        cards[n] = make_card(n, cmc=3.0, type_line="Enchantment")
        members["cheat-into-play"].append(n)
    parsed = parse_decklist("\n".join(lines) + "\n")
    res = Resolution({k: CardData.from_scryfall(v) for k, v in cards.items()}, [], 0, None)
    return build_facts(parsed, res, None, None, "t.txt", tag_cache=full_tag_cache(**members))


def test_tipping_point_reports_target_curve_and_turn():
    tp = tipping_point(_facts(land_one=36, spells_mv=(3.0, 3.0, 3.0)), CFG)
    assert isinstance(tp, TippingPoint) and tp.target == 3 and tp.functional_avg_mv == pytest.approx(3.0)
    assert tp.land_classes == {"one": 36, "two": 0, "utility": 0} and tp.fast_mana == 0 and tp.ramp == 0
    assert list(tp.curve) == list(range(1, CFG.max_turn + 1))
    assert tp.curve[3] == pytest.approx(land_mana_probability(39, 36, 0, 9, 3, 3.0))
    assert tp.turn == min(t for t, p in tp.curve.items() if p >= CFG.threshold)
    assert tp.probability == pytest.approx(tp.curve[tp.turn])


def test_fast_mana_and_two_mana_lands_move_the_tipping_point_earlier():
    slow = tipping_point(_facts(land_one=36, spells_mv=(4.0,) * 3), CFG)
    fast = tipping_point(_facts(land_one=36, fast=3, rocks=4, spells_mv=(9.0, 10.0, 10.0)), CFG)   # (3×1 + 4×2 + 29)/10 = 4.0 → same target
    tombs = tipping_point(_facts(land_one=30, land_two=6, spells_mv=(4.0,) * 3), CFG)
    assert slow.target == fast.target == tombs.target == 4
    assert fast.boosts["fast_mana"] == pytest.approx(min(3 * CFG.fast_mana_boost, CFG.fast_mana_boost_max))
    assert fast.boosts["ramp"] == pytest.approx(min(4 * CFG.ramp_boost, CFG.ramp_boost_max))
    assert (fast.turn or 99) <= (slow.turn or 99) and (tombs.turn or 99) <= (slow.turn or 99)
    assert all(fast.curve[t] >= slow.curve[t] for t in slow.curve)


def test_functional_average_excludes_heavy_creatures_with_cheat_package():
    plain = tipping_point(_facts(land_one=36, spells_mv=(2.0,) * 4, heavy=3), CFG)
    cheaty = tipping_point(_facts(land_one=36, spells_mv=(2.0,) * 4, heavy=3, cheat=2), CFG)
    assert plain.functional_avg_mv > cheaty.functional_avg_mv and cheaty.functional_avg_mv == pytest.approx((2.0 * 4 + 3.0 * 2) / 6)
    assert any("heavy creature" in n for n in cheaty.notes)


def test_target_is_clamped_and_never_reached_is_none():
    huge = tipping_point(_facts(land_one=10, spells_mv=(9.0,) * 15), CFG)   # 10 lands in 25 cards: 6 lands by turn 7 is < 80 %
    assert huge.target == CFG.target_max and huge.turn is None and huge.probability == pytest.approx(huge.curve[CFG.max_turn])
    tiny = tipping_point(_facts(land_one=36, spells_mv=(1.0,) * 5), CFG)
    assert tiny.target == CFG.target_min
    d = huge.to_dict()
    assert d["turn"] is None and isinstance(d["curve"], dict)


def test_probability_is_monotonically_nondecreasing_in_turn():
    tp = tipping_point(_facts(land_one=36, land_two=0, spells_mv=(4.0,) * 4), CFG)
    turns = sorted(tp.curve)
    probs = [tp.curve[t] for t in turns]
    assert all(b >= a - 1e-6 for a, b in zip(probs, probs[1:]))


def test_max_turn_is_populated_from_config_and_carried_in_to_dict():
    tp = tipping_point(_facts(land_one=36, spells_mv=(3.0, 3.0, 3.0)), CFG)
    assert tp.max_turn == CFG.max_turn
    assert tp.to_dict()["max_turn"] == CFG.max_turn


def test_ramp_boost_from_turn_is_populated_from_config():
    tp = tipping_point(_facts(land_one=36, spells_mv=(3.0, 3.0, 3.0)), CFG)
    assert tp.ramp_boost_from_turn == CFG.ramp_boost_from_turn
    assert tp.to_dict()["ramp_boost_from_turn"] == CFG.ramp_boost_from_turn


def _facts_no_tags(land_one=36, spells_mv=(3.0,)):
    """Same shape as _facts() but with no tag_cache, so tags_status != 'ok' (ramp/cheat counts are 0)."""
    lines = ["1 Commander", "", f"{land_one} Forest"]
    cards = {
        "Commander": make_card("Commander", cmc=4.0, type_line="Legendary Creature"),
        "Forest": make_card("Forest", cmc=0.0, type_line="Basic Land — Forest", oracle_text="({T}: Add {G}.)"),
    }
    for i, mv in enumerate(spells_mv):
        n = f"Spell {i}"
        lines.append(f"1 {n}")
        cards[n] = make_card(n, cmc=mv, type_line="Sorcery")
    parsed = parse_decklist("\n".join(lines) + "\n")
    res = Resolution({k: CardData.from_scryfall(v) for k, v in cards.items()}, [], 0, None)
    return build_facts(parsed, res, None, None, "t.txt")  # no tag_cache -> tags_status != "ok"


def test_tags_unavailable_note_is_present_only_when_tags_are_unavailable():
    ok = tipping_point(_facts(land_one=36, spells_mv=(3.0, 3.0, 3.0)), CFG)
    assert ok.to_dict()  # sanity: full round trip still works
    assert not any("tags unavailable" in n for n in ok.notes)

    degraded_facts = _facts_no_tags(spells_mv=(3.0, 3.0, 3.0))
    assert degraded_facts.tags_status != "ok"
    degraded = tipping_point(degraded_facts, CFG)
    assert any("tags unavailable" in n and "floor" in n for n in degraded.notes)
