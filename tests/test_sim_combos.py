from dataclasses import replace

from edhpower.config import load_config
from edhpower.sim.combos import missing_pieces, pieces_to_cast, select_lines
from edhpower.spellbook import ComboData, ComboFlags, ComboLine, ComboPiece, ComboTemplate

from .conftest import make_card, sim_facts

CFG = load_config().sim


def _line(cid, pieces, templates=(), produces=("Infinite colorless mana",), mana="", mvn=None, prereq="", popularity=None):
    return ComboLine(cid, tuple(ComboPiece(n, tuple(z), False) for n, z in pieces), tuple(ComboTemplate(t, ("H",)) for t in templates),
                     tuple(produces), mana, mvn, "R", popularity, prereq, "")


def _facts(lines):
    cards = [make_card("Ulalek, Fused Atrocity", cmc=5.0, mana_cost="{C/W}{C/U}{C/B}{C/R}{C/G}", type_line="Legendary Creature — Eldrazi", power="2", toughness="5"),
             make_card("Basalt Monolith", cmc=3.0, mana_cost="{3}"), make_card("Forsaken Monument", cmc=5.0, mana_cost="{5}"),
             make_card("Kinnan, Bonder Prodigy", cmc=2.0, mana_cost="{G}{U}", type_line="Legendary Creature — Human Druid", colors=["G", "U"]),
             make_card("Strionic Resonator", cmc=2.0, mana_cost="{2}"), make_card("Spawn-Gang Commander", cmc=5.0, mana_cost="{4}{R}", type_line="Creature — Eldrazi Goblin", colors=["R"]),
             make_card("Wastes", cmc=0.0, mana_cost="", type_line="Basic Land", produced_mana=["C"])]
    flags = {l.id: ComboFlags(l.id, len(l.pieces) == 2, False, 5, False, False, False, False, True) for l in lines}
    combos = ComboData("C", list(lines), 0, {}, flags, "R", "2026-09-10T00:00:00Z")
    deck = "1 Ulalek, Fused Atrocity\n\n1 Basalt Monolith\n1 Forsaken Monument\n1 Kinnan, Bonder Prodigy\n1 Strionic Resonator\n1 Spawn-Gang Commander\n30 Wastes\n"
    return sim_facts(deck, cards, {}, combos)


def test_two_and_three_card_lines_are_selected_and_the_rest_explained():
    lines = [
        _line("two", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], popularity=100),
        _line("templated", [("Ulalek, Fused Atrocity", "B"), ("Forsaken Monument", "B"), ("Basalt Monolith", "B")], templates=("Eldrazi Creature Card with MV=4, 5 or 6",)),
        _line("three", [("Ulalek, Fused Atrocity", "B"), ("Strionic Resonator", "B"), ("Spawn-Gang Commander", "H")],
              produces=("Infinite colorless mana", "Infinite damage"), mana="{5}{C}{C}{R}{R}", mvn=9),
        _line("prereq", [("Kinnan, Bonder Prodigy", "B"), ("Basalt Monolith", "B")], prereq="You have at least three opponents."),
        _line("graveyard", [("Kinnan, Bonder Prodigy", "G"), ("Basalt Monolith", "B")]),
        _line("four", [("Kinnan, Bonder Prodigy", "B"), ("Basalt Monolith", "B"), ("Strionic Resonator", "B"), ("Forsaken Monument", "B")]),
    ]
    simulated, skipped = select_lines(_facts(lines), CFG)
    assert [l.id for l in simulated] == ["two", "three"]
    two, three = simulated
    assert two.label == "Basalt Monolith + Forsaken Monument" and two.extra_mana == 0 and two.lethal is False
    assert three.extra_mana == 9 and three.lethal is True
    assert three.pieces[0].name == "Ulalek, Fused Atrocity" and three.pieces[2].zones == frozenset({"H"})
    reasons = {s.label: s.reason for s in skipped}
    assert reasons["Ulalek, Fused Atrocity + Forsaken Monument + Basalt Monolith"].startswith("templated: Eldrazi Creature Card")
    assert reasons["Kinnan, Bonder Prodigy + Basalt Monolith"] in ("notable prerequisites", "piece in zone G")
    assert len(skipped) == 4 and any(r == "4+ pieces" for r in reasons.values())


def test_caps_keep_the_most_popular_lines():
    lines = [_line(f"l{i}", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], popularity=i) for i in range(5)]
    simulated, skipped = select_lines(_facts(lines), replace(CFG, max_two_card_lines=2))
    assert [l.id for l in simulated] == ["l4", "l3"] and all(s.reason == "over cap" for s in skipped) and len(skipped) == 3


def test_no_combo_data_means_no_lines():
    facts = _facts([])
    facts.combos = None
    assert select_lines(facts, CFG) == ([], [])


def test_extra_mana_falls_back_to_parsing_mana_needed():
    (line,), _ = select_lines(_facts([_line("x", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], mana="{2}{U}")]), CFG)
    assert line.extra_mana == 3


def test_pieces_to_cast_respects_zones():
    (three,), _ = select_lines(_facts([_line("three", [("Ulalek, Fused Atrocity", "BC"), ("Strionic Resonator", "B"), ("Spawn-Gang Commander", "H")])]), CFG)
    cz = {"Ulalek, Fused Atrocity"}
    assert pieces_to_cast(three, board=set(), hand={"Strionic Resonator", "Spawn-Gang Commander"}, command_zone=cz) == ["Strionic Resonator"]
    assert pieces_to_cast(three, board={"Strionic Resonator"}, hand={"Spawn-Gang Commander"}, command_zone=cz) == []
    assert pieces_to_cast(three, board={"Strionic Resonator", "Spawn-Gang Commander"}, hand=set(), command_zone=cz) is None   # H-only piece on the battlefield
    assert pieces_to_cast(three, board=set(), hand={"Spawn-Gang Commander"}, command_zone=cz) is None
    (two,), _ = select_lines(_facts([_line("two", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")])]), CFG)
    assert pieces_to_cast(two, board={"Basalt Monolith"}, hand={"Forsaken Monument"}, command_zone=set()) == ["Forsaken Monument"]
    assert missing_pieces(two, board={"Basalt Monolith"}, hand=set(), command_zone=set()) == ["Forsaken Monument"]
