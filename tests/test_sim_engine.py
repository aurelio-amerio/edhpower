import random

from edhpower.config import load_config
from edhpower.sim.combos import select_lines
from edhpower.sim.engine import CLOCKS, Game, Perm, play_game
from edhpower.sim.model import build_sim_deck
from edhpower.spellbook import ComboData, ComboFlags, ComboLine, ComboPiece

from .conftest import make_card, sim_facts

CFG = load_config().sim
CMD = make_card("Zhulodok, Void Gorger", cmc=7.0, mana_cost="{7}", type_line="Legendary Creature — Eldrazi", power="6", toughness="6")
BLUE_CMD = make_card("Blue Commander", cmc=2.0, mana_cost="{U}{U}", type_line="Legendary Creature — Wizard", power="2", toughness="2", colors=["U"])
WASTES = make_card("Wastes", cmc=0.0, mana_cost="", type_line="Basic Land", oracle_text="({T}: Add {C}.)", produced_mana=["C"])
FOREST = make_card("Forest", cmc=0.0, mana_cost="", type_line="Basic Land — Forest", oracle_text="({T}: Add {G}.)", produced_mana=["G"])
ISLAND = make_card("Island", cmc=0.0, mana_cost="", type_line="Basic Land — Island", oracle_text="({T}: Add {U}.)", produced_mana=["U"])
TOMB = make_card("Ancient Tomb", cmc=0.0, mana_cost="", type_line="Land", oracle_text="{T}: Add {C}{C}. Ancient Tomb deals 2 damage to you.", produced_mana=["C"])
SOL_RING = make_card("Sol Ring", cmc=1.0, mana_cost="{1}", oracle_text="{T}: Add {C}{C}.", produced_mana=["C"])
VAULT = make_card("Mana Vault", cmc=1.0, mana_cost="{1}", oracle_text="Mana Vault doesn't untap during your untap step.\n{T}: Add {C}{C}{C}.", produced_mana=["C"])
CLOCK = make_card("Unwinding Clock", cmc=4.0, mana_cost="{4}", oracle_text="Untap all artifacts you control during each other player's untap step.")
OPAL = make_card("Mox Opal", cmc=0.0, mana_cost="{0}", oracle_text="Metalcraft — {T}: Add one mana of any color. Activate only if you control three or more artifacts.", produced_mana=["W", "U", "B", "R", "G"])
INCUBATOR = make_card("Urza's Incubator", cmc=3.0, mana_cost="{3}", oracle_text="As Urza's Incubator enters, choose a creature type.\nCreature spells of the chosen type cost {2} less to cast.")
CITY = make_card("City of Traitors", cmc=0.0, mana_cost="", type_line="Land", oracle_text="When you play another land, sacrifice City of Traitors.\n{T}: Add {C}{C}.", produced_mana=["C"])
MINE = make_card("Urza's Mine", cmc=0.0, mana_cost="", type_line="Land — Urza's Mine", oracle_text="{T}: Add {C}.", produced_mana=["C"])
PLANT = make_card("Urza's Power Plant", cmc=0.0, mana_cost="", type_line="Land — Urza's Power-Plant", oracle_text="{T}: Add {C}.", produced_mana=["C"])
TOWER = make_card("Urza's Tower", cmc=0.0, mana_cost="", type_line="Land — Urza's Tower", oracle_text="{T}: Add {C}.", produced_mana=["C"])
BASALT = make_card("Basalt Monolith", cmc=3.0, mana_cost="{3}", oracle_text="Basalt Monolith doesn't untap during your untap step.\n{T}: Add {C}{C}{C}.\n{3}: Untap Basalt Monolith.", produced_mana=["C"])
MONUMENT = make_card("Forsaken Monument", cmc=5.0, mana_cost="{5}", oracle_text="Colorless spells you cast cost {1} less to cast.\nWhenever you tap a permanent for {C}, add an additional {C}.")
TUTOR = make_card("Demonic Tutor", cmc=2.0, mana_cost="{1}{B}", type_line="Sorcery", oracle_text="Search your library for a card, put that card into your hand, then shuffle.", colors=["B"])
SWAMP = make_card("Swamp", cmc=0.0, mana_cost="", type_line="Basic Land — Swamp", oracle_text="({T}: Add {B}.)", produced_mana=["B"])
BEAR = make_card("Grizzly Bears", cmc=2.0, mana_cost="{1}{G}", type_line="Creature — Bear", power="2", toughness="2", colors=["G"])
BIG = make_card("Ulamog, the Ceaseless Hunger", cmc=10.0, mana_cost="{10}", type_line="Legendary Creature — Eldrazi", power="10", toughness="10")
ELDRAZI = make_card("Endbringer", cmc=6.0, mana_cost="{5}{C}", type_line="Creature — Eldrazi", power="5", toughness="5")
RITUAL = make_card("Pyre Charger", cmc=0.0, mana_cost="{0}", oracle_text="{T}, Sacrifice Pyre Charger: Add {C}.", produced_mana=["C"])
ALL_IS_DUST = make_card("All Is Dust", cmc=7.0, mana_cost="{7}", type_line="Sorcery", oracle_text="Each player sacrifices all colored permanents they control.")
RAMP = make_card("Traverse the Wastes", cmc=2.0, mana_cost="{2}", type_line="Sorcery", oracle_text="Search your library for a land card and put it onto the battlefield tapped.")


