import json
from pathlib import Path

from edhpower.decklist import parse_decklist
from edhpower.facts import DeckFacts, build_facts, load_facts, save_facts
from edhpower.scryfall import CardData, Resolution
from edhpower.spellbook import ComboData
from edhpower.tags import TagCache, TagSet

from .conftest import full_tag_cache, make_card


def _resolution(*objs, unresolved=()):
    cards = {o["name"]: CardData.from_scryfall(o) for o in objs}
    return Resolution(cards=cards, unresolved=list(unresolved), network_requests=0, cache_updated_at="2026-09-10T00:00:00Z",
                       fetched_unknown=len(objs))


def _combos() -> ComboData:
    return ComboData(identity="C", included=[], almost_included_count=0, card_flags={}, combo_flags={},
                     spellbook_bracket_tag="C", fetched_at="2026-09-10T01:00:00Z", api_version="6.4.0")


def test_build_facts_basic():
    parsed = parse_decklist("1 Zhulodok, Void Gorger\n\n2 Wastes\n1 Ancient Tomb\n")
    res = _resolution(
        make_card("Zhulodok, Void Gorger", type_line="Legendary Creature — Eldrazi", cmc=7.0, color_identity=[]),
        make_card("Wastes", type_line="Basic Land", cmc=0.0),
        make_card("Ancient Tomb", type_line="Land", cmc=0.0, game_changer=True),
    )
    facts = build_facts(parsed, res, _combos(), None, "deck.txt")
    assert facts.commanders == ["Zhulodok, Void Gorger"]
    assert facts.total_cards == 4
    assert facts.curve.land_count == 3 and facts.curve.nonland_count == 1
    assert facts.game_changers == ["Ancient Tomb"]
    assert facts.identity_violations == [] and facts.commander_identity == []
    assert facts.fetched["scryfall_cards_oldest"] is None and facts.fetched["scryfall_cards_unknown"] == 3
    assert facts.fetched["spellbook"] == "2026-09-10T01:00:00Z" and facts.fetched["spellbook_api_version"] == "6.4.0"
    assert facts.tags_status == "tags not requested" and facts.profiles["Ancient Tomb"].land_mana == 2
    assert facts.special_hits == ["Ancient Tomb (land, mana 2)"] and facts.untagged == []
    assert facts.partition["lands"] == ["Ancient Tomb", "Wastes"] and facts.partition_counts["lands"] == 3
    assert facts.combos is not None and facts.combos_unavailable_reason is None


def test_entries_use_canonical_name_and_keep_as_written():
    parsed = parse_decklist("1 Wandering Archaic // Explore the Vastlands\n")
    dfc = make_card("Wandering Archaic // Explore the Vastlands", layout="modal_dfc")
    dfc["card_faces"] = [{"name": "Wandering Archaic", "mana_cost": "{5}", "type_line": "Creature", "oracle_text": ""},
                         {"name": "Explore the Vastlands", "mana_cost": "{3}", "type_line": "Sorcery", "oracle_text": ""}]
    del dfc["oracle_text"]
    res = Resolution({"Wandering Archaic": CardData.from_scryfall(dfc)}, [], 0, None)
    facts = build_facts(parsed, res, None, "offline", "d.txt")
    e = facts.entries[0]
    assert e.name == "Wandering Archaic // Explore the Vastlands" and e.as_written == "1 Wandering Archaic // Explore the Vastlands"
    assert facts.combos is None and facts.combos_unavailable_reason == "offline"
    assert facts.fetched["spellbook"] is None


def test_unresolved_are_carried_not_dropped():
    parsed = parse_decklist("1 Sol Ring\n1 Fake Card\n")
    res = _resolution(make_card("Sol Ring"), unresolved=["Fake Card"])
    facts = build_facts(parsed, res, None, None, "d.txt")
    assert facts.unresolved == ["Fake Card"] and facts.total_cards == 1


def test_identity_violation_detected():
    parsed = parse_decklist("1 Zhulodok, Void Gorger\n\n1 Kozilek's Unsealing\n")
    res = _resolution(make_card("Zhulodok, Void Gorger", color_identity=[]), make_card("Kozilek's Unsealing", color_identity=["U"]))
    facts = build_facts(parsed, res, None, None, "d.txt")
    assert facts.identity_violations == ["Kozilek's Unsealing"]


def test_json_round_trip(tmp_path: Path):
    parsed = parse_decklist("1 Zhulodok, Void Gorger\n\n2 Wastes\n")
    res = _resolution(make_card("Zhulodok, Void Gorger"), make_card("Wastes", type_line="Basic Land", cmc=0.0))
    facts = build_facts(parsed, res, _combos(), None, "d.txt")
    p = tmp_path / "f.json"
    save_facts(facts, p)
    loaded = load_facts(p)
    assert loaded == facts
    assert json.loads(p.read_text())["schema_version"] == 2


def test_build_facts_with_tags_partitions_and_flags_untagged():
    parsed = parse_decklist("1 Zhulodok, Void Gorger\n\n1 Sol Ring\n1 Demonic Tutor\n1 Brand New Card\n1 Wastes\n")
    res = _resolution(
        make_card("Zhulodok, Void Gorger", type_line="Legendary Creature — Eldrazi", cmc=6.0),
        make_card("Sol Ring", cmc=1.0, oracle_text="{T}: Add {C}{C}."),
        make_card("Demonic Tutor", cmc=2.0, type_line="Sorcery", color_identity=["B"]),
        make_card("Brand New Card", cmc=3.0, type_line="Creature — Eldrazi"),
        make_card("Wastes", type_line="Basic Land", cmc=0.0, oracle_text="({T}: Add {C}.)"),
    )
    cache = full_tag_cache(**{"mana-rock": ["Sol Ring"], "ramp": ["Sol Ring"], "tutor": ["Demonic Tutor"]})
    facts = build_facts(parsed, res, None, "offline", "d.txt", tag_cache=cache)
    assert facts.tags_status == "ok"
    assert facts.partition["fast_mana"] == ["Sol Ring"] and facts.partition["tutors"] == ["Demonic Tutor"]
    assert facts.untagged == ["Brand New Card", "Zhulodok, Void Gorger"]
    assert facts.fetched["tags_oldest"] == "2026-09-05T00:00:00Z"
    assert facts.profiles["Sol Ring"].tags == ("mana-rock", "ramp")


def test_incomplete_tag_cache_is_reported_not_used():
    parsed = parse_decklist("1 Sol Ring\n")
    res = _resolution(make_card("Sol Ring"))
    cache = TagCache({"ramp": TagSet("ramp", frozenset({"Sol Ring"}), "x", 1, "q")})
    facts = build_facts(parsed, res, None, None, "d.txt", tag_cache=cache, tags_unavailable_reason="tag cache incomplete (20 slugs missing)")
    assert facts.tags_status == "tag cache incomplete (20 slugs missing)"
    assert facts.profiles["Sol Ring"].tags == () and facts.untagged == []


def test_load_facts_rejects_other_schema_versions(tmp_path: Path):
    parsed = parse_decklist("1 Sol Ring\n")
    facts = build_facts(parsed, _resolution(make_card("Sol Ring")), None, None, "d.txt")
    p = tmp_path / "f.json"
    save_facts(facts, p)
    d = json.loads(p.read_text())
    assert d["schema_version"] == 2
    d["schema_version"] = 1
    p.write_text(json.dumps(d))
    import pytest
    with pytest.raises(ValueError, match="schema 1"):
        load_facts(p)
