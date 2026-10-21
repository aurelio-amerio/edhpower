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

RAMP_SCRIPT = ("Name:Traverse the Wastes\nManaCost:2\nTypes:Sorcery\n"
               "A:SP$ ChangeZone | Origin$ Library | Destination$ Battlefield | ChangeType$ Land | Tapped$ True | ChangeNum$ 1\n")


def _deck(commander, entries, tags=None, combos=None, scripts=None):
    """entries: list of (card, count). Returns (SimDeck, lines)."""
    cards = [commander] + [c for c, _ in entries]
    text = f"1 {commander['name']}\n\n" + "".join(f"{n} {c['name']}\n" for c, n in entries)
    facts = sim_facts(text, cards, tags if tags is not None else {}, combos, scripts=scripts)
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
    g.lands_played, g.land_drops = 0, 1
    g._land_step()
    assert [p.card.name for p in g.board] == ["City of Traitors"]
    g.turn, g.lands_played = 2, 0
    g._land_step()
    assert [p.card.name for p in g.board] == ["Wastes"] and g.graveyard == ["City of Traitors"]


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
    g.lands_played = 0
    g._land_step()
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
    deck, _ = _deck(CMD, [(RAMP, 1), (WASTES, 30), (TOMB, 8)], tags={"land-ramp": ["Traverse the Wastes"]},
                    scripts={"Traverse the Wastes": RAMP_SCRIPT})
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
        g.lands_played = 0
        g._land_step()
    assert _tokens(g, "Zombie") == 0 and _tokens(g, "Plant") == 12

    deck = _fx_deck(NECROBLOOM_C, [(FOREST, 10), (ISLAND, 5), (SWAMP, 5), (PLAINS, 5), (MOUNTAIN, 5), (SAVANNAH, 1), (BAYOU, 1)])
    order = ["Forest", "Island", "Swamp", "Plains", "Mountain", "Savannah", "Forest", "Bayou", "Forest"]
    g = _staged(deck, ["The Necrobloom"])
    zombies = []
    for t, land in enumerate(order, 1):
        g.turn, g.hand = t, [land]
        g.lands_played = 0
        g._land_step()
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
    g.lands_played = 0
    g._land_step()
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
    assert g.life == [CFG.life_per_opponent] * CFG.opponents   # its own entry does not trigger it
    g.board.append(Perm(deck.cards["Grizzly Bears"], 3))
    g._creature_entered(g.board[-1])
    assert g.life == [CFG.life_per_opponent - 1] * CFG.opponents


def test_token_created_drain_fires_per_token():
    deck = _fx_deck(CMD, [(FOREST, 38), (BATS_C, 1), (AVENGER_C, 1)])
    g = _staged(deck, ["Forest"] * 5 + ["Mirkwood Bats"], hand=["Avenger of Zendikar"], turn=7)
    g.command_zone = set()
    g.pool = g._produce() + [frozenset("G")] * 2
    g._cast("Avenger of Zendikar")
    assert _tokens(g, "Plant") == 5
    assert g.life == [CFG.life_per_opponent - 5] * CFG.opponents


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


# ---- three opponents, pumps held for lethal, win clocks ------------------------------------------

import dataclasses

from .test_sim_effects import OVERRUN

HUGE = make_card("Huge Thing", cmc=12.0, mana_cost="{12}", type_line="Creature — Eldrazi", power="45", toughness="45")
FORTY = make_card("Forty Thing", cmc=12.0, mana_cost="{12}", type_line="Creature — Eldrazi", power="40", toughness="40")
BRUTE = make_card("Brute", cmc=12.0, mana_cost="{12}", type_line="Creature — Beast", power="36", toughness="36")
OVERRUN_C = make_card("Overrun", cmc=5.0, mana_cost="{2}{G}{G}{G}", type_line="Sorcery", colors=["G"])


def _attack_game(deck, attackers, turn=0):
    g = _game(deck)
    g.turn, g.hand, g.library = turn, [], ["Wastes"] * 20
    g.command_zone = set()
    g.board = [Perm(deck.cards[n], 0) for n in attackers] + [Perm(deck.cards["Wastes"], 0)]
    return g


def test_single_huge_attacker_does_not_kill_the_table_in_one_swing():
    deck, _ = _deck(CMD, [(HUGE, 1), (WASTES, 39)])
    g = _attack_game(deck, ["Huge Thing"])
    g.take_turn()
    assert g.life == [-5, 40, 40]
    clocks = _run_to(g, 3)
    assert clocks["combat"] == 1 and clocks["first_opponent"] == 1
    assert clocks["lethal_table"] == 3 and clocks["win"] == 3


def test_three_forty_power_attackers_kill_the_table_in_one_swing():
    deck, _ = _deck(CMD, [(FORTY, 3), (WASTES, 37)])
    g = _attack_game(deck, ["Forty Thing"] * 3)
    g.take_turn()
    assert g.life == [0, 0, 0] and g.damage == 120
    assert g.record.clocks["lethal_table"] == 1 and g.record.clocks["win"] == 1 and g.record.clocks["first_opponent"] == 1


def test_pump_is_held_until_it_kills_someone():
    deck = _fx_deck(CMD, [(FOREST, 38), (BRUTE, 1), (OVERRUN_C, 1)], scripts={**SCRIPTS, "Overrun": OVERRUN})
    assert deck.cards["Overrun"].role == "held"
    g = _staged(deck, ["Forest"] * 5 + ["Brute"], hand=["Overrun"])
    g.command_zone = set()
    g.take_turn()   # 36 + 3 = 39 does not kill a 40-life opponent: held
    assert "Overrun" in g.hand and g.life == [4, 40, 40] and g.record.damage_by_turn[1] == 36
    g.life = [39, 5, 5]
    g.take_turn()   # 36 leaves 3; 39 kills: cast
    assert "Overrun" not in g.hand and g.life == [0, 5, 5] and g.record.damage_by_turn[2] == 39
    assert g.damage == 36 + 39 and g.record.clocks["first_opponent"] == 2
    g.take_turn()   # the pump ended with the turn
    assert g.record.damage_by_turn[3] == 36 and not g.pumps


