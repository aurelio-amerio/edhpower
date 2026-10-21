import pytest

from edhpower.extract import extract
from edhpower.profile import CardProfile, build_profile, is_fast_mana, load_special_behaviours, special_behaviours_from
from edhpower.scryfall import CardData
from edhpower.sim.effects import Effect

from .conftest import make_card


def _card(name, **over) -> CardData:
    return CardData.from_scryfall(make_card(name, **over))


def test_special_table_loads_and_is_small():
    table = load_special_behaviours()
    assert set(table) >= {"Ancient Tomb", "Eldrazi Temple", "Eye of Ugin", "Gaea's Cradle", "Urza's Tower", "Forsaken Monument",
                          "Basalt Monolith", "Mana Vault", "Unwinding Clock", "Seedborn Muse", "Manifold Key"}
    assert len(table) <= 25
    tomb = table["Ancient Tomb"]
    assert (tomb.kind, tomb.mana) == ("land", 2)
    eye = table["Eye of Ugin"]
    assert eye.mana == 0 and eye.params["reduces"] == 2 and eye.params["tutor_cost"] == 7
    assert table["Mana Vault"].params["untap_cost"] == 4
    assert all(b.kind in {None, "land", "rock", "doubler", "untap"} for b in table.values())


def test_profile_of_sol_ring_is_fast_mana_rock():
    card = _card("Sol Ring", cmc=1.0, mana_cost="{1}", oracle_text="{T}: Add {C}{C}.", produced_mana=["C"])
    p = build_profile(card, ("mana-rock", "ramp"), None, tags_known=True)
    assert p.tags == ("mana-rock", "ramp") and not p.is_land and p.mana_per_activation == 2 and p.repeatable_mana
    assert p.is_fast_mana and p.land_mana == 0 and p.special is None and not p.untagged


def test_profile_of_ancient_tomb_uses_table_for_land_class():
    table = load_special_behaviours()
    card = _card("Ancient Tomb", cmc=0.0, mana_cost="", type_line="Land", oracle_text="{T}: Add {C}{C}. Ancient Tomb deals 2 damage to you.", produced_mana=["C"])
    p = build_profile(card, ("ramp",), table["Ancient Tomb"], tags_known=True)
    assert p.is_land and p.land_mana == 2 and p.special == "land" and not p.is_fast_mana


def test_plain_producing_land_is_class_1_and_utility_land_is_class_0():
    forest = build_profile(_card("Forest", cmc=0.0, type_line="Basic Land — Forest", oracle_text="({T}: Add {G}.)", produced_mana=["G"]), (), None, True)
    assert forest.land_mana == 1 and forest.is_basic_land and not forest.untagged
    cave = build_profile(_card("Urza's Cave", cmc=0.0, type_line="Land", oracle_text="{T}: Add {C}.\n{3}, {T}, Sacrifice: search...", produced_mana=["C"]), (), None, True)
    assert cave.land_mana == 1
    table = load_special_behaviours()
    eye = build_profile(_card("Eye of Ugin", cmc=0.0, type_line="Legendary Land", oracle_text="Colorless Eldrazi spells you cast cost {2} less to cast.\n{7}, {T}: Search your library for a colorless creature card, reveal it, put it into your hand, then shuffle.", produced_mana=[]), ("tutor",), table["Eye of Ugin"], True)
    assert eye.land_mana == 0 and eye.cost_reduction == 2 and eye.cost_reduction_scope == "colorless eldrazi spells you cast" and eye.special == "land"


def test_fast_mana_rule_examples():
    table = load_special_behaviours()
    def fast(name, **over):
        card = _card(name, **over)
        return is_fast_mana(card, extract(card.oracle_text, card.type_line), table.get(name))
    assert fast("Mana Crypt", cmc=0.0, oracle_text="{T}: Add {C}{C}{C}.")
    assert fast("Mana Vault", cmc=1.0, oracle_text="{T}: Add {C}{C}{C}.\nMana Vault doesn't untap during your untap step.")
    assert fast("Dark Ritual", cmc=1.0, type_line="Instant", oracle_text="Add {B}{B}{B}.")
    assert fast("Jeweled Lotus", cmc=0.0, oracle_text="{T}, Sacrifice Jeweled Lotus: Add three mana of any one color.")
    assert fast("Chrome Mox", cmc=0.0, oracle_text="{T}: Add one mana of any of the exiled card's colors.")
    assert not fast("Arcane Signet", cmc=2.0, oracle_text="{T}: Add one mana of any color in your commander's color identity.")
    assert not fast("Basalt Monolith", cmc=3.0, oracle_text="{T}: Add {C}{C}{C}.")
    assert not fast("Llanowar Elves", cmc=1.0, type_line="Creature — Elf Druid", oracle_text="{T}: Add {G}.")
    assert not fast("Seething Song", cmc=3.0, type_line="Instant", oracle_text="Add {R}{R}{R}{R}{R}.")
    assert not fast("Ancient Tomb", cmc=0.0, type_line="Land", oracle_text="{T}: Add {C}{C}.")
    assert not fast("Tapped Rock", cmc=2.0, oracle_text="Tapped Rock enters tapped.\n{T}: Add {C}{C}.")


