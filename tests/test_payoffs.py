"""Payoff detection: real oracle text (Scryfall, 2026-10-18), one positive and one negative per category."""

from __future__ import annotations

from edhpower.config import PAYOFF_CATEGORIES
from edhpower.decklist import parse_decklist
from edhpower.facts import build_facts
from edhpower.payoffs import TAG_CHECKS, DeckPayoffs, categories_for, detect
from edhpower.scryfall import CardData, Resolution

from .conftest import full_tag_cache, make_card

ALL = frozenset(TAG_CHECKS)   # every tag check applied


def _card(name, text, cost="{2}", type_line="Artifact", **over):
    return CardData.from_scryfall(make_card(name, oracle_text=text, mana_cost=cost, type_line=type_line, **over))


BALLISTA = _card("Walking Ballista", "This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nRemove a +1/+1 counter from this creature: It deals 1 damage to any target.", cost="{X}{X}", type_line="Artifact Creature — Construct")
EXSANGUINATE = _card("Exsanguinate", "Each opponent loses X life. You gain life equal to the life lost this way.", cost="{X}{B}{B}", type_line="Sorcery")
HAILFIRE = _card("Torment of Hailfire", "Repeat the following process X times. Each opponent loses 3 life unless that player sacrifices a nonland permanent of their choice or discards a card.", cost="{X}{B}{B}", type_line="Sorcery")
PASSAGE = _card("Rogue's Passage", "{T}: Add {C}.\n{4}, {T}: Target creature can't be blocked this turn.", cost="", type_line="Land")
WOLF_RUN = _card("Kessig Wolf Run", "{T}: Add {C}.\n{X}{R}{G}, {T}: Target creature gets +X/+0 and gains trample until end of turn.", cost="", type_line="Land")
BLOOD_ARTIST = _card("Blood Artist", "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.", cost="{1}{B}", type_line="Creature — Vampire")
ZULAPORT = _card("Zulaport Cutthroat", "Whenever this creature or another creature you control dies, each opponent loses 1 life and you gain 1 life.", cost="{1}{B}", type_line="Creature — Human Rogue Ally")
TREMORS = _card("Impact Tremors", "Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.", cost="{1}{R}", type_line="Enchantment")
PURPHOROS = _card("Purphoros, God of the Forge", "Indestructible\nAs long as your devotion to red is less than five, Purphoros isn't a creature.\nWhenever another creature you control enters, Purphoros deals 2 damage to each opponent.\n{2}{R}: Creatures you control get +1/+0 until end of turn.", cost="{3}{R}", type_line="Legendary Enchantment Creature — God")
HOOF = _card("Craterhoof Behemoth", "Haste\nWhen this creature enters, creatures you control gain trample and get +X/+X until end of turn, where X is the number of creatures you control.", cost="{5}{G}{G}{G}", type_line="Creature — Beast")
BATS = _card("Mirkwood Bats", "Flying\nWhenever you create or sacrifice a token, each opponent loses 1 life.", cost="{3}{B}", type_line="Creature — Bat")
ASCENDANCY = _card("Simic Ascendancy", "{1}{G}{U}: Put a +1/+1 counter on target creature you control.\nWhenever one or more +1/+1 counters are put on a creature you control, put that many growth counters on this enchantment.\nAt the beginning of your upkeep, if this enchantment has twenty or more growth counters on it, you win the game.", cost="{G}{U}", type_line="Enchantment")
PINNACLE = _card("Helix Pinnacle", "Shroud (This enchantment can't be the target of spells or abilities.)\n{X}: Put X tower counters on this enchantment.\nAt the beginning of your upkeep, if there are 100 or more tower counters on this enchantment, you win the game.", cost="{G}", type_line="Enchantment")
GUTTERSNIPE = _card("Guttersnipe", "Whenever you cast an instant or sorcery spell, this creature deals 2 damage to each opponent.", cost="{2}{R}", type_line="Creature — Goblin Shaman")
ORACLE = _card("Thassa's Oracle", "When this creature enters, look at the top X cards of your library, where X is your devotion to blue. Put up to one of them on top of your library and the rest on the bottom of your library in a random order. If X is greater than or equal to the number of cards in your library, you win the game. (Each {U} in the mana costs of permanents you control counts toward your devotion to blue.)", cost="{U}{U}", type_line="Creature — Merfolk Wizard")
LAB_MAN = _card("Laboratory Maniac", "If you would draw a card while your library has no cards in it, you win the game instead.", cost="{2}{U}", type_line="Creature — Human Wizard")
JACE = _card("Jace, Wielder of Mysteries", "If you would draw a card while your library has no cards in it, you win the game instead.\n+1: Target player mills two cards. Draw a card.\n−8: Draw seven cards. Then if your library has no cards in it, you win the game.", cost="{1}{U}{U}{U}", type_line="Legendary Planeswalker — Jace")
VITO = _card("Vito, Thorn of the Dusk Rose", "Whenever you gain life, target opponent loses that much life.\n{3}{B}{B}: Creatures you control gain lifelink until end of turn.", cost="{2}{B}", type_line="Legendary Creature — Vampire Cleric")
HAGRA = _card("Retreat to Hagra", "Landfall — Whenever a land you control enters, choose one —\n• Target creature gets +1/+0 and gains deathtouch until end of turn.\n• Each opponent loses 1 life and you gain 1 life.", cost="{2}{B}", type_line="Enchantment")
OB_NIX = _card("Ob Nixilis, the Fallen", "Landfall — Whenever a land you control enters, you may have target player lose 3 life. If you do, put three +1/+1 counters on Ob Nixilis.", cost="{3}{B}{B}", type_line="Legendary Creature — Demon")
FIELD = _card("Field of the Dead", "This land enters tapped.\n{T}: Add {C}.\nWhenever this land or another land you control enters, if you control seven or more lands with different names, create a 2/2 black Zombie creature token.", cost="", type_line="Land")
SCUTE = _card("Scute Swarm", "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, create a token that's a copy of this creature instead.", cost="{2}{G}", type_line="Creature — Insect")
SOL_RING = _card("Sol Ring", "{T}: Add {C}{C}.", cost="{1}")