def _deck(commander, entries, tags=None, combos=None):
    """entries: list of (card, count). Returns (SimDeck, lines)."""
    cards = [commander] + [c for c, _ in entries]
    text = f"1 {commander['name']}\n\n" + "".join(f"{n} {c['name']}\n" for c, n in entries)
    facts = sim_facts(text, cards, tags if tags is not None else {}, combos)
    return build_sim_deck(facts, CFG), select_lines(facts, CFG)[0]


def _game(deck, lines=(), seed=1, target=4):
    return Game(deck, list(lines), CFG, random.Random(seed), target)


def _cards(deck, *names):
    return [deck.cards[n] for n in names]


def test_forty_wastes_cast_a_seven_drop_on_turn_seven():
    deck, _ = _deck(CMD, [(WASTES, 40)])
    rec = play_game(deck, [], CFG, random.Random(3), tipping_target=4)
    assert rec.clocks["commander"] == 7 and rec.clocks["mana_threshold"] == 7 and rec.clocks["tipping_target"] == 4
    assert rec.mana_by_turn[1:8] == [1, 2, 3, 4, 5, 6, 7] and rec.idle_by_turn[6] and not rec.idle_by_turn[7]
    assert rec.clocks["threat"] is None and rec.clocks["combo"] is None
    assert rec.clocks["combat"] is None   # 6 power from turn 8 never reaches 40 by turn 12


def test_two_mana_lands_and_colours():
    deck, _ = _deck(CMD, [(TOMB, 40)])
    assert play_game(deck, [], CFG, random.Random(0), 4).clocks["commander"] == 4
    deck, _ = _deck(BLUE_CMD, [(FOREST, 40)])
    assert play_game(deck, [], CFG, random.Random(0), 2).clocks["commander"] is None
    deck, _ = _deck(BLUE_CMD, [(ISLAND, 40)])
    assert play_game(deck, [], CFG, random.Random(0), 2).clocks["commander"] == 2


def test_rock_cast_this_turn_adds_mana_immediately():
    deck, _ = _deck(CMD, [(WASTES, 39), (SOL_RING, 1)])
    g = _game(deck)
    g.turn, g.hand, g.board = 1, ["Sol Ring"], [Perm(deck.cards["Wastes"], 0)]
    g.pool = g._produce()
    g._main_phase()
    assert g.produced == 3 and not g.hand and any(p.card.name == "Sol Ring" and p.tapped for p in g.board)


def test_monolith_rocks_stay_tapped_until_an_untap_engine():
    deck, _ = _deck(CMD, [(WASTES, 38), (VAULT, 1), (CLOCK, 1)])
    g = _game(deck)
    g.board = [Perm(deck.cards["Wastes"], 0)]
    g.turn, g.hand = 1, ["Mana Vault"]
    g.pool = g._produce(); g._main_phase()
    assert g.produced == 4
    g.take_turn()   # turn 2: Vault is still tapped, only the land produces
    assert g.produced == 1 + (1 if any(p.card.is_land and p.entered == 2 for p in g.board) else 0)
    g.board.append(Perm(deck.cards["Unwinding Clock"], 2))
    g.take_turn()   # turn 3: the engine untapped the Vault
    assert g.produced >= 3 + 1


def test_metalcraft_rock_needs_three_artifacts():
    deck, _ = _deck(CMD, [(WASTES, 37), (OPAL, 1), (SOL_RING, 1), (VAULT, 1)])
    g = _game(deck)
    g.turn, g.board = 3, [Perm(deck.cards["Wastes"], 0), Perm(deck.cards["Mox Opal"], 1)]
    assert len(g._produce()) == 1
    g.board += [Perm(deck.cards["Sol Ring"], 1), Perm(deck.cards["Mana Vault"], 1, tapped=True)]
    for p in g.board:
        p.tapped = p.card.name == "Mana Vault"
    assert len(g._produce()) == 1 + 1 + 2   # Wastes, Opal (metalcraft on), Sol Ring