def test_each_opponent_drain_hits_all_three():
    deck = _fx_deck(CMD, [(FOREST, 37), (SWAMP, 1), (WATCHER_C, 1), (BEAR, 1)])
    g = _staged(deck, ["Forest", "Swamp", "Drain Watcher"], hand=["Grizzly Bears"], turn=3)
    g.command_zone = set()
    g.board[-1].entered = 4   # cannot attack this turn: only the drain deals damage
    g.life = [1, 1, 1]
    g.take_turn()
    assert g.life == [0, 0, 0] and g.damage == 0
    assert g.record.damage_by_turn[4] == 3
    assert g.record.clocks["first_opponent"] == 4 and g.record.clocks["lethal_table"] == 4 and g.record.clocks["win"] == 4
    assert g.record.clocks["combat"] is None


def test_win_stamps_on_lethal_combo_too():
    deck, lines = _deck_lines(BIG_CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1)], _payoff_line(["Infinite colorless mana", "Infinite damage"]))
    clocks = _run_to(_staged_game(deck, lines, "Wastes"), 12)
    assert clocks["lethal_combo"] == 6 and clocks["win"] == 6 and clocks["lethal_table"] is None


def test_damage_by_turn_and_max_swing():
    deck, _ = _deck(CMD, [(BIG, 2), (WASTES, 38)])
    g = _attack_game(deck, ["Ulamog, the Ceaseless Hunger"])
    g.take_turn()
    g.board.append(Perm(deck.cards["Ulamog, the Ceaseless Hunger"], 2))
    _run_to(g, 3)
    assert g.record.damage_by_turn[1:4] == [10, 10, 20] and g.record.max_swing == 20
    assert len(g.record.damage_by_turn) == CFG.max_turn + 1


def test_token_created_does_not_make_tokens_from_tokens():
    deck = _fx_deck(CMD, [(FOREST, 39), (BALOTHS_C, 1)])
    card = dataclasses.replace(deck.cards["Rampaging Baloths"], effects=(Effect("token_created", "token", 1, 1, 1, "Elf"),))
    g = _staged(deck, ["Forest"])
    g.board.append(Perm(card, 0))
    g._fire(Effect("landfall", "token", 1, 4, 4, "Beast"), None)   # would recurse without the guard
    assert _tokens(g, "Beast") == 1 and _tokens(g, "Elf") == 0


# ---- stage 2: graveyard, sacrifice, mill, cast effects on resolution, spell policies, mass return -------------

from .test_sim_effects import (AFTERMATH_ANALYST, EVOLVING_WILDS, LIFE_FROM_THE_LOAM, SPLENDID_RECLAMATION, SPRINGBLOOM_DRUID,
                               TITANIA)
from .test_sim_model import CAST_TOKENS

SPLENDID_C = make_card("Splendid Reclamation", cmc=4.0, mana_cost="{3}{G}", type_line="Sorcery", colors=["G"])
LOAM_C = make_card("Life from the Loam", cmc=2.0, mana_cost="{1}{G}", type_line="Sorcery", colors=["G"])
ANALYST_C = make_card("Aftermath Analyst", cmc=2.0, mana_cost="{1}{G}", type_line="Creature — Elf Detective", power="1", toughness="3", colors=["G"])
TITANIA_C = make_card("Titania, Protector of Argoth", cmc=5.0, mana_cost="{3}{G}{G}", type_line="Legendary Creature — Elemental",
                      power="5", toughness="3", colors=["G"])
SPRINGBLOOM_C = make_card("Springbloom Druid", cmc=3.0, mana_cost="{2}{G}", type_line="Creature — Elf Druid", power="1", toughness="1", colors=["G"])
CAST_TOKENS_C = make_card("Cast Tokens", cmc=2.0, mana_cost="{1}{W}", type_line="Instant", colors=["W"])
WILDS_C = make_card("Evolving Wilds", cmc=0.0, mana_cost="", type_line="Land",
                    oracle_text="{T}, Sacrifice Evolving Wilds: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.")
BARRENS = make_card("Scoured Barrens", cmc=0.0, mana_cost="", type_line="Land",
                    oracle_text="Scoured Barrens enters tapped.\nWhen Scoured Barrens enters, you gain 1 life.\n{T}: Add {W} or {B}.",
                    produced_mana=["W", "B"])

SCRIPTS2 = {**SCRIPTS, "Splendid Reclamation": SPLENDID_RECLAMATION, "Life from the Loam": LIFE_FROM_THE_LOAM,
            "Aftermath Analyst": AFTERMATH_ANALYST, "Titania, Protector of Argoth": TITANIA, "Springbloom Druid": SPRINGBLOOM_DRUID,
            "Cast Tokens": CAST_TOKENS, "Evolving Wilds": EVOLVING_WILDS}


def _fx2(entries, tags=None):
    return _fx_deck(CMD, entries, tags=tags, scripts=SCRIPTS2)


def _lands(g):
    return [p for p in g.board if p.card.is_land]


def test_resolved_spells_go_to_the_graveyard():
    deck = _fx2([(FOREST, 39), (HARROW_C, 1)], tags={"land-ramp": ["Harrow"]})
    assert "held" not in {c.role for c in deck.cards.values()}
    g = _staged(deck, ["Forest"] * 3, hand=["Harrow"], turn=4)
    g.command_zone = set()
    g.pool = g._produce()
    g._cast("Harrow")
    assert g.graveyard == ["Forest", "Harrow"]   # the sacrificed land, then the resolved spell
    assert g._gy_lands() == ["Forest"]


def test_sacrificed_land_fires_land_sacrificed():
    deck = _fx2([(FOREST, 38), (HARROW_C, 1), (TITANIA_C, 1)], tags={"land-ramp": ["Harrow"]})
    g = _staged(deck, ["Forest"] * 3 + ["Titania, Protector of Argoth"], hand=["Harrow"], turn=4)
    g.command_zone = set()
    g.pool = g._produce()
    g._cast("Harrow")
    assert _tokens(g, "Elemental") == 1 and "Forest" in g.graveyard and "Harrow" in g.graveyard


