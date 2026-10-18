from edhpower.bracket import evaluate_bracket, load_rules
from edhpower.decklist import parse_decklist
from edhpower.facts import build_facts
from edhpower.scryfall import CardData, Resolution
from edhpower.spellbook import CardFlags, ComboData, ComboFlags, ComboLine, ComboPiece

from .conftest import full_tag_cache, make_card


def _facts(cards: list[dict], combos: ComboData | None, reason=None):
    text = "\n".join(f"1 {c['name']}" for c in cards) + "\n"
    parsed = parse_decklist(text)
    res = Resolution({c["name"]: CardData.from_scryfall(c) for c in cards}, [], 0, None)
    return build_facts(parsed, res, combos, reason, "t.txt")


def _combos(card_flags=(), lines=(), combo_flags=()) -> ComboData:
    return ComboData(
        identity="C", included=list(lines), almost_included_count=0,
        card_flags={f.name: f for f in card_flags}, combo_flags={f.combo_id: f for f in combo_flags},
        spellbook_bracket_tag="", fetched_at="2026-09-10T00:00:00Z",
    )


def _line(cid, *names):
    return ComboLine(cid, tuple(ComboPiece(n, ("B",), False) for n in names), (), ("Infinite colorless mana",), "", 0, "R", 1, "", "")


def _cf(cid, two=False, speed=None, mld=False, et=False):
    return ComboFlags(cid, two, False, speed, mld, et, False, False, True)


def test_rules_load():
    r = load_rules()
    assert r["game_changers"]["bracket3_max"] == 3 and r["source_url"].startswith("https://")


def test_clean_deck_is_bracket_2_floor():
    v = evaluate_bracket(_facts([make_card("Sol Ring")], _combos()))
    assert v.minimum_bracket == 2
    assert {c.name: c.status for c in v.criteria}["game_changers"] == "ok"
    assert {c.name: c.status for c in v.criteria}["tutors"] == "unevaluated"
    assert any("self-declared" in n for n in v.notes)


def test_one_to_three_game_changers_floor_3_and_lists_them():
    cards = [make_card("Ancient Tomb", game_changer=True), make_card("Mana Vault", game_changer=True), make_card("Sol Ring")]
    v = evaluate_bracket(_facts(cards, _combos()))
    gc = next(c for c in v.criteria if c.name == "game_changers")
    assert v.minimum_bracket == 3 and gc.status == "triggered" and gc.floor == 3
    assert gc.triggers == ["Ancient Tomb", "Mana Vault"]


def test_four_game_changers_floor_4():
    cards = [make_card(f"GC{i}", game_changer=True) for i in range(4)]
    assert evaluate_bracket(_facts(cards, _combos())).minimum_bracket == 4


def test_scryfall_spellbook_gc_disagreement_is_noted():
    cards = [make_card("Farewell", game_changer=True)]
    combos = _combos(card_flags=[CardFlags("Farewell", False, False, False, False)])
    v = evaluate_bracket(_facts(cards, combos))
    assert any("Farewell" in n and "disagree" in n for n in v.notes)


def test_mass_land_denial_from_card_flag_floor_4():
    combos = _combos(card_flags=[CardFlags("Armageddon", False, True, False, False)])
    v = evaluate_bracket(_facts([make_card("Armageddon")], combos))
    mld = next(c for c in v.criteria if c.name == "mass_land_denial")
    assert v.minimum_bracket == 4 and mld.triggers == ["Armageddon"]


def test_looped_extra_turns_floor_4_and_plain_count_reported():
    combos = _combos(card_flags=[CardFlags("Time Warp", False, False, True, False)],
                     lines=[_line("c1", "Time Warp", "Archaeomancer")], combo_flags=[_cf("c1", et=True)])
    v = evaluate_bracket(_facts([make_card("Time Warp"), make_card("Archaeomancer")], combos))
    et = next(c for c in v.criteria if c.name == "extra_turns")
    assert et.status == "triggered" and et.floor == 4 and "1 extra-turn card" in et.detail


def test_two_card_combo_floor_3_with_speed_and_review_when_cheap():
    cards = [make_card("Basalt Monolith", cmc=3.0), make_card("Forsaken Monument", cmc=5.0),
             make_card("Thassa's Oracle", cmc=2.0), make_card("Demonic Consultation", cmc=1.0)]
    combos = _combos(lines=[_line("c1", "Basalt Monolith", "Forsaken Monument"), _line("c2", "Thassa's Oracle", "Demonic Consultation")],
                     combo_flags=[_cf("c1", two=True, speed=5), _cf("c2", two=True, speed=2)])
    v = evaluate_bracket(_facts(cards, combos))
    two = next(c for c in v.criteria if c.name == "two_card_combos")
    assert v.minimum_bracket == 3 and two.status == "triggered" and two.floor == 3
    assert two.triggers == ["Basalt Monolith + Forsaken Monument (speed 5)", "Thassa's Oracle + Demonic Consultation (speed 2)"]
    review = next(c for c in v.criteria if c.name == "two_card_combos_early_review")
    assert review.status == "review" and review.floor is None
    assert review.triggers == ["Thassa's Oracle + Demonic Consultation (total MV 3)"]


def test_no_combos_marks_dependent_criteria_unevaluated():
    v = evaluate_bracket(_facts([make_card("Sol Ring")], None, reason="Spellbook unreachable"))
    statuses = {c.name: c.status for c in v.criteria}
    assert statuses["mass_land_denial"] == "unevaluated"
    assert statuses["extra_turns"] == "unevaluated"
    assert statuses["two_card_combos"] == "unevaluated"
    assert v.minimum_bracket == 2 and any("Spellbook unreachable" in n for n in v.notes)