def test_reducer_applies_to_matching_spells_only():
    deck, _ = _deck(CMD, [(WASTES, 36), (INCUBATOR, 1), (ELDRAZI, 1), (BEAR, 1), (FOREST, 1)])
    g = _game(deck)
    g.board = [Perm(deck.cards["Wastes"], 0) for _ in range(4)] + [Perm(deck.cards["Urza's Incubator"], 0)]
    assert g._reduction_for(deck.cards["Endbringer"]) == 2 and g._reduction_for(deck.cards["Grizzly Bears"]) == 0
    g.turn, g.hand = 5, ["Endbringer"]
    g.pool = g._produce(); g._main_phase()
    assert "Endbringer" not in g.hand   # {5}{C} paid with 4 colourless after −2 generic


def test_city_of_traitors_is_sacrificed_on_the_next_land_drop():
    deck, _ = _deck(CMD, [(CITY, 1), (WASTES, 39)])
    g = _game(deck)
    g.turn, g.hand, g.board = 1, ["City of Traitors", "Wastes"], []
    g._play_land()
    assert [p.card.name for p in g.board] == ["City of Traitors"]
    g.turn = 2
    g._play_land()
    assert [p.card.name for p in g.board] == ["Wastes"]


def test_tron_completes_to_seven():
    deck, _ = _deck(CMD, [(MINE, 1), (PLANT, 1), (TOWER, 1), (WASTES, 37)])
    g = _game(deck)
    g.turn, g.board = 3, [Perm(deck.cards["Urza's Mine"], 0), Perm(deck.cards["Urza's Power Plant"], 0)]
    assert len(g._produce()) == 2
    for p in g.board:
        p.tapped = False
    g.board.append(Perm(deck.cards["Urza's Tower"], 0))
    assert len(g._produce()) == 7
    g.hand = ["Urza's Tower", "Wastes"]
    g.board = [Perm(deck.cards["Urza's Mine"], 0), Perm(deck.cards["Urza's Power Plant"], 0)]
    g._play_land()
    assert g.board[-1].card.name == "Urza's Tower"