def test_mill_fills_the_graveyard_from_the_top():
    deck = _fx2([(FOREST, 36), (ISLAND, 1), (SWAMP, 1), (MOUNTAIN, 1), (ANALYST_C, 1)])
    g = _staged(deck, ["Forest"] * 2, hand=["Aftermath Analyst"], library=["Swamp", "Mountain", "Island", "Forest"], turn=2)
    g.command_zone = set()
    g.pool = g._produce()
    g._cast("Aftermath Analyst")
    assert g.graveyard == ["Forest", "Island", "Mountain"] and g.library == ["Swamp"]   # top of the library is its end
    assert any(p.card.name == "Aftermath Analyst" for p in g.board)


def _splendid_game(deck, gy_lands, baloths, turn):
    board = ["Forest"] * 6 + (["Rampaging Baloths"] if baloths else [])
    g = _staged(deck, board, hand=["Splendid Reclamation"], turn=turn)
    g.command_zone = set()
    g.graveyard = ["Forest"] * gy_lands
    g.pool = g._produce()
    g._main_phase()
    return g


def test_mass_return_waits_for_four_lands_and_a_landfall_source():
    deck = _fx2([(FOREST, 38), (SPLENDID_C, 1), (BALOTHS_C, 1)])
    assert CFG.mass_return_min_lands == 4
    g = _splendid_game(deck, 3, True, 5)
    assert "Splendid Reclamation" in g.hand and g._gy_lands() == ["Forest"] * 3
    g = _splendid_game(deck, 4, True, 5)
    assert "Splendid Reclamation" not in g.hand and g.graveyard == ["Splendid Reclamation"]
    returned = [p for p in _lands(g) if p.entered == 5]
    assert len(returned) == 4 and all(p.tapped for p in returned) and _tokens(g, "Beast") == 4
    g = _splendid_game(deck, 4, False, 5)
    assert "Splendid Reclamation" in g.hand
    g = _splendid_game(deck, 4, False, CFG.max_turn - 1)
    assert "Splendid Reclamation" not in g.hand and len(_lands(g)) == 10


def test_return_lands_picks_best_priority_first():
    deck = _fx2([(FOREST, 37), (BARRENS, 1), (VIRTUE_C, 1), (TITANIA_C, 1)])
    assert deck.cards["Scoured Barrens"].enters_tapped and not deck.cards["Forest"].enters_tapped
    g = _staged(deck, ["Forest"] * 5, hand=["Titania, Protector of Argoth", "Intangible Virtue"], turn=5)
    g.command_zone = set()
    g.graveyard = ["Forest", "Scoured Barrens"]
    g.pool = g._produce()
    g._cast("Titania, Protector of Argoth")
    back = [p for p in _lands(g) if p.entered == 5]
    assert [p.card.name for p in back] == ["Scoured Barrens"] and back[0].tapped   # both enter tapped: the fixer wins
    assert g.graveyard == ["Forest"] and "Scoured Barrens" in g.distinct_lands


def test_loam_returns_three_lands_when_the_hand_lacks_one():
    deck = _fx2([(FOREST, 39), (LOAM_C, 1)])
    assert deck.cards["Life from the Loam"].role == "spell"
    g = _staged(deck, ["Forest"] * 3, hand=["Life from the Loam"], turn=5)
    g.command_zone = set()
    g.graveyard = ["Forest"] * 4
    g.pool = g._produce()
    g._main_phase()
    assert g.hand == ["Forest"] * 3 and g.graveyard == ["Forest", "Life from the Loam"]
    g = _staged(deck, ["Forest"] * 3, hand=["Life from the Loam", "Forest"], turn=5)
    g.command_zone = set()
    g.graveyard = ["Forest"] * 4
    g.pool = g._produce()
    g._main_phase()
    assert "Life from the Loam" in g.hand and g.graveyard == ["Forest"] * 4


def test_cast_effects_fire_on_resolution():
    deck = _fx2([(PLAINS, 39), (CAST_TOKENS_C, 1)])
    assert deck.cards["Cast Tokens"].role == "spell"
    g = _staged(deck, ["Plains"] * 2, hand=["Cast Tokens"], library=["Plains"] * 5, turn=2)
    g.command_zone = set()
    g.pool = g._produce()
    g._cast("Cast Tokens")
    assert _tokens(g, "Soldier") == 2 and g.graveyard == ["Cast Tokens"]


def test_token_spell_is_cast_in_the_main_phase():
    deck = _fx2([(PLAINS, 39), (CAST_TOKENS_C, 1)])
    g = _staged(deck, ["Plains"] * 2, hand=["Cast Tokens"], library=["Plains"] * 5, turn=2)
    g.command_zone = set()
    g.pool = g._produce()
    g._main_phase()
    assert _tokens(g, "Soldier") == 2 and not g.hand


def test_triggered_fetch_pays_its_land_cost():
    deck = _fx2([(FOREST, 39), (SPRINGBLOOM_C, 1)])
    g = _staged(deck, ["Forest"] * 2, hand=["Springbloom Druid"], library=["Forest"] * 5, turn=3)
    g.command_zone = set()
    g.pool = g._produce() + [frozenset("G")]
    g._cast("Springbloom Druid")
    fetched = [p for p in _lands(g) if p.entered == 3]
    assert len(_lands(g)) == 3 and len(fetched) == 2 and all(p.tapped for p in fetched)
    assert g.graveyard == ["Forest"] and len(g.library) == 3
    g = _staged(deck, [], hand=["Springbloom Druid"], library=["Forest"] * 5, turn=3)
    g.command_zone = set()
    g.pool = [frozenset("G")] * 3
    g._cast("Springbloom Druid")
    assert not _lands(g) and len(g.library) == 5 and g.graveyard == []
    assert any(p.card.name == "Springbloom Druid" for p in g.board)


def test_land_sacrifice_spares_an_uncracked_fetch():
    deck = _fx2([(FOREST, 38), (WILDS_C, 1), (HARROW_C, 1)], tags={"land-ramp": ["Harrow"]})
    assert any(e.on == "activated" and e.do == "fetch" for e in deck.cards["Evolving Wilds"].effects)
    g = _staged(deck, ["Evolving Wilds", "Forest", "Forest"], library=["Forest"] * 5, turn=4)
    assert g._sacrifice_lands(1) == 1
    assert g.graveyard == ["Forest"] and any(p.card.name == "Evolving Wilds" for p in g.board)
    g = _staged(deck, ["Evolving Wilds"], library=["Forest"] * 5, turn=4)
    assert g._sacrifice_lands(2) == 1 and g.graveyard == ["Evolving Wilds"]   # the only land qualifies after all