def test_mana_sink_x_spells_need_no_tag():
    assert categories_for(EXSANGUINATE, (), ALL) == {"mana_sink"}
    assert categories_for(HAILFIRE, (), ALL) == {"mana_sink"}


def test_mana_sink_activation_rule_requires_the_tag_when_checked():
    assert categories_for(BALLISTA, ("mana-sink",), ALL) == {"mana_sink"}
    assert categories_for(BALLISTA, (), ALL) == frozenset()
    assert categories_for(BALLISTA, (), frozenset()) == {"mana_sink"}   # tag check not applied → pattern decides


def test_mana_sink_negatives_even_with_the_tag():
    assert categories_for(PASSAGE, ("mana-sink",), ALL) == frozenset()
    assert categories_for(WOLF_RUN, ("mana-sink",), ALL) == frozenset()
    assert categories_for(SOL_RING, (), ALL) == frozenset()


def test_drain_death_triggers():
    assert categories_for(BLOOD_ARTIST, (), ALL) == {"drain"}
    assert categories_for(ZULAPORT, (), ALL) == {"drain"}
    assert "drain" not in categories_for(TREMORS, (), ALL)


def test_etb_damage():
    assert categories_for(TREMORS, (), ALL) == {"etb_damage"}
    assert categories_for(PURPHOROS, (), ALL) == {"etb_damage"}
    assert "etb_damage" not in categories_for(BLOOD_ARTIST, (), ALL)


def test_go_wide_accepts_both_word_orders():
    assert categories_for(HOOF, (), ALL) == {"go_wide"}
    overrun = _card("Overrun", "Creatures you control get +3/+3 and gain trample until end of turn.", cost="{2}{G}{G}{G}", type_line="Sorcery")
    assert categories_for(overrun, (), ALL) == {"go_wide"}
    assert "go_wide" not in categories_for(WOLF_RUN, ("mana-sink",), ALL)   # single target creature


def test_token_drain():
    assert categories_for(BATS, (), ALL) == {"token_drain"}
    assert "token_drain" not in categories_for(ZULAPORT, (), ALL)


def test_counter_win():
    assert categories_for(ASCENDANCY, ("alternate-win-condition",), ALL) == {"counter_win"}
    assert "counter_win" in categories_for(PINNACLE, ("alternate-win-condition", "mana-sink"), ALL)
    assert "counter_win" not in categories_for(BALLISTA, ("mana-sink",), ALL)


def test_cast_damage():
    assert categories_for(GUTTERSNIPE, (), ALL) == {"cast_damage"}
    assert "cast_damage" not in categories_for(PURPHOROS, (), ALL)


def test_empty_library_win_requires_the_tag_when_checked():
    for c in (ORACLE, LAB_MAN, JACE):
        assert categories_for(c, ("alternate-win-condition",), ALL) == {"empty_library_win"}, c.name
        assert categories_for(c, (), ALL) == frozenset(), c.name
        assert categories_for(c, (), frozenset()) == {"empty_library_win"}, c.name