def test_combo_line_fires_when_pieces_and_mana_are_there():
    line = ComboLine("c1", (ComboPiece("Basalt Monolith", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), ("Infinite colorless mana",), "", 0, "R", 10, "", "")
    combos = ComboData("C", [line], 0, {}, {"c1": ComboFlags("c1", True, False, 5, False, False, False, False, True)}, "R", "2026-09-10T00:00:00Z")
    deck, lines = _deck(CMD, [(BASALT, 1), (MONUMENT, 1), (WASTES, 38)], combos=combos)
    assert len(lines) == 1
    g = _game(deck, lines)
    g.turn, g.hand = 5, ["Forsaken Monument"]
    g.board = [Perm(deck.cards["Basalt Monolith"], 3, tapped=True)] + [Perm(deck.cards["Wastes"], 0) for _ in range(5)]
    g.pool = g._produce(); g._main_phase()
    assert g.record.clocks["combo"] == 5 and g.record.clocks["lethal_combo"] is None
    assert {p.card.name for p in g.board} >= {"Basalt Monolith", "Forsaken Monument"}


def test_tutor_digs_for_the_missing_piece():
    line = ComboLine("c1", (ComboPiece("Basalt Monolith", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), ("Infinite colorless mana",), "", 0, "R", 10, "", "")
    combos = ComboData("C", [line], 0, {}, {"c1": ComboFlags("c1", True, False, 5, False, False, False, False, True)}, "R", "2026-09-10T00:00:00Z")
    deck, lines = _deck(CMD, [(BASALT, 1), (MONUMENT, 1), (TUTOR, 1), (SWAMP, 1), (WASTES, 36)], tags={"tutor": ["Demonic Tutor"]}, combos=combos)
    g = _game(deck, lines)
    g.turn, g.hand = 3, ["Demonic Tutor"]
    g.board = [Perm(deck.cards["Basalt Monolith"], 2, tapped=True), Perm(deck.cards["Swamp"], 0), Perm(deck.cards["Wastes"], 0)]
    g.library = [n for n in g.library if n != "Forsaken Monument"] + ["Forsaken Monument"]
    g.pool = g._produce(); g._main_phase()
    assert "Forsaken Monument" in g.hand and "Demonic Tutor" not in g.hand and "Forsaken Monument" not in g.library


def test_combat_clock_counts_creatures_from_the_turn_after_they_enter():
    deck, _ = _deck(CMD, [(BIG, 4), (WASTES, 36)])
    g = _game(deck)
    g.board = [Perm(deck.cards["Ulamog, the Ceaseless Hunger"], 0) for _ in range(4)] + [Perm(deck.cards["Wastes"], 0)]
    g.hand, g.library = [], ["Wastes"] * 20
    g.take_turn()
    assert g.damage == 40 and g.record.clocks["combat"] == 1
    g2 = _game(deck)
    g2.board = [Perm(deck.cards["Wastes"], 0)]
    g2.hand, g2.library = ["Ulamog, the Ceaseless Hunger"], ["Wastes"] * 20
    g2.take_turn()
    assert g2.damage == 0


def test_record_shape():
    deck, _ = _deck(CMD, [(WASTES, 40)])
    rec = play_game(deck, [], CFG, random.Random(5), 4)
    assert set(rec.clocks) == set(CLOCKS) and len(rec.mana_by_turn) == CFG.max_turn + 1 and len(rec.idle_by_turn) == CFG.max_turn + 1


def test_doubler_adds_one_unit_per_source_tapped_not_per_mana_produced():
    deck, _ = _deck(CMD, [(TOMB, 1), (MONUMENT, 1), (WASTES, 38)])
    g = _game(deck)
    g.board = [Perm(deck.cards["Ancient Tomb"], 0), Perm(deck.cards["Forsaken Monument"], 0)]
    assert len(g._produce()) == 3   # Ancient Tomb taps once for 2 colourless; the doubler adds exactly 1, not 2 more


def test_doubler_does_not_bonus_a_colourless_one_shot():
    deck, _ = _deck(CMD, [(RITUAL, 1), (MONUMENT, 1), (WASTES, 38)])
    g = _game(deck)
    g.turn, g.hand, g.board = 1, ["Pyre Charger"], [Perm(deck.cards["Forsaken Monument"], 0)]
    g.pool = g._produce()
    g._cast("Pyre Charger")
    assert g.produced == 1   # no permanent was tapped for {C}, so the doubler must not bonus the ritual's own mana


def test_try_one_shot_casts_only_when_it_enables_another_cast():
    deck, _ = _deck(CMD, [(WASTES, 37), (RITUAL, 1), (SOL_RING, 1), (BEAR, 1)])
    g = _game(deck)
    g.turn, g.hand, g.board = 1, ["Pyre Charger", "Sol Ring"], []
    g.pool = g._produce()
    assert g._try_pay(deck.cards["Sol Ring"]) is None    # unpayable before the ritual's mana
    assert g._try_one_shot() is True
    assert "Pyre Charger" not in g.hand and g.produced == 1
    assert g._try_pay(deck.cards["Sol Ring"]) is not None   # the ritual's mana now pays for it

    g2 = _game(deck, seed=2)
    g2.turn, g2.hand, g2.board = 1, ["Pyre Charger", "Grizzly Bears"], []
    g2.pool = g2._produce()
    assert g2._try_one_shot() is False   # Bears needs {G}; the ritual only ever makes {C}, so nothing is enabled
    assert "Pyre Charger" in g2.hand and g2.produced == 0 and g2.pool == []


def test_fetch_land_puts_a_tapped_land_and_reports_when_the_library_has_none():
    deck, _ = _deck(CMD, [(RAMP, 1), (WASTES, 30), (TOMB, 8)], tags={"land-ramp": ["Traverse the Wastes"]})
    g = _game(deck)
    g.turn, g.hand, g.board = 3, ["Traverse the Wastes"], [Perm(deck.cards["Wastes"], 0), Perm(deck.cards["Wastes"], 0)]
    g.library = ["Ancient Tomb", "Wastes", "Wastes"]
    g.pool = g._produce()
    g._cast("Traverse the Wastes")
    assert "Traverse the Wastes" not in g.hand
    fetched = [p for p in g.board if p.entered == 3 and p.card.name == "Wastes"]
    assert len(fetched) == 1 and fetched[0].tapped is True   # a 1-mana land enters tapped, producing nothing this turn
    assert g.library == ["Ancient Tomb", "Wastes"]   # the 2-mana Ancient Tomb was skipped; only one Wastes consumed

    board_len = len(g.board)
    g.library = ["Ancient Tomb"]   # no 1-mana land left
    assert g._fetch_land() is False
    assert len(g.board) == board_len   # nothing added


def test_threat_clock_stamps_for_a_high_mv_sorcery_cast_from_hand():
    deck, _ = _deck(CMD, [(ALL_IS_DUST, 1), (WASTES, 39)])
    g = _game(deck)
    g.turn, g.hand, g.board, g.command_zone = 7, ["All Is Dust"], [Perm(deck.cards["Wastes"], 0) for _ in range(7)], set()
    g.pool = g._produce()
    g._main_phase()
    assert "All Is Dust" not in g.hand and g.record.clocks["threat"] == 7


from edhpower.payoffs import detect

BALLISTA_40 = make_card("Walking Ballista", cmc=40.0, mana_cost="{40}", type_line="Artifact Creature — Construct", power="0", toughness="0",
                        oracle_text="This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nRemove a +1/+1 counter from this creature: It deals 1 damage to any target.")
TREMORS_2 = make_card("Impact Tremors", cmc=2.0, mana_cost="{2}", type_line="Enchantment",
                      oracle_text="Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.")
TREMORS_40 = make_card("Impact Tremors", cmc=40.0, mana_cost="{40}", type_line="Enchantment",
                       oracle_text="Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.")


BIG_CMD = make_card("Big Commander", cmc=20.0, mana_cost="{20}", type_line="Legendary Creature — Eldrazi", power="1", toughness="1")   # never castable: keeps the mana for the pieces


def _payoff_line(produces):
    line = ComboLine("pl", (ComboPiece("Basalt Monolith", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), tuple(produces), "", 0, "R", 1, "", "")
    return ComboData("C", [line], 0, {}, {"pl": ComboFlags("pl", True, False, 5, False, False, False, False, True)}, "R", "2026-09-10T00:00:00Z")


def _deck_lines(commander, entries, combos, tags=None):
    cards = [commander] + [c for c, _ in entries]
    text = f"1 {commander['name']}\n\n" + "".join(f"{n} {c['name']}\n" for c, n in entries)
    facts = sim_facts(text, cards, tags if tags is not None else {}, combos)
    return build_sim_deck(facts, CFG), select_lines(facts, CFG, detect(facts))[0]


def _staged_game(deck, lines, payoff_name):
    """Turn 5 board of 8 Wastes; both pieces in hand; payoff drawn on turn 8 (library pops from the end)."""
    g = _game(deck, lines)
    g.turn = 5
    g.board = [Perm(deck.cards["Wastes"], 0) for _ in range(8)]
    g.hand = ["Basalt Monolith", "Forsaken Monument"]
    g.library = [payoff_name, "Wastes", "Wastes"]
    return g


def _run_to(g, turn):
    while g.turn < turn:
        g.take_turn()
    return g.record.clocks


def test_payoff_line_in_hand_counts_for_infinite_mana():
    deck, lines = _deck_lines(BIG_CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1), (BALLISTA_40, 1)], _payoff_line(["Infinite colorless mana"]), tags={"mana-sink": ["Walking Ballista"]})
    assert lines[0].status == "payoff" and lines[0].payoff.hand_ok
    g = _staged_game(deck, lines, "Walking Ballista")
    clocks = _run_to(g, 8)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] == 8   # Ballista costs 40 (Monument doubles land mana, so 20 would be castable): never cast, but in hand is enough