# ---- stage 2: land drops, lands from the graveyard, fetch lands, activated abilities, upkeep ---------------

from .test_sim_effects import AZUSA, EXPLORE, GITROG, MYRIAD_LANDSCAPE, RAMUNAP_EXCAVATOR, SAKURA_TRIBE_ELDER

AZUSA_C = make_card("Azusa, Lost but Seeking", cmc=3.0, mana_cost="{2}{G}", type_line="Legendary Creature — Human Monk",
                    power="1", toughness="2", colors=["G"])
RAMUNAP_C = make_card("Ramunap Excavator", cmc=3.0, mana_cost="{2}{G}", type_line="Creature — Snake Cleric", power="2", toughness="3",
                      colors=["G"])
MYRIAD_C = make_card("Myriad Landscape", cmc=0.0, mana_cost="", type_line="Land",
                     oracle_text="Myriad Landscape enters tapped.\n{T}: Add {C}.\n{2}, {T}, Sacrifice Myriad Landscape: Search your library "
                                 "for up to two basic land cards that share a land type, put them onto the battlefield tapped, then shuffle.",
                     produced_mana=["C"])
SAKURA_C = make_card("Sakura-Tribe Elder", cmc=2.0, mana_cost="{1}{G}", type_line="Creature — Snake Shaman", power="1", toughness="1",
                     colors=["G"])
GITROG_C = make_card("The Gitrog Monster", cmc=5.0, mana_cost="{3}{B}{G}", type_line="Legendary Creature — Frog Horror",
                     power="6", toughness="6", colors=["B", "G"])
EXPLORE_C = make_card("Explore", cmc=2.0, mana_cost="{1}{G}", type_line="Sorcery", oracle_text="You may play an additional land this turn.\nDraw a card.",
                      colors=["G"])
BLUE_THING = make_card("Blue Thing", cmc=2.0, mana_cost="{1}{U}", type_line="Artifact", colors=["U"])

SCRIPTS3 = {**SCRIPTS2, "Azusa, Lost but Seeking": AZUSA, "Ramunap Excavator": RAMUNAP_EXCAVATOR, "Myriad Landscape": MYRIAD_LANDSCAPE,
            "Sakura-Tribe Elder": SAKURA_TRIBE_ELDER, "The Gitrog Monster": GITROG, "Explore": EXPLORE}


def _fx3(entries, tags=None):
    return _fx_deck(CMD, entries, tags=tags, scripts=SCRIPTS3)


def _step(g, drops=1):
    g.lands_played, g.land_drops = 0, drops
    g._land_step()


def test_extra_land_statics_raise_the_drops():
    deck = _fx3([(FOREST, 37), (AZUSA_C, 1), (NECROBLOOM_C, 1)])
    g = _staged(deck, ["Forest", "Azusa, Lost but Seeking", "The Necrobloom"], hand=["Forest"] * 3, library=["Forest"] * 10, turn=3)
    g.command_zone = set()
    g.take_turn()
    assert g.land_drops == 3 and g.lands_played == 3
    assert g.record.landfall_by_turn[4] == 3 and len(_lands(g)) == 4 and _tokens(g, "Plant") == 3


def test_cast_extra_land_plays_another_land_this_turn():
    deck = _fx3([(FOREST, 39), (EXPLORE_C, 1)])
    assert deck.cards["Explore"].role == "spell"
    g = _staged(deck, ["Forest"] * 2, hand=["Explore", "Forest", "Forest"], library=["Forest"] * 10, turn=1)
    g.command_zone = set()
    g.take_turn()
    assert "Explore" in g.graveyard and g.land_drops == 2 and g.lands_played == 2
    assert g.record.landfall_by_turn[2] == 2 and len(_lands(g)) == 4


def test_explore_is_held_without_a_land_in_hand_or_before_the_drop_is_used():
    deck = _fx3([(FOREST, 39), (EXPLORE_C, 1)])
    explore = deck.cards["Explore"]
    g = _staged(deck, ["Forest"] * 2, hand=["Explore"], turn=2)
    g.lands_played, g.land_drops = 1, 1
    assert not g._spell_wanted(explore)
    g.hand.append("Forest")
    assert g._spell_wanted(explore)
    g.lands_played = 0
    assert not g._spell_wanted(explore)


def test_lands_are_played_from_the_graveyard_only_without_a_land_in_hand():
    deck = _fx3([(FOREST, 38), (BARRENS, 1), (RAMUNAP_C, 1)])
    g = _staged(deck, ["Ramunap Excavator"], hand=["Forest"], turn=3)
    g.graveyard = ["Scoured Barrens"]
    _step(g)
    assert g.hand == [] and g.graveyard == ["Scoured Barrens"] and [p.card.name for p in _lands(g)] == ["Forest"]
    g.turn = 4
    _step(g)
    assert g.graveyard == [] and [p.card.name for p in _lands(g)] == ["Forest", "Scoured Barrens"] and _lands(g)[1].tapped
    g = _staged(deck, [], turn=3)
    g.graveyard = ["Scoured Barrens"]
    _step(g)
    assert g.graveyard == ["Scoured Barrens"] and not _lands(g)


def test_free_fetch_is_cracked_on_entry():
    deck = _fx3([(FOREST, 38), (WILDS_C, 1), (BEAR, 1)])
    g = _staged(deck, ["Forest"], hand=["Evolving Wilds"], library=["Forest"] * 10 + ["Grizzly Bears"], turn=3)   # draws the Bears
    g.command_zone = set()
    g.take_turn()
    assert g._gy_lands() == ["Evolving Wilds"] and g.record.landfall_by_turn[4] == 2
    fetched = [p for p in _lands(g) if p.entered == 4]
    assert [p.card.name for p in fetched] == ["Forest"] and fetched[0].tapped