def test_to_dict_is_json_shaped():
    v = evaluate_bracket(_facts([make_card("Sol Ring")], _combos()))
    d = v.to_dict()
    assert d["minimum_bracket"] == 2 and isinstance(d["criteria"], list) and d["source_date"] == "2026-02-09"


def test_gc_cross_check_skips_names_not_in_entries():
    v = evaluate_bracket(_facts([make_card("Sol Ring")], _combos(card_flags=[CardFlags("Ghost Card", True, False, False, False)])))
    assert not any("disagree" in n for n in v.notes)


def _facts_with_tags(cards: list[dict], tags: dict[str, tuple[str, ...]], combos=None):
    text = "\n".join(f"1 {c['name']}" for c in cards) + "\n"
    members: dict[str, list[str]] = {}
    for name, ts in tags.items():
        for t in ts:
            members.setdefault(t, []).append(name)
    res = Resolution({c["name"]: CardData.from_scryfall(c) for c in cards}, [], 0, None)
    return build_facts(parse_decklist(text), res, combos, None, "t.txt", tag_cache=full_tag_cache(**members))


def test_tutors_unevaluated_without_tags():
    v = evaluate_bracket(_facts([make_card("Demonic Tutor")], _combos()))
    t = next(c for c in v.criteria if c.name == "tutors")
    assert t.status == "unevaluated" and "tags not requested" in t.detail
    assert t.floor is None and v.minimum_bracket == 2  # an unevaluated criterion must never floor the bracket


def test_tutors_ok_below_review_threshold_and_review_at_or_above():
    cards = [make_card(f"Tutor {i}", type_line="Sorcery") for i in range(4)] + [make_card("Sol Ring")]
    few = _facts_with_tags(cards[:3] + cards[4:], {f"Tutor {i}": ("tutor",) for i in range(3)}, _combos())
    t = next(c for c in evaluate_bracket(few).criteria if c.name == "tutors")
    assert t.status == "ok" and t.floor is None and t.triggers == ["Tutor 0", "Tutor 1", "Tutor 2"] and "3 tutor" in t.detail
    many = _facts_with_tags(cards, {f"Tutor {i}": ("tutor",) for i in range(4)}, _combos())
    v = evaluate_bracket(many)
    t = next(c for c in v.criteria if c.name == "tutors")
    assert t.status == "review" and t.floor is None and len(t.triggers) == 4 and v.minimum_bracket == 2


def _self_mill_line(cid, *names):
    return ComboLine(cid, tuple(ComboPiece(n, ("B",), False) for n in names), (), ("Infinite self-mill", "Near-infinite self-discard triggers"), "", 0, "S", 1, "", "")


def test_self_harm_two_card_combo_without_payoff_is_flagged_for_review_not_floored_lower():
    from edhpower.config import load_config
    from edhpower.payoffs import detect
    cards = [make_card("The Gitrog Monster", type_line="Legendary Creature — Frog Horror"), make_card("The Necrobloom", type_line="Legendary Creature — Plant Horror")]
    combos = _combos(lines=[_self_mill_line("g", "The Gitrog Monster", "The Necrobloom")], combo_flags=[_cf("g", two=True, speed=5)])
    facts = _facts(cards, combos)
    v = evaluate_bracket(facts, detect(facts), load_config().sim)
    names = {c.name: c for c in v.criteria}
    assert v.minimum_bracket == 3 and names["two_card_combos"].status == "triggered"
    r = names["two_card_combos_no_payoff"]
    assert r.status == "review" and r.floor is None and r.triggers == ["The Gitrog Monster + The Necrobloom (self_mill)"]
    assert "no empty-library win" in r.detail and "scrollvault would not floor" in r.detail


def test_self_harm_combo_with_a_payoff_in_the_deck_is_not_flagged():
    from edhpower.config import load_config
    from edhpower.payoffs import detect
    lab = make_card("Laboratory Maniac", type_line="Creature — Human Wizard", oracle_text="If you would draw a card while your library has no cards in it, you win the game instead.")
    cards = [make_card("The Gitrog Monster"), make_card("The Necrobloom"), lab]
    combos = _combos(lines=[_self_mill_line("g", "The Gitrog Monster", "The Necrobloom")], combo_flags=[_cf("g", two=True, speed=5)])
    facts = _facts(cards, combos)   # tags unavailable → pattern-only detection finds Lab Man
    v = evaluate_bracket(facts, detect(facts), load_config().sim)
    assert "two_card_combos_no_payoff" not in {c.name for c in v.criteria}


def test_mana_combo_without_sink_is_not_a_self_harm_review():
    from edhpower.config import load_config
    from edhpower.payoffs import detect
    cards = [make_card("Basalt Monolith"), make_card("Forsaken Monument")]
    combos = _combos(lines=[_line("m", "Basalt Monolith", "Forsaken Monument")], combo_flags=[_cf("m", two=True, speed=5)])
    facts = _facts(cards, combos)
    v = evaluate_bracket(facts, detect(facts), load_config().sim)
    assert "two_card_combos_no_payoff" not in {c.name for c in v.criteria}


def test_bracket_without_payoffs_argument_is_unchanged():
    cards = [make_card("The Gitrog Monster"), make_card("The Necrobloom")]
    combos = _combos(lines=[_self_mill_line("g", "The Gitrog Monster", "The Necrobloom")], combo_flags=[_cf("g", two=True, speed=5)])
    v = evaluate_bracket(_facts(cards, combos))
    assert "two_card_combos_no_payoff" not in {c.name for c in v.criteria} and v.minimum_bracket == 3
