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
    assert two.status == "no_payoff" and three.status == "direct"
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


from edhpower.payoffs import detect
from edhpower.sim.combos import PayoffNeed, SimLine, classify, is_lock_only, payoff_ready, resources_of

TREMORS = make_card("Impact Tremors", cmc=2.0, mana_cost="{1}{R}", type_line="Enchantment", colors=["R"],
                    oracle_text="Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.")
BALLISTA = make_card("Walking Ballista", cmc=0.0, mana_cost="{X}{X}", type_line="Artifact Creature — Construct", power="0", toughness="0",
                     oracle_text="This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nRemove a +1/+1 counter from this creature: It deals 1 damage to any target.")
FIELD = make_card("Field of the Dead", cmc=0.0, mana_cost="", type_line="Land", produced_mana=["C"],
                  oracle_text="This land enters tapped.\n{T}: Add {C}.\nWhenever this land or another land you control enters, if you control seven or more lands with different names, create a 2/2 black Zombie creature token.")
HOOF = make_card("Craterhoof Behemoth", cmc=8.0, mana_cost="{5}{G}{G}{G}", type_line="Creature — Beast", power="5", toughness="5", colors=["G"],
                 oracle_text="Haste\nWhen this creature enters, creatures you control gain trample and get +X/+X until end of turn, where X is the number of creatures you control.")


def _facts_with(lines, extra_cards=(), tags=None):
    """Like _facts, plus extra make_card() objects in the 99."""
    base = _facts(lines)
    if not extra_cards:
        return base
    cards = [make_card("Ulalek, Fused Atrocity", cmc=5.0, mana_cost="{C/W}{C/U}{C/B}{C/R}{C/G}", type_line="Legendary Creature — Eldrazi", power="2", toughness="5"),
             make_card("Basalt Monolith", cmc=3.0, mana_cost="{3}"), make_card("Forsaken Monument", cmc=5.0, mana_cost="{5}"),
             make_card("Kinnan, Bonder Prodigy", cmc=2.0, mana_cost="{G}{U}", type_line="Legendary Creature — Human Druid", colors=["G", "U"]),
             make_card("Strionic Resonator", cmc=2.0, mana_cost="{2}"), make_card("Spawn-Gang Commander", cmc=5.0, mana_cost="{4}{R}", type_line="Creature — Eldrazi Goblin", colors=["R"]),
             make_card("Wastes", cmc=0.0, mana_cost="", type_line="Basic Land", produced_mana=["C"]), *extra_cards]
    deck = ("1 Ulalek, Fused Atrocity\n\n1 Basalt Monolith\n1 Forsaken Monument\n1 Kinnan, Bonder Prodigy\n1 Strionic Resonator\n1 Spawn-Gang Commander\n30 Wastes\n"
            + "".join(f"1 {c['name']}\n" for c in extra_cards))
    return sim_facts(deck, cards, tags if tags is not None else {}, base.combos)


def test_resources_of_folds_near_infinite_and_ignores_unknown_features():
    assert resources_of(["Infinite colorless mana", "Near-infinite creature ETB", "Infinite landfall triggers", "Infinite storm count"], CFG) == ("mana", "etb", "landfall", "storm")
    assert resources_of(["Infinite tapped land tokens", "Lock"], CFG) == ()
    assert resources_of([], CFG) == ()


def test_is_lock_only():
    assert is_lock_only(["Prevent all damage that would be dealt to you", "Lock"], CFG)
    assert not is_lock_only(["Lock", "Infinite colorless mana"], CFG)
    assert not is_lock_only([], CFG)


def test_classify_direct_payoff_no_payoff_unmapped():
    mana = _line("m", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")])
    direct = _line("d", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], produces=("Infinite colorless mana", "Infinite damage"))
    empty = _line("e", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], produces=())
    no_sink = detect(_facts_with([mana]))
    with_sink = detect(_facts_with([mana], [BALLISTA], tags={"mana-sink": ["Walking Ballista"]}))
    assert classify(direct, CFG, no_sink) == ("direct", ("mana",), None)
    assert classify(mana, CFG, no_sink) == ("no_payoff", ("mana",), None)
    assert classify(mana, CFG, with_sink) == ("payoff", ("mana",), PayoffNeed(frozenset({"Walking Ballista"}), True))
    assert classify(empty, CFG, no_sink) == ("unmapped", (), None)