def test_fetch_replay_loop_uses_a_drop_each_time():
    deck = _fx3([(FOREST, 37), (WILDS_C, 1), (RAMUNAP_C, 1), (AZUSA_C, 1)])
    g = _staged(deck, ["Ramunap Excavator", "Azusa, Lost but Seeking"], library=["Forest"] * 10, turn=3)
    g.graveyard = ["Evolving Wilds"]
    g.lands_played, g.land_drops = 0, 1 + 2
    g._land_step()
    assert g.lands_played == 3 and g.landfalls == 6
    assert g.graveyard == ["Evolving Wilds"] and [p.card.name for p in _lands(g)] == ["Forest"] * 3 and len(g.library) == 7


def test_costed_fetch_waits_for_spare_mana():
    deck = _fx3([(FOREST, 39), (MYRIAD_C, 1)])
    assert deck.cards["Myriad Landscape"].enters_tapped
    for spare, cracked in ((2, True), (1, False)):
        g = _staged(deck, ["Myriad Landscape", "Forest", "Forest"], library=["Forest"] * 10, turn=4)
        g.command_zone = set()
        g.pool = [frozenset("G")] * spare
        g._main_phase()
        on_board = any(p.card.name == "Myriad Landscape" for p in g.board)
        assert on_board is not cracked
        if cracked:
            fetched = [p for p in _lands(g) if p.entered == 4]
            assert len(fetched) == 2 and all(p.tapped and p.card.mana == 1 for p in fetched)
            assert g.graveyard == ["Myriad Landscape"] and g.pool == []
        else:
            assert len(g.pool) == 1 and g.graveyard == []


def test_creature_fetch_cracks_the_turn_it_enters():
    deck = _fx3([(FOREST, 39), (SAKURA_C, 1)])
    assert deck.cards["Sakura-Tribe Elder"].role == "creature"
    g = _staged(deck, ["Forest"] * 2, hand=["Sakura-Tribe Elder"], library=["Forest"] * 10, turn=2)
    g.command_zone = set()
    g.pool = g._produce()
    g._main_phase()
    assert g.graveyard == ["Sakura-Tribe Elder"] and not any(p.card.name == "Sakura-Tribe Elder" for p in g.board)
    fetched = [p for p in _lands(g) if p.entered == 2]
    assert len(fetched) == 1 and fetched[0].tapped


def test_activated_mass_return_pays_and_sacrifices():
    deck = _fx3([(FOREST, 38), (ANALYST_C, 1), (BALOTHS_C, 1)])
    g = _staged(deck, ["Forest"] * 5 + ["Aftermath Analyst", "Rampaging Baloths"], turn=5)
    g.command_zone = set()
    g.graveyard = ["Forest"] * 4
    g.pool = g._produce()
    g._main_phase()
    assert g.graveyard == ["Aftermath Analyst"] and len(_lands(g)) == 9 and g.casts == 0
    assert _tokens(g, "Beast") == 4 and len(g.pool) == 1
    g = _staged(deck, ["Forest"] * 5 + ["Aftermath Analyst", "Rampaging Baloths"], turn=5)
    g.command_zone = set()
    g.graveyard = ["Forest"] * 3
    g.pool = g._produce()
    g._main_phase()
    assert any(p.card.name == "Aftermath Analyst" for p in g.board) and g._gy_lands() == ["Forest"] * 3


def test_upkeep_sacrifice_land_prefers_a_land_then_the_permanent():
    deck = _fx3([(FOREST, 37), (ISLAND, 1), (BLUE_THING, 1), (GITROG_C, 1)])
    g = _staged(deck, ["The Gitrog Monster", "Forest", "Forest"], turn=3)
    g._upkeep()
    assert len(_lands(g)) == 1 and g.graveyard == ["Forest"] and any(p.card.name == "The Gitrog Monster" for p in g.board)
    g = _staged(deck, ["The Gitrog Monster", "Island", "Forest"], hand=["Blue Thing"], turn=3)
    g.command_zone = set()
    g._upkeep()
    assert [p.card.name for p in _lands(g)] == ["Island"] and g.graveyard == ["Forest"]
    g = _staged(deck, ["The Gitrog Monster"], turn=3)
    g._upkeep()
    assert g.graveyard == ["The Gitrog Monster"] and not g.board


def test_upkeep_runs_before_the_land_drops_are_counted():
    deck = _fx3([(FOREST, 39), (GITROG_C, 1)])
    g = _staged(deck, ["The Gitrog Monster"], hand=["Forest", "Forest"], library=["Forest"] * 10, turn=3)
    g.command_zone = set()
    g.take_turn()   # no land at upkeep: Gitrog goes, and its extra land drop with it
    assert "The Gitrog Monster" in g.graveyard and g.land_drops == 1 and g.lands_played == 1
    g = _staged(deck, ["The Gitrog Monster", "Forest"], hand=["Forest", "Forest"], library=["Forest"] * 10, turn=3)
    g.command_zone = set()
    g.take_turn()
    assert g.graveyard == ["Forest"] and g.land_drops == 2 and g.lands_played == 2


def test_fetch_priority_is_a_tapped_fixer():
    deck = _fx3([(FOREST, 38), (WILDS_C, 1), (MYRIAD_C, 1)])
    g = _staged(deck, [], library=["Forest"] * 10, turn=3)
    wilds = deck.cards["Evolving Wilds"]
    assert g._land_priority(wilds, frozenset()) == 3 and g._land_priority(wilds, frozenset("G"), tapped=True) == 3
    assert g._land_priority(deck.cards["Myriad Landscape"], frozenset()) == 2   # a costed fetch is unchanged
    g.hand = ["Evolving Wilds", "Forest"]
    _step(g)
    assert [p.card.name for p in _lands(g)] == ["Forest"] and g.hand == ["Evolving Wilds"]


def test_board_diagnostics_stage2():
    deck = _fx3([(FOREST, 38), (WILDS_C, 1), (BEAR, 1)])
    rec = play_game(deck, [], CFG, random.Random(5), 4)
    n = CFG.max_turn + 1
    assert len(rec.graveyard_lands_by_turn) == n and len(rec.distinct_lands_by_turn) == n
    g = _staged(deck, ["Forest"], hand=["Evolving Wilds"], library=["Forest"] * 10 + ["Grizzly Bears"], turn=3)
    g.command_zone = set()
    g.take_turn()
    assert g.record.graveyard_lands_by_turn[4] == 1 and g.record.distinct_lands_by_turn[4] == 1


