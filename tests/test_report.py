from edhpower.analysis import analyse
from edhpower.decklist import parse_decklist
from edhpower.facts import build_facts
from edhpower.report import render_text
from edhpower.scryfall import CardData, Resolution
from edhpower.spellbook import ComboData, ComboFlags, ComboLine, ComboPiece, ComboTemplate

from .conftest import make_card


def _facts():
    parsed = parse_decklist("1 Zhulodok, Void Gorger\n\n2 Wastes\n1 Ancient Tomb\n1 Basalt Monolith\n1 Forsaken Monument\n")
    objs = [make_card("Zhulodok, Void Gorger", cmc=7.0, type_line="Legendary Creature — Eldrazi"),
            make_card("Wastes", type_line="Basic Land", cmc=0.0), make_card("Ancient Tomb", type_line="Land", cmc=0.0, game_changer=True),
            make_card("Basalt Monolith", cmc=3.0), make_card("Forsaken Monument", cmc=5.0)]
    res = Resolution({o["name"]: CardData.from_scryfall(o) for o in objs}, ["Ghost Card"], 0, "2026-09-10T00:00:00Z")
    line = ComboLine("c1", (ComboPiece("Basalt Monolith", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)),
                     (ComboTemplate("Eldrazi Creature Card with MV=4, 5 or 6", ("H",)),), ("Infinite colorless mana",), "", 0, "R", 5, "", "")
    combos = ComboData("C", [line], 3, {}, {"c1": ComboFlags("c1", True, False, 5, False, False, False, False, True)}, "R", "2026-09-10T01:00:00Z")
    return build_facts(parsed, res, combos, None, "deck/x.txt")


def test_report_contains_every_section():
    facts = _facts()
    text = render_text(analyse(facts, iterations=30))
    for needle in ["deck/x.txt", "Zhulodok, Void Gorger", "Unresolved: Ghost Card", "Mana curve", "7+", "Pips",
                   "Prices", "Game Changers", "Ancient Tomb", "Combos", "Basalt Monolith + Forsaken Monument",
                   "template: Eldrazi Creature Card", "Infinite colorless mana", "speed 5", "Bracket", "minimum bracket: 3",
                   "game_changers", "tutors", "unevaluated", "Functional profile", "tags not requested",
                   "special behaviours: Ancient Tomb (land, mana 2)", "Scores", "Curve model (edhpowerlevel-2026-08)",
                   "power", "bracket estimate", "Component model (v1)", "Tipping point", "target", "Data freshness", "2026-09-10T01:00:00Z",
                   "Goldfish simulation", "commander castable", "7 mana available", "combat damage", "combo line assembled",
                   "lines simulated: none", "not simulated: Basalt Monolith + Forsaken Monument (templated", "model coverage", "Findings", "Bracket 3 is forced by game_changers",
                   ]:
        assert needle in text, needle


def test_report_without_combos_says_so():
    facts = _facts()
    facts.combos = None
    facts.combos_unavailable_reason = "Spellbook unreachable"
    text = render_text(analyse(facts, iterations=30))
    assert "Combos: unavailable (Spellbook unreachable)" in text
    assert text.count("unevaluated") >= 4   # three Spellbook-dependent criteria, the tutors criterion, the component model


def test_report_says_not_reached_when_turn_is_none():
    # _facts() has only 3 lands against a commander cmc 7 + spells up to cmc 5: the tipping
    # threshold is never reached by max_turn, so tp.turn is None and the report must read
    # TippingPoint.max_turn directly rather than deriving it from the curve.
    a = analyse(_facts(), iterations=30)
    assert a.tipping.turn is None
    text = render_text(a)
    assert f"not reached by turn {a.tipping.max_turn} (p=" in text


def test_report_prints_unevaluated_combo_clocks_and_no_sim():
    facts = _facts()
    facts.combos = None
    facts.combos_unavailable_reason = "Spellbook unreachable"
    text = render_text(analyse(facts, iterations=20))
    assert "combo line assembled" in text and "unevaluated" in text.split("Goldfish simulation")[1].split("Findings")[0]
    text = render_text(analyse(facts, run_sim=False))
    assert "Goldfish simulation: skipped (--no-sim)" in text and "Simulation skipped (--no-sim)" in text