def test_payoff_line_needs_the_battlefield_for_etb():
    deck, lines = _deck_lines(BIG_CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1), (TREMORS_2, 1)], _payoff_line(["Infinite creature ETB"]))
    assert lines[0].status == "payoff" and not lines[0].payoff.hand_ok
    clocks = _run_to(_staged_game(deck, lines, "Impact Tremors"), 8)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] == 8   # drawn and cast on turn 8, checked after the main phase
    deck, lines = _deck_lines(BIG_CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1), (TREMORS_40, 1)], _payoff_line(["Infinite creature ETB"]))
    clocks = _run_to(_staged_game(deck, lines, "Impact Tremors"), 12)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] is None   # in hand only: not enough for a battlefield payoff


def test_no_payoff_line_never_goes_lethal_and_direct_line_does_at_once():
    deck, lines = _deck_lines(BIG_CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1)], _payoff_line(["Infinite colorless mana"]))
    assert lines[0].status == "no_payoff"
    clocks = _run_to(_staged_game(deck, lines, "Wastes"), 12)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] is None
    deck, lines = _deck_lines(BIG_CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1)], _payoff_line(["Infinite colorless mana", "Infinite damage"]))
    clocks = _run_to(_staged_game(deck, lines, "Wastes"), 12)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] == 6


def test_payoff_already_on_board_stamps_lethal_at_assembly():
    deck, lines = _deck_lines(BIG_CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1), (TREMORS_2, 1)], _payoff_line(["Infinite creature ETB"]))
    g = _staged_game(deck, lines, "Wastes")
    g.board.append(Perm(deck.cards["Impact Tremors"], 0))
    clocks = _run_to(g, 7)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] == 6


# ---- tokens, triggers, counters, ramp counts, board diagnostics ---------------------------------

from edhpower.sim.effects import Effect
from edhpower.sim.engine import OPPONENTS
from edhpower.sim.model import token_card

from .test_sim_effects import (AVENGER, BALOTHS, CULTIVATE, GRIZZLY_BEARS, HARROW, INTANGIBLE_VIRTUE, LOTUS_COBRA, MIRKWOOD_BATS,
                               NECROBLOOM, OPP_LANDFALL)