# ---- stage 2: dredge in the draw step, Cultivator chains -----------------------------------------------------

COLOSSUS_C = make_card("Cultivator Colossus", cmc=7.0, mana_cost="{4}{G}{G}{G}", type_line="Creature — Plant Beast", power="*",
                       toughness="*", colors=["G"])


def _fx5(entries, tags=None):
    return _fx_deck(CMD, entries, tags=tags, scripts=SCRIPTS3)


def _draw_game(deck, board, hand, graveyard, library, turn=3, drops=1):
    g = _staged(deck, board, hand=hand, library=library, turn=turn)
    g.command_zone = set()
    g.graveyard = list(graveyard)
    g.land_drops = drops
    return g


def test_dredge_replaces_the_draw_only_when_the_hand_lacks_a_land():
    deck = _fx5([(FOREST, 38), (NECROBLOOM_C, 1), (BEAR, 1)])
    g = _draw_game(deck, ["The Necrobloom"], ["Grizzly Bears"], ["Forest"], ["Grizzly Bears"] * 5)
    g._draw_step()
    assert g.dredged and sorted(g.hand) == ["Forest", "Grizzly Bears"] and len(g.library) == 3
    assert g.graveyard == ["Grizzly Bears"] * 2   # the Forest left, two cards were milled
    g = _draw_game(deck, ["The Necrobloom"], ["Forest"], ["Forest"], ["Grizzly Bears"] * 5)
    g._draw_step()
    assert not g.dredged and g.hand == ["Forest", "Grizzly Bears"] and g.graveyard == ["Forest"] and len(g.library) == 4
    g = _draw_game(deck, ["Forest"], ["Grizzly Bears"], ["Forest"], ["Grizzly Bears"] * 5)   # no dredge source
    g._draw_step()
    assert not g.dredged and g.graveyard == ["Forest"] and g.hand == ["Grizzly Bears"] * 2


def test_dredged_is_reset_each_turn():
    deck = _fx5([(FOREST, 38), (NECROBLOOM_C, 1), (BEAR, 1)])
    g = _draw_game(deck, ["The Necrobloom"], ["Grizzly Bears"], ["Forest"], ["Grizzly Bears"] * 10)
    g.take_turn()
    assert g.dredged and g.record.landfall_by_turn[4] == 1   # the dredged Forest is played
    g.take_turn()
    assert not g.dredged   # no land in the graveyard: a plain draw


def test_dredge_never_replaces_the_opening_hand(monkeypatch):
    deck = _fx5([(FOREST, 38), (NECROBLOOM_C, 1), (BEAR, 1)])
    g = _game(deck)
    assert len(g.hand) in (6, 7) and g.turn == 0
    calls = []
    monkeypatch.setattr(g, "_draw_step", lambda: calls.append(g.turn))
    g.take_turn()
    assert calls == []
    g.take_turn()
    assert calls == [2]


def test_dredge_needs_enough_library():
    deck = _fx5([(FOREST, 37), (NECROBLOOM_C, 1), (BEAR, 1), (LOAM_C, 1)])
    g = _draw_game(deck, ["The Necrobloom"], ["Grizzly Bears"], ["Forest", "Life from the Loam"], ["Grizzly Bears"])
    g._draw_step()   # dredge 2 and dredge 3 both need more cards than the library holds: draw the last one
    assert not g.dredged and g.hand == ["Grizzly Bears"] * 2 and g.library == []
    assert g.graveyard == ["Forest", "Life from the Loam"]
    g = _draw_game(deck, ["The Necrobloom"], ["Grizzly Bears"], ["Forest", "Life from the Loam"], ["Grizzly Bears"] * 2)
    g._draw_step()   # exactly two cards: the land dredge 2 is taken
    assert g.dredged and g.library == [] and "Forest" in g.hand
    g = _draw_game(deck, [], ["Grizzly Bears"], ["Forest", "Life from the Loam"], ["Grizzly Bears"] * 2)
    g._draw_step()   # only Loam's dredge 3 is available and the library is short: draw
    assert not g.dredged and g.graveyard == ["Forest", "Life from the Loam"] and len(g.library) == 1
    g = _draw_game(deck, [], ["Grizzly Bears"], [], [])
    g._draw_step()   # an empty library never crashes
    assert not g.dredged and g.hand == ["Grizzly Bears"]


def test_self_dredge_card_comes_back_when_it_would_be_cast():
    deck = _fx5([(FOREST, 38), (LOAM_C, 1), (BEAR, 1)])
    assert any(e.on == "static" and e.do == "dredge" and e.type == "" for e in deck.cards["Life from the Loam"].effects)
    g = _draw_game(deck, ["Forest"], ["Grizzly Bears"], ["Forest", "Life from the Loam"], ["Grizzly Bears"] * 5)
    g._draw_step()
    assert g.dredged and sorted(g.hand) == ["Grizzly Bears", "Life from the Loam"] and len(g.library) == 2
    assert g.graveyard == ["Forest"] + ["Grizzly Bears"] * 3
    g = _draw_game(deck, ["Forest"], ["Forest"], ["Forest", "Life from the Loam"], ["Grizzly Bears"] * 5)
    g._draw_step()
    assert not g.dredged and g.hand == ["Forest", "Grizzly Bears"] and "Life from the Loam" in g.graveyard
    g = _draw_game(deck, ["Forest"], ["Grizzly Bears"], ["Life from the Loam"], ["Grizzly Bears"] * 5)
    g._draw_step()   # no land in the graveyard: Loam would not be cast
    assert not g.dredged and g.graveyard == ["Life from the Loam"]


def test_land_dredge_beats_self_dredge():
    deck = _fx5([(FOREST, 37), (NECROBLOOM_C, 1), (LOAM_C, 1), (BEAR, 1)])
    g = _draw_game(deck, ["The Necrobloom"], ["Grizzly Bears"], ["Life from the Loam", "Forest"], ["Grizzly Bears"] * 5)
    g._draw_step()
    assert g.dredged and sorted(g.hand) == ["Forest", "Grizzly Bears"] and len(g.library) == 3
    assert "Life from the Loam" in g.graveyard


