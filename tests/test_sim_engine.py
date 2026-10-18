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