# Hand-written: "Whenever another creature you control enters, each opponent loses 1 life."
OTHER_CREATURE_DRAIN = r"""Name:Drain Watcher
ManaCost:1 B
Types:Creature Human
PT:1/1
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Creature.Other+YouCtrl | TriggerZones$ Battlefield | Execute$ TrigLoseLife | TriggerDescription$ Whenever another creature you control enters, each opponent loses 1 life.
SVar:TrigLoseLife:DB$ LoseLife | LifeAmount$ 1 | Defined$ Player.Opponent
Oracle:Whenever another creature you control enters, each opponent loses 1 life.
"""

BALOTHS_C = make_card("Rampaging Baloths", cmc=6.0, mana_cost="{4}{G}{G}", type_line="Creature — Beast", power="6", toughness="6", colors=["G"])
AVENGER_C = make_card("Avenger of Zendikar", cmc=7.0, mana_cost="{5}{G}{G}", type_line="Creature — Elemental", power="5", toughness="5", colors=["G"])
NECROBLOOM_C = make_card("The Necrobloom", cmc=4.0, mana_cost="{1}{W}{B}{G}", type_line="Legendary Creature — Plant", power="2", toughness="7", colors=["W", "B", "G"])
VIRTUE_C = make_card("Intangible Virtue", cmc=2.0, mana_cost="{1}{W}", type_line="Enchantment", colors=["W"])
COBRA_C = make_card("Lotus Cobra", cmc=2.0, mana_cost="{1}{G}", type_line="Creature — Snake", power="2", toughness="1", colors=["G"])
BATS_C = make_card("Mirkwood Bats", cmc=4.0, mana_cost="{3}{B}", type_line="Creature — Bat", power="2", toughness="3", colors=["B"])
WATCHER_C = make_card("Drain Watcher", cmc=2.0, mana_cost="{1}{B}", type_line="Creature — Human", power="1", toughness="1", colors=["B"])
HARROW_C = make_card("Harrow", cmc=3.0, mana_cost="{2}{G}", type_line="Instant", colors=["G"])
CULTIVATE_C = make_card("Cultivate", cmc=3.0, mana_cost="{2}{G}", type_line="Sorcery", colors=["G"])
PLAINS = make_card("Plains", cmc=0.0, mana_cost="", type_line="Basic Land — Plains", oracle_text="({T}: Add {W}.)", produced_mana=["W"])
MOUNTAIN = make_card("Mountain", cmc=0.0, mana_cost="", type_line="Basic Land — Mountain", oracle_text="({T}: Add {R}.)", produced_mana=["R"])
SAVANNAH = make_card("Savannah", cmc=0.0, mana_cost="", type_line="Land — Forest Plains", oracle_text="({T}: Add {G} or {W}.)", produced_mana=["G", "W"])
BAYOU = make_card("Bayou", cmc=0.0, mana_cost="", type_line="Land — Swamp Forest", oracle_text="({T}: Add {B} or {G}.)", produced_mana=["B", "G"])

SCRIPTS = {"Rampaging Baloths": BALOTHS, "Avenger of Zendikar": AVENGER, "The Necrobloom": NECROBLOOM, "Intangible Virtue": INTANGIBLE_VIRTUE,
           "Lotus Cobra": LOTUS_COBRA, "Mirkwood Bats": MIRKWOOD_BATS, "Drain Watcher": OTHER_CREATURE_DRAIN, "Harrow": HARROW,
           "Cultivate": CULTIVATE, "Grizzly Bears": GRIZZLY_BEARS}


def _fx_deck(commander, entries, tags=None, scripts=None):
    cards = [commander] + [c for c, _ in entries]
    text = f"1 {commander['name']}\n\n" + "".join(f"{n} {c['name']}\n" for c, n in entries)
    facts = sim_facts(text, cards, tags if tags is not None else {}, None, scripts=scripts if scripts is not None else SCRIPTS)
    return build_sim_deck(facts, CFG)


def _staged(deck, board, hand=(), library=("Forest",) * 20, turn=0):
    """A game with a hand-placed board; distinct land names follow the board."""
    g = _game(deck)
    g.turn, g.hand, g.library = turn, list(hand), list(library)
    g.board = [Perm(deck.cards[n], 0) for n in board]
    g.distinct_lands = {p.card.name for p in g.board if p.card.is_land}
    return g


def _tokens(g, type_):
    return sum(1 for p in g.board if p.card.role == "token" and type_ in p.card.subtypes)


def test_landfall_token_maker_makes_one_token_per_land_drop():
    deck = _fx_deck(CMD, [(FOREST, 39), (BALOTHS_C, 1)])
    g = _staged(deck, ["Forest"] * 5, hand=["Rampaging Baloths"], turn=3)
    for _ in range(3):
        g.take_turn()
    assert any(p.card.name == "Rampaging Baloths" and p.entered == 4 for p in g.board)
    assert g.record.tokens_by_turn["Beast"][4:7] == [0, 1, 2]
    assert g.record.lands_by_turn[4:7] == [6, 7, 8] and g.record.landfall_by_turn[4:7] == [1, 1, 1]