def _colossus_game(deck, board, hand, graveyard, library):
    g = _staged(deck, ["Forest"] * 7 + board, hand=["Cultivator Colossus", *hand], library=library, turn=7)
    g.command_zone = set()
    g.graveyard = list(graveyard)
    g.lands_played = g.land_drops = 1   # the turn's drop is already used: the chain needs none
    g.pool = g._produce()
    g._cast("Cultivator Colossus")
    return g


def test_chain_plays_every_land_in_hand_and_draws_between():
    deck = _fx5([(FOREST, 37), (COLOSSUS_C, 1), (BEAR, 1), (NECROBLOOM_C, 1)])
    assert Effect("etb", "chain_lands_from_hand") in deck.cards["Cultivator Colossus"].effects
    g = _colossus_game(deck, [], ["Forest"] * 3, [], ["Grizzly Bears"] * 10)
    chained = [p for p in _lands(g) if p.entered == 7]
    assert len(chained) == 3 and all(p.tapped for p in chained)
    assert g.hand == ["Grizzly Bears"] * 3 and len(g.library) == 7
    assert g.landfalls == 3 and g.lands_played == 1
    # with land dredge and lands in the graveyard, each draw dredges a land back and the chain continues
    g = _colossus_game(deck, ["The Necrobloom"], ["Forest"], ["Forest"] * 3, ["Grizzly Bears"] * 10)
    assert g.landfalls == 4 and g._gy_lands() == [] and len(g.library) == 10 - 3 * 2 - 1
    assert g.hand == ["Grizzly Bears"] and _tokens(g, "Plant") == 4


def test_chain_is_capped():
    deck = _fx5([(FOREST, 38), (COLOSSUS_C, 1), (BEAR, 1)])
    assert CFG.chain_cap == 20
    g = _colossus_game(deck, [], ["Forest"], [], ["Forest"] * 50)
    assert g.landfalls == CFG.chain_cap and len(g.library) == 50 - CFG.chain_cap and g.hand == ["Forest"]


# ---- stage 3: land-milled and dies triggers, triggered draw, reanimation --------------------------------------

from .test_sim_effects import DREAD_RETURN, HEDGE_SHREDDER, HORIZON_CANOPY, SUN_TITAN, WORLD_SHAPER

DREAD_C = make_card("Dread Return", cmc=4.0, mana_cost="{2}{B}{B}", type_line="Sorcery", colors=["B"])
VICTIMIZE_C = make_card("Victimize", cmc=3.0, mana_cost="{2}{B}", type_line="Sorcery", colors=["B"])
SUN_TITAN_C = make_card("Sun Titan", cmc=6.0, mana_cost="{4}{W}{W}", type_line="Creature — Giant", power="6", toughness="6", colors=["W"])
SHAPER_C = make_card("World Shaper", cmc=4.0, mana_cost="{3}{G}", type_line="Creature — Merfolk Shaman", power="3", toughness="3", colors=["G"])
SHREDDER_C = make_card("Hedge Shredder", cmc=4.0, mana_cost="{2}{G}{G}", type_line="Artifact — Vehicle", power="5", toughness="5", colors=["G"])
CANOPY_C = make_card("Horizon Canopy", cmc=0.0, mana_cost="", type_line="Land",
                     oracle_text="{T}, Pay 1 life: Add {G} or {W}.\n{1}, {T}, Sacrifice Horizon Canopy: Draw a card.", produced_mana=["G", "W"])
THREE_C = make_card("Three Thing", cmc=3.0, mana_cost="{3}", type_line="Artifact")

SCRIPTS8 = {**SCRIPTS3, "Dread Return": DREAD_RETURN, "Sun Titan": SUN_TITAN, "World Shaper": WORLD_SHAPER,
            "Hedge Shredder": HEDGE_SHREDDER, "Horizon Canopy": HORIZON_CANOPY}


def _fx8(entries, tags=None):
    return _fx_deck(CMD, entries, tags=tags, scripts=SCRIPTS8)


def _on_board(g, name):
    return [p for p in g.board if p.card.name == name]


def test_land_milled_fires_once_per_mill_with_a_land():
    deck = _fx8([(FOREST, 37), (GITROG_C, 1), (BEAR, 1), (ISLAND, 1)])
    g = _staged(deck, ["The Gitrog Monster"], library=["Grizzly Bears"] * 3 + ["Forest", "Grizzly Bears", "Island"], turn=3)
    assert g._mill(3) == ["Island", "Grizzly Bears", "Forest"]
    assert g.hand == ["Grizzly Bears"] and len(g.library) == 2   # two lands, one mill: one draw
    g._mill(1)
    assert g.hand == ["Grizzly Bears"] and len(g.library) == 1   # no land milled: no draw
    g = _staged(deck, ["The Gitrog Monster", "Forest", "Forest", "Forest"], library=["Grizzly Bears"] * 5, turn=3)
    g._sacrifice_lands(2)
    assert g.hand == ["Grizzly Bears"] * 2   # land_sacrificed draws once per land


def test_milled_lands_return_exactly_once():
    deck = _fx8([(FOREST, 35), (SHREDDER_C, 1), (NECROBLOOM_C, 1), (GITROG_C, 1), (BEAR, 1), (ISLAND, 1), (SWAMP, 1)])
    lib = ["Grizzly Bears"] * 3 + ["Swamp", "Island"]
    g = _draw_game(deck, ["Hedge Shredder", "The Necrobloom"], ["Grizzly Bears"], ["Forest", "Forest"], lib)
    g._draw_step()
    assert g.dredged and sorted(g.hand) == ["Forest", "Grizzly Bears"]
    back = [p for p in _lands(g) if p.card.name in ("Island", "Swamp")]
    assert sorted(p.card.name for p in back) == ["Island", "Swamp"] and all(p.tapped for p in back)
    assert g.graveyard == ["Forest"] and g.landfalls == 2 and _tokens(g, "Plant") == 2   # the older Forest stays
    g = _draw_game(deck, ["Hedge Shredder", "The Gitrog Monster", "The Necrobloom"], ["Grizzly Bears"], ["Forest", "Forest"], lib)
    g._draw_step()
    assert g.dredged and sorted(g.hand) == ["Forest", "Grizzly Bears", "Grizzly Bears"] and len(g.library) == 2
    assert g.graveyard == ["Forest"] and g.landfalls == 2