def test_classify_battlefield_only_resource_and_self_paying_piece():
    etb = _line("etb", [("Kinnan, Bonder Prodigy", "B"), ("Basalt Monolith", "B")], produces=("Infinite creature ETB",))
    p = detect(_facts_with([etb], [TREMORS]))
    assert classify(etb, CFG, p) == ("payoff", ("etb",), PayoffNeed(frozenset({"Impact Tremors"}), False))
    # the engine's own piece is a payoff: Purphoros-style text on a piece
    piece_payoff = make_card("Kinnan, Bonder Prodigy", cmc=2.0, mana_cost="{G}{U}", type_line="Legendary Creature — Human Druid", colors=["G", "U"],
                             oracle_text="Whenever another creature you control enters, this creature deals 2 damage to each opponent.")
    import dataclasses
    from edhpower.scryfall import CardData
    facts = _facts_with([etb])
    facts.entries = [dataclasses.replace(e, card=CardData.from_scryfall(piece_payoff)) if e.name == "Kinnan, Bonder Prodigy" else e for e in facts.entries]
    status, _, need = classify(etb, CFG, detect(facts))
    assert status == "payoff" and need.candidates == frozenset({"Kinnan, Bonder Prodigy"})


def test_classify_landfall_tokens_is_fuel_only_with_a_go_wide_payoff():
    land = _line("lf", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], produces=("Infinite landfall triggers",))
    assert classify(land, CFG, detect(_facts_with([land], [FIELD]))) == ("no_payoff", ("landfall",), None)
    status, _, need = classify(land, CFG, detect(_facts_with([land], [FIELD, HOOF])))
    assert status == "payoff" and need == PayoffNeed(frozenset({"Field of the Dead"}), False)


def test_select_lines_skips_lock_only_and_carries_status():
    lock = _line("lock", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], produces=("Prevent all damage that would be dealt to you", "Lock"))
    mana = _line("mana", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], popularity=3)
    direct = _line("direct", [("Kinnan, Bonder Prodigy", "B"), ("Basalt Monolith", "B")], produces=("Infinite damage",), popularity=2)
    simulated, skipped = select_lines(_facts_with([lock, mana, direct]), CFG)
    assert [(l.id, l.status, l.resources, l.lethal, l.payoff) for l in simulated] == [("mana", "no_payoff", ("mana",), False, None), ("direct", "direct", (), True, None)]
    assert [(s.label, s.reason) for s in skipped] == [("Basalt Monolith + Forsaken Monument", "lock only")]


def test_select_lines_accepts_precomputed_payoffs():
    mana = _line("mana", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")])
    facts = _facts_with([mana], [BALLISTA], tags={"mana-sink": ["Walking Ballista"]})
    (line,), _ = select_lines(facts, CFG, detect(facts))
    assert line.status == "payoff" and line.payoff.hand_ok


def test_payoff_ready_zone_rules():
    board_only = SimLine("x", "x", (), 0, False, "payoff", ("etb",), PayoffNeed(frozenset({"Impact Tremors"}), False))
    hand_ok = SimLine("y", "y", (), 0, False, "payoff", ("mana",), PayoffNeed(frozenset({"Walking Ballista"}), True))
    none = SimLine("z", "z", (), 0, False, "no_payoff", ("mana",), None)
    assert payoff_ready(board_only, {"Impact Tremors"}, set()) and not payoff_ready(board_only, set(), {"Impact Tremors"})
    assert payoff_ready(hand_ok, set(), {"Walking Ballista"}) and payoff_ready(hand_ok, {"Walking Ballista"}, set())
    assert not payoff_ready(none, {"Walking Ballista"}, {"Walking Ballista"})