def test_life_drain_has_no_tag_check():
    assert categories_for(VITO, (), ALL) == {"life_drain"}
    assert "life_drain" not in categories_for(EXSANGUINATE, ("lifedrain",), ALL)


def test_landfall_payoff_and_tokens():
    assert categories_for(HAGRA, (), ALL) == {"landfall_payoff"}
    assert categories_for(OB_NIX, (), ALL) == {"landfall_payoff"}
    assert categories_for(FIELD, (), ALL) == {"landfall_tokens"}
    assert categories_for(SCUTE, (), ALL) == {"landfall_tokens"}
    assert "landfall_payoff" not in categories_for(SCUTE, (), ALL)


def test_back_face_text_is_scanned():
    dfc = make_card("Front // Back", layout="modal_dfc", oracle_text="", mana_cost="",
                    card_faces=[{"name": "Front", "mana_cost": "{1}{B}", "type_line": "Sorcery", "oracle_text": "Draw a card."},
                                {"name": "Back", "mana_cost": "{3}{B}", "type_line": "Enchantment",
                                 "oracle_text": "Whenever another creature you control dies, each opponent loses 1 life."}])
    assert categories_for(CardData.from_scryfall(dfc), (), ALL) == {"drain"}


def _facts(cards, tags=None):
    text = "1 Grizzly Bears\n\n" + "".join(f"1 {c.name}\n" for c in cards)
    bears = CardData.from_scryfall(make_card("Grizzly Bears", type_line="Legendary Creature — Bear", mana_cost="{1}{G}", cmc=2.0))
    res = Resolution({c.name: c for c in [bears, *cards]}, [], 0, None)
    cache = full_tag_cache(**tags) if tags is not None else None
    return build_facts(parse_decklist(text), res, None, "offline", "t.txt", tag_cache=cache)


def test_detect_groups_cards_and_applies_both_tag_checks():
    p = detect(_facts([BALLISTA, EXSANGUINATE, ORACLE, TREMORS, SOL_RING], tags={"mana-sink": ["Walking Ballista"], "alternate-win-condition": ["Thassa's Oracle"]}))
    assert isinstance(p, DeckPayoffs)
    assert set(p.by_category) == set(PAYOFF_CATEGORIES)
    assert p.by_category["mana_sink"] == ["Exsanguinate", "Walking Ballista"]
    assert p.by_category["empty_library_win"] == ["Thassa's Oracle"]
    assert p.by_category["etb_damage"] == ["Impact Tremors"] and p.by_category["drain"] == []
    assert p.tag_checked == ("empty_library_win", "mana_sink") and p.notes == []
    assert p.cards_for(["etb_damage", "mana_sink"]) == ["Exsanguinate", "Impact Tremors", "Walking Ballista"]
    assert p.to_dict() == {"by_category": p.by_category, "tag_checked": ["empty_library_win", "mana_sink"], "notes": []}


def test_detect_without_tags_is_pattern_only_and_says_so():
    p = detect(_facts([BALLISTA, ORACLE]))
    assert p.by_category["mana_sink"] == ["Walking Ballista"] and p.by_category["empty_library_win"] == ["Thassa's Oracle"]
    assert p.tag_checked == ()
    assert len(p.notes) == 1 and "tags not requested" in p.notes[0] and "mana_sink" in p.notes[0] and "empty_library_win" in p.notes[0]


def test_detect_with_facts_that_predate_a_slug_degrades_loudly():
    facts = _facts([BALLISTA, ORACLE], tags={"mana-sink": ["Walking Ballista"]})
    facts.fetched["tag_table"] = "ramp,tutor,mana-sink"   # alternate-win-condition unknown when these facts were built
    p = detect(facts)
    assert p.tag_checked == ("mana_sink",)
    assert p.by_category["empty_library_win"] == ["Thassa's Oracle"]
    assert p.notes == ["payoff tag check skipped for empty_library_win: facts predate the alternate-win-condition tag"]


def test_commander_is_scanned_too():
    oracle_cmd = CardData.from_scryfall(make_card("Thassa's Oracle", oracle_text=ORACLE.oracle_text, mana_cost="{U}{U}", type_line="Legendary Creature — Merfolk Wizard"))
    res = Resolution({"Thassa's Oracle": oracle_cmd, "Sol Ring": SOL_RING}, [], 0, None)
    facts = build_facts(parse_decklist("1 Thassa's Oracle\n\n1 Sol Ring\n"), res, None, "offline", "t.txt", tag_cache=full_tag_cache(**{"alternate-win-condition": ["Thassa's Oracle"]}))
    assert detect(facts).by_category["empty_library_win"] == ["Thassa's Oracle"]