def test_tokens_attack_from_the_turn_after_they_enter():
    deck = _fx_deck(CMD, [(FOREST, 39), (BALOTHS_C, 1)])
    g = _staged(deck, ["Forest"] * 2 + ["Rampaging Baloths"], turn=4)
    g.command_zone = set()
    g.take_turn()   # turn 5: a Beast enters, it cannot attack yet
    assert _tokens(g, "Beast") == 1 and g.record.board_power_by_turn[5] == 6
    g.take_turn()   # turn 6: last turn's Beast attacks; this turn's does not
    assert _tokens(g, "Beast") == 2 and g.record.board_power_by_turn[6] == 6 + 4


def test_zombie_threshold_needs_seven_distinct_names():
    deck = _fx_deck(NECROBLOOM_C, [(FOREST, 40)])
    g = _staged(deck, ["The Necrobloom"], hand=["Forest"] * 12)
    for t in range(1, 13):
        g.turn = t
        g._play_land()
    assert _tokens(g, "Zombie") == 0 and _tokens(g, "Plant") == 12

    deck = _fx_deck(NECROBLOOM_C, [(FOREST, 10), (ISLAND, 5), (SWAMP, 5), (PLAINS, 5), (MOUNTAIN, 5), (SAVANNAH, 1), (BAYOU, 1)])
    order = ["Forest", "Island", "Swamp", "Plains", "Mountain", "Savannah", "Forest", "Bayou", "Forest"]
    g = _staged(deck, ["The Necrobloom"])
    zombies = []
    for t, land in enumerate(order, 1):
        g.turn, g.hand = t, [land]
        g._play_land()
        zombies.append(_tokens(g, "Zombie"))
    assert len(g.distinct_lands) == 7
    assert zombies == [0, 0, 0, 0, 0, 0, 0, 1, 2]   # the eighth drop brings the seventh name: it makes the first Zombie
    assert _tokens(g, "Plant") == 7


def test_etb_tokens_scale_with_lands():
    deck = _fx_deck(CMD, [(FOREST, 39), (AVENGER_C, 1)])
    g = _staged(deck, ["Forest"] * 6, hand=["Avenger of Zendikar"], turn=7)
    g.command_zone = set()
    g.pool = g._produce()
    g.pool += g.pool[:1]   # 7 mana for a 7-drop
    g._cast("Avenger of Zendikar")
    assert _tokens(g, "Plant") == 6
    assert all(p.entered == 7 and p.card.power == 0 for p in g.board if p.card.role == "token")


def test_landfall_counters_hit_tokens_of_type():
    deck = _fx_deck(CMD, [(FOREST, 38), (AVENGER_C, 1), (BALOTHS_C, 1)])
    g = _staged(deck, ["Forest", "Avenger of Zendikar", "Rampaging Baloths"], hand=["Forest"], turn=3)
    plant, beast = token_card("Plant", 0, 1), token_card("Beast", 4, 4)
    g.board += [Perm(plant, 1), Perm(plant, 1), Perm(beast, 1)]
    g._play_land()
    assert [p.counters for p in g.board if p.card.role == "token"] == [1, 1, 0, 0]   # the Beast it just made is not a Plant
    assert all(p.counters == 0 for p in g.board if p.card.role != "token")


def test_anthem_adds_to_tokens_only_when_scoped():
    deck = _fx_deck(CMD, [(FOREST, 38), (VIRTUE_C, 1), (BEAR, 1)])
    g = _staged(deck, ["Forest", "Intangible Virtue", "Grizzly Bears"], turn=5)
    beast = token_card("Beast", 4, 4)
    g.board += [Perm(beast, 2) for _ in range(3)]
    assert g._anthem_bonus(beast) == 1 and g._anthem_bonus(deck.cards["Grizzly Bears"]) == 0
    assert g._board_power() == 3 * 5 + 2


def test_landfall_mana_enters_the_pool():
    deck = _fx_deck(CMD, [(FOREST, 39), (COBRA_C, 1)])
    base = _staged(deck, ["Forest"] * 2, hand=["Forest"], turn=2)
    base.take_turn()
    cobra = _staged(deck, ["Forest"] * 2 + ["Lotus Cobra"], hand=["Forest"], turn=2)
    cobra.take_turn()
    assert cobra.record.landfall_by_turn[3] == 1
    assert cobra.record.mana_by_turn[3] == base.record.mana_by_turn[3] + 1