def test_dies_returns_lands():
    deck = _fx8([(SWAMP, 34), (FOREST, 1), (ISLAND, 1), (VICTIMIZE_C, 1), (SHAPER_C, 1), (BALOTHS_C, 1), (AVENGER_C, 1)])
    assert Effect("dies", "return_lands", "all") in deck.cards["World Shaper"].effects
    g = _staged(deck, ["Swamp"] * 3 + ["World Shaper"], hand=["Victimize"], turn=5)
    g.command_zone = set()
    g.graveyard = ["Forest", "Island", "Swamp", "Rampaging Baloths", "Avenger of Zendikar"]
    g.pool = g._produce()
    g._main_phase()
    assert g._gy_lands() == [] and len(_lands(g)) == 6 and g.landfalls == 3
    assert g.graveyard == ["World Shaper", "Victimize"]
    assert _on_board(g, "Avenger of Zendikar") and _on_board(g, "Rampaging Baloths") and g.record.clocks["reanimate"] == 5


def test_reanimate_policy_and_target():
    deck = _fx8([(SWAMP, 36), (DREAD_C, 1), (BEAR, 1), (BALOTHS_C, 1)])
    assert CFG.reanimate_min_power == 4
    g = _staged(deck, ["Swamp"] * 4, hand=["Dread Return"], library=["Swamp"] * 10, turn=6)
    g.command_zone = set()
    g.graveyard = ["Grizzly Bears", "Rampaging Baloths"]
    g.pool = g._produce()
    g._main_phase()
    baloths = _on_board(g, "Rampaging Baloths")
    assert baloths and baloths[0].entered == 6 and g.graveyard == ["Grizzly Bears", "Dread Return"]
    assert g.record.clocks["reanimate"] == 6
    g = _staged(deck, ["Swamp"] * 4, hand=["Dread Return"], library=["Swamp"] * 10, turn=6)
    g.command_zone = set()
    g.graveyard = ["Grizzly Bears"]
    g.pool = g._produce()
    g._main_phase()
    assert g.hand == ["Dread Return"] and g.graveyard == ["Grizzly Bears"] and g.record.clocks["reanimate"] is None


def test_sun_titan_returns_a_cheap_permanent_or_a_land():
    deck = _fx8([(PLAINS, 34), (SUN_TITAN_C, 1), (WILDS_C, 1), (THREE_C, 1), (BALOTHS_C, 1), (DREAD_C, 1), (FOREST, 1)])
    g = _staged(deck, ["Plains"] * 6, hand=["Sun Titan"], library=["Forest"] * 10, turn=6)
    g.command_zone = set()
    g.graveyard = ["Evolving Wilds", "Three Thing", "Rampaging Baloths", "Dread Return"]
    g.pool = g._produce()
    g._cast("Sun Titan")
    assert _on_board(g, "Three Thing") and g.graveyard == ["Evolving Wilds", "Rampaging Baloths", "Dread Return"]
    assert g.record.clocks["reanimate"] is None   # a noncreature permanent is not the reanimate clock
    g = _staged(deck, ["Plains"] * 6 + ["Rampaging Baloths"], hand=["Sun Titan"], library=["Forest"] * 10, turn=6)
    g.command_zone = set()
    g.graveyard = ["Evolving Wilds"]
    g.pool = g._produce()
    g._cast("Sun Titan")
    wilds = _on_board(g, "Evolving Wilds")
    assert wilds and wilds[0].tapped and g.graveyard == [] and g.landfalls == 1 and _tokens(g, "Beast") == 1


def test_sacrifice_cost_prefers_a_token_and_refuses_when_empty():
    deck = _fx8([(SWAMP, 37), (VICTIMIZE_C, 1), (ELDRAZI, 1), (AVENGER_C, 1)])
    g = _staged(deck, ["Swamp"] * 3 + ["Endbringer"], hand=["Victimize"], library=["Swamp"] * 10, turn=5)
    g.board.append(Perm(token_card("Saproling", 1, 1), 0))
    g.command_zone = set()
    g.graveyard = ["Avenger of Zendikar"]
    g.pool = g._produce()
    g._main_phase()
    assert _on_board(g, "Endbringer") and not _tokens(g, "Saproling") and _on_board(g, "Avenger of Zendikar")
    assert g.graveyard == ["Victimize"]
    g = _staged(deck, ["Swamp"] * 3, hand=["Victimize"], library=["Swamp"] * 10, turn=5)
    g.command_zone = set()
    g.graveyard = ["Avenger of Zendikar"]
    g.pool = g._produce()
    g._main_phase()
    assert g.hand == ["Victimize"] and g.graveyard == ["Avenger of Zendikar"] and len(g.pool) == 3


def test_horizon_land_draws_when_the_hand_is_empty():
    deck = _fx8([(FOREST, 38), (CANOPY_C, 1), (BIG, 1)])
    assert any(e.on == "activated" and e.do == "draw" for e in deck.cards["Horizon Canopy"].effects)
    g = _staged(deck, ["Horizon Canopy", "Forest"], library=["Forest"] * 10, turn=4)
    g.command_zone = set()
    g.pool = [frozenset("G")]
    g._main_phase()
    assert g.graveyard == ["Horizon Canopy"] and g.hand == ["Forest"] and g.pool == [] and len(g.library) == 9
    g = _staged(deck, ["Horizon Canopy", "Forest"], hand=["Ulamog, the Ceaseless Hunger"], library=["Forest"] * 10, turn=4)
    g.command_zone = set()
    g.pool = [frozenset("G")]
    g._main_phase()
    assert _on_board(g, "Horizon Canopy") and g.hand == ["Ulamog, the Ceaseless Hunger"] and len(g.pool) == 1


def test_triggered_draw_is_never_a_dredge():
    deck = _fx8([(FOREST, 36), (GITROG_C, 1), (NECROBLOOM_C, 1), (BEAR, 1), (ISLAND, 1)])
    g = _draw_game(deck, ["The Gitrog Monster", "The Necrobloom"], ["Grizzly Bears"], ["Forest"],
                   ["Grizzly Bears"] * 3 + ["Island"])
    g._mill(1)
    assert g.hand == ["Grizzly Bears"] * 2 and g.graveyard == ["Forest", "Island"] and len(g.library) == 2