def test_untagged_is_only_meaningful_when_tags_are_known():
    card = _card("Brand New Card", cmc=3.0, type_line="Creature — Eldrazi", oracle_text="Flying")
    assert build_profile(card, (), None, tags_known=True).untagged
    assert not build_profile(card, (), None, tags_known=False).untagged
    assert build_profile(_card("Wastes", cmc=0.0, type_line="Basic Land"), (), None, True).untagged is False


def test_profile_round_trip():
    p = build_profile(_card("Sol Ring", cmc=1.0, oracle_text="{T}: Add {C}{C}."), ("mana-rock",), None, True)
    assert CardProfile.from_dict(p.to_dict()) == p
    assert p.is_creature is False and p.is_eldrazi is False


from edhpower.profile import PARTITION_KEYS, partition


def _prof(name, tags=(), **over) -> CardProfile:
    base = dict(name=name, tags=tuple(tags), is_land=False, is_basic_land=False, is_creature=False, is_eldrazi=False, cmc=2.0,
                mana_per_activation=0, mana_colors=(), repeatable_mana=False, board_dependent_mana=False, land_mana=0,
                is_fast_mana=False, cost_reduction=0, cost_reduction_scope="", draw_count=0, enters_tapped=False, special=None, untagged=False)
    base.update(over)
    return CardProfile(**base)


def test_partition_is_exclusive_within_the_mana_family():
    profs = [
        (_prof("Sol Ring", ("mana-rock", "ramp"), is_fast_mana=True), 1),
        (_prof("Arcane Signet", ("mana-rock", "ramp")), 1),
        (_prof("Llanowar Elves", ("mana-dork", "ramp"), is_creature=True), 1),
        (_prof("Rampant Growth", ("land-ramp", "ramp")), 1),
        (_prof("Dark Ritual", ("ritual", "ramp"), is_fast_mana=True), 1),
        (_prof("Seething Song", ("ritual", "ramp")), 1),
        (_prof("Smothering Tithe", ("ramp",)), 1),
        (_prof("Forest", ("ramp",), is_land=True, land_mana=1), 3),
    ]
    names, counts = partition(profs)
    assert names["fast_mana"] == ["Dark Ritual", "Sol Ring"] and names["mana_rocks"] == ["Arcane Signet"]
    assert names["mana_dorks"] == ["Llanowar Elves"] and names["land_ramp"] == ["Rampant Growth"]
    assert names["rituals"] == ["Seething Song"] and names["other_ramp"] == ["Smothering Tithe"]
    assert names["lands"] == ["Forest"] and counts["lands"] == 3 and counts["fast_mana"] == 2
    assert names["creatures"] == ["Llanowar Elves"]
    assert set(names) == set(PARTITION_KEYS) and set(counts) == set(PARTITION_KEYS)


def test_partition_interaction_and_card_advantage_families():
    profs = [
        (_prof("Counterspell", ("counterspell",)), 1),
        (_prof("Swords to Plowshares", ("removal",)), 1),
        (_prof("Farewell", ("board-wipe", "removal")), 1),
        (_prof("Brainstorm", ("cantrip", "card-advantage")), 1),
        (_prof("Rhystic Study", ("card-advantage",)), 1),
        (_prof("Herald of Kozilek", (), cost_reduction=1), 1),
        (_prof("Thalia", ("hatebear", "tax")), 1),
        (_prof("New Card", (), untagged=True), 1),
    ]
    names, _ = partition(profs)
    assert names["removal"] == ["Swords to Plowshares"] and names["board_wipes"] == ["Farewell"] and names["counterspells"] == ["Counterspell"]
    assert names["cantrips"] == ["Brainstorm"] and names["card_advantage"] == ["Rhystic Study"]
    assert names["cost_reducers"] == ["Herald of Kozilek"] and names["stax"] == ["Thalia"] and names["untagged"] == ["New Card"]


def test_city_of_traitors_declares_its_sacrifice():
    table = load_special_behaviours()
    entry = table["City of Traitors"]
    assert entry.kind == "land" and entry.mana == 2
    assert entry.params == {"sacrifice_on_land_drop": True}


def test_effects_only_entry_has_no_kind():
    raw = {"version": 2, "cards": {"Some Landfall Card": {
        "effects": [{"on": "landfall", "do": "token", "power": 1, "toughness": 1, "type": "Goat"}], "note": "table override"}}}
    entry = special_behaviours_from(raw)["Some Landfall Card"]
    assert entry.kind is None and entry.mana == 0 and entry.params == {} and entry.note == "table override"
    assert entry.effects == (Effect("landfall", "token", 1, 1, 1, "Goat"),)


def test_entry_without_kind_or_effects_is_rejected():
    with pytest.raises(ValueError, match="Nothing Card"):
        special_behaviours_from({"version": 2, "cards": {"Nothing Card": {"mana": 1, "note": "x"}}})


def test_colossus_table_entry():
    entry = load_special_behaviours()["Cultivator Colossus"]
    assert entry.effects == (Effect("etb", "chain_lands_from_hand"),) and entry.kind is None
