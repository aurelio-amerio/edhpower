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
                   "lines simulated: none", "not simulated: Basalt Monolith + Forsaken Monument (templated", "payoffs:", "model coverage", "Findings", "Bracket 3 is forced by game_changers",
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


def _payoff_facts(extra_objs=(), extra_lines=()):
    parsed = parse_decklist("1 Zhulodok, Void Gorger\n\n6 Wastes\n1 Basalt Monolith\n1 Forsaken Monument\n1 Glacial Chasm\n1 Walking Ballista\n"
                            + "".join(f"1 {o['name']}\n" for o in extra_objs))
    objs = [make_card("Zhulodok, Void Gorger", cmc=7.0, type_line="Legendary Creature — Eldrazi"),
            make_card("Wastes", type_line="Basic Land", cmc=0.0, produced_mana=["C"]),
            make_card("Basalt Monolith", cmc=3.0), make_card("Forsaken Monument", cmc=5.0), make_card("Glacial Chasm", type_line="Land", cmc=0.0),
            make_card("Walking Ballista", cmc=0.0, mana_cost="{X}{X}", type_line="Artifact Creature — Construct", power="0", toughness="0",
                      oracle_text="This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nRemove a +1/+1 counter from this creature: It deals 1 damage to any target.")]
    objs = objs + list(extra_objs)
    res = Resolution({o["name"]: CardData.from_scryfall(o) for o in objs}, [], 0, "2026-09-10T00:00:00Z")
    mana = ComboLine("m", (ComboPiece("Basalt Monolith", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), ("Infinite colorless mana",), "", 0, "R", 5, "", "")
    lock = ComboLine("l", (ComboPiece("Glacial Chasm", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), ("Prevent all damage that would be dealt to you", "Lock"), "", 0, "S", 4, "", "")
    lines = [*extra_lines, mana, lock]
    flags = {ln.id: ComboFlags(ln.id, True, False, 5, False, False, False, False, True) for ln in lines}
    combos = ComboData("C", lines, 0, {}, flags, "R", "2026-09-10T01:00:00Z")
    from .conftest import full_tag_cache
    return build_facts(parsed, res, combos, None, "deck/p.txt", tag_cache=full_tag_cache(**{"mana-sink": ["Walking Ballista"]}))


def test_report_shows_line_status_and_payoffs():
    text = render_text(analyse(_payoff_facts(), iterations=20))
    assert "lines simulated: Basalt Monolith + Forsaken Monument [mana → Walking Ballista]" in text
    assert "not simulated: Glacial Chasm + Forsaken Monument (lock only)" in text
    assert "payoffs: mana sink: Walking Ballista" in text
    assert "1 lock line(s) excluded from the combo clock: Glacial Chasm + Forsaken Monument" in text


def test_report_names_engines_without_payoff():
    facts = _payoff_facts()
    facts.entries = [e for e in facts.entries if e.name != "Walking Ballista"]
    text = render_text(analyse(facts, iterations=20))
    assert "lines simulated: Basalt Monolith + Forsaken Monument [mana → no payoff in deck]" in text
    assert "payoffs: mana sink: none" in text
    assert "1 infinite engine(s) have no payoff in this deck: Basalt Monolith + Forsaken Monument" in text


def test_report_explains_landfall_fuel_without_a_finisher():
    field = make_card("Field of the Dead", type_line="Land", cmc=0.0, produced_mana=["C"],
                      oracle_text="This land enters tapped.\n{T}: Add {C}.\nWhenever this land or another land you control enters, if you control seven or more lands with different names, create a 2/2 black Zombie creature token.")
    land = ComboLine("lf", (ComboPiece("Basalt Monolith", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), ("Infinite landfall triggers",), "", 0, "R", 9, "", "")
    facts = _payoff_facts(extra_objs=[field], extra_lines=[land])
    text = render_text(analyse(facts, iterations=20))
    assert "Basalt Monolith + Forsaken Monument [landfall → Field of the Dead is fuel only: no go-wide finisher, token drain or ETB damage in deck]" in text
    assert "go-wide finisher: none" in text and "token drain: none" in text and "ETB damage: none" in text


def test_report_prints_fast_column_and_board_rows():
    from dataclasses import replace
    a = analyse(_facts(), iterations=20)
    sim = replace(a.sim, tokens_by_turn={"Zombie": {t: 1.0 for t in range(1, a.sim.max_turn + 1)}}, unmodelled=["Foo"],
                  partial=["Bar"], effects_sources={"table": ["Baz"], "forge": [], "none": []})
    text = render_text(replace(a, sim=sim))
    for needle in ["fast", "tokens: Zombie", "win route:", "unmodelled", "damage this turn", "board power", "lands on battlefield",
                   "biggest swing (median)", "effects: table 1 (Baz) · forge 0 · unmodelled: Foo · partial: Bar",
                   "lands entering this turn", "lands in graveyard", "distinct land names",
                   "  not modelled: fetch then dredge in one turn (Gitrog loop), Sylvan Library dredges, Field of the Dead counting lands "
                   "that enter with it, Saga chapters, attack triggers, life as a resource, Room cards, blockers/interaction"]:
        assert needle in text, needle


def test_report_coverage_line_has_spells():
    text = render_text(analyse(_facts(), iterations=20))
    line = next(l for l in text.splitlines() if "model coverage:" in l)
    assert " · spells " in line and line.index("spells") < line.index("held")


def test_report_clock_column_fits_the_longest_label():
    a = analyse(_facts(), iterations=20)
    lines = render_text(a).splitlines()
    header = next(l for l in lines if l.lstrip().startswith("clock ") and "median" in l)
    col = header.index("median")
    for c in a.sim.clocks.values():
        row = next(l for l in lines if l.startswith(f"  {c.label} "))
        assert row[col - 1] == " " and row[col] in "T>u", c.label