def test_creature_etb_fires_for_other_creatures_only():
    deck = _fx_deck(CMD, [(SWAMP, 38), (WATCHER_C, 1), (BEAR, 1)])
    g = _staged(deck, ["Swamp", "Swamp"], hand=["Drain Watcher"], library=["Swamp"] * 5, turn=3)
    g.command_zone = set()
    g.pool = g._produce()
    g._cast("Drain Watcher")
    assert g.life == [CFG.lethal_damage] * OPPONENTS   # its own entry does not trigger it
    g.board.append(Perm(deck.cards["Grizzly Bears"], 3))
    g._creature_entered(g.board[-1])
    assert g.life == [CFG.lethal_damage - 1] * OPPONENTS


def test_token_created_drain_fires_per_token():
    deck = _fx_deck(CMD, [(FOREST, 38), (BATS_C, 1), (AVENGER_C, 1)])
    g = _staged(deck, ["Forest"] * 5 + ["Mirkwood Bats"], hand=["Avenger of Zendikar"], turn=7)
    g.command_zone = set()
    g.pool = g._produce() + [frozenset("G")] * 2
    g._cast("Avenger of Zendikar")
    assert _tokens(g, "Plant") == 5
    assert g.life == [CFG.lethal_damage - 5] * OPPONENTS


def test_single_target_drain_hits_the_opponent_with_most_life():
    deck = _fx_deck(CMD, [(FOREST, 40)])
    g = _staged(deck, [])
    g.life = [10, 12, 12]
    g._fire(Effect("landfall", "drain", 3, each_opponent=False), None)
    assert g.life == [10, 9, 12]


def test_opponents_land_trigger_never_fires():
    deck = _fx_deck(CMD, [(FOREST, 39), (BALOTHS_C, 1)], scripts={**SCRIPTS, "Rampaging Baloths": OPP_LANDFALL})
    g = _staged(deck, ["Forest", "Rampaging Baloths"], turn=1)
    g.command_zone = set()
    for _ in range(4):
        g.take_turn()
    assert _tokens(g, "Beast") == 0 and sum(g.record.landfall_by_turn) == 4


def test_ramp_spell_puts_as_many_lands_as_its_script_says():
    deck = _fx_deck(CMD, [(FOREST, 38), (HARROW_C, 1), (BALOTHS_C, 1)], tags={"land-ramp": ["Harrow"]})
    g = _staged(deck, ["Forest"] * 3 + ["Rampaging Baloths"], hand=["Harrow"], turn=4)
    g.command_zone = set()
    g.pool = g._produce()
    g._cast("Harrow")
    assert _tokens(g, "Beast") == 2
    assert sum(1 for p in g.board if p.card.is_land) == 4   # 3 − 1 sacrificed + 2 fetched
    assert g.landfalls == 2


def test_ramp_sacrifice_keeps_a_needed_colour_and_distinct_names():
    deck = _fx_deck(BLUE_CMD, [(FOREST, 37), (ISLAND, 1), (HARROW_C, 1), (BEAR, 1)], tags={"land-ramp": ["Harrow"]})
    g = _staged(deck, ["Island", "Forest", "Forest"], hand=["Harrow"], library=["Forest"] * 5, turn=4)
    g.command_zone = {"Blue Commander"}
    g.pool = g._produce()
    g._cast("Harrow")
    assert any(p.card.name == "Island" for p in g.board)   # the commander's only blue source survives
    assert g.distinct_lands == {"Island", "Forest"}
    g = _staged(deck, ["Island", "Forest", "Forest"], hand=["Harrow"], library=["Forest"] * 5, turn=4)
    g.command_zone = set()   # nothing needs blue now: the Island is the first lowest-priority land
    g.pool = g._produce()
    g._cast("Harrow")
    assert not any(p.card.name == "Island" for p in g.board) and g.distinct_lands == {"Forest"}


def test_ramp_spell_second_land_to_hand():
    deck = _fx_deck(CMD, [(FOREST, 39), (CULTIVATE_C, 1)], tags={"land-ramp": ["Cultivate"]})
    g = _staged(deck, ["Forest"] * 3, hand=["Cultivate"], library=["Forest"] * 5, turn=4)
    g.command_zone = set()
    g.pool = g._produce()
    g._cast("Cultivate")
    assert g.hand == ["Forest"] and len(g.library) == 3
    assert sum(1 for p in g.board if p.card.is_land) == 4


def test_board_diagnostics_shape():
    deck = _fx_deck(CMD, [(FOREST, 39), (BALOTHS_C, 1)])
    rec = play_game(deck, [], CFG, random.Random(5), 4)
    n = CFG.max_turn + 1
    assert len(rec.board_power_by_turn) == n and len(rec.lands_by_turn) == n and len(rec.landfall_by_turn) == n
    assert set(rec.tokens_by_turn) == {"Beast"} and len(rec.tokens_by_turn["Beast"]) == n
