from dataclasses import replace

import pytest

from edhpower.config import load_config
from edhpower.decklist import parse_decklist
from edhpower.facts import build_facts
from edhpower.scorers.components import ComponentScore, infer_archetype, score_components
from edhpower.scryfall import CardData, Resolution
from edhpower.spellbook import ComboData, ComboFlags, ComboLine, ComboPiece

from .conftest import full_tag_cache, make_card

PROF = load_config().components


def _facts(lines: list[tuple[str, int, dict, tuple[str, ...]]], combos=None, reason=None, tagged=True):
    """lines: (name, count, card overrides, tags). First line is the commander."""
    text = f"1 {lines[0][0]}\n\n" + "\n".join(f"{n} {name}" for name, n, _, _ in lines[1:]) + "\n"
    cards = {name: CardData.from_scryfall(make_card(name, **over)) for name, _, over, _ in lines}
    members: dict[str, list[str]] = {}
    for name, _, _, tags in lines:
        for t in tags:
            members.setdefault(t, []).append(name)
    cache = full_tag_cache(**members) if tagged else None
    return build_facts(parse_decklist(text), Resolution(cards, [], 0, None), combos, reason, "t.txt", tag_cache=cache)


def _two_card_combos() -> ComboData:
    line = ComboLine("c1", (ComboPiece("Basalt Monolith", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), ("Infinite colorless mana",), "", 0, "R", 1, "", "")
    other = ComboLine("c2", (ComboPiece("A", ("B",), False), ComboPiece("B", ("B",), False), ComboPiece("C", ("H",), False)), (), ("Win the game",), "", 0, "S", 1, "", "")
    flags = {"c1": ComboFlags("c1", True, False, 5, False, False, False, False, True), "c2": ComboFlags("c2", False, False, 8, False, False, False, False, True)}
    return ComboData("C", [line, other], 0, {}, flags, "R", "2026-09-10T00:00:00Z", api_version="6.4.0")


DECK = [
    ("Commander", 1, {"cmc": 4.0, "type_line": "Legendary Creature"}, ()),
    ("Sol Ring", 1, {"cmc": 1.0, "oracle_text": "{T}: Add {C}{C}."}, ("mana-rock", "ramp")),
    ("Mana Crypt", 1, {"cmc": 0.0, "oracle_text": "{T}: Add {C}{C}{C}."}, ("mana-rock", "ramp")),
    ("Arcane Signet", 1, {"cmc": 2.0, "oracle_text": "{T}: Add one mana of any color."}, ("mana-rock", "ramp")),
    ("Demonic Tutor", 4, {"cmc": 2.0, "type_line": "Sorcery"}, ("tutor",)),
    ("Counterspell", 3, {"cmc": 2.0, "type_line": "Instant"}, ("counterspell",)),
    ("Swords to Plowshares", 3, {"cmc": 1.0, "type_line": "Instant"}, ("removal",)),
    ("Rhystic Study", 3, {"cmc": 3.0, "type_line": "Enchantment"}, ("card-advantage",)),
    ("Forest", 10, {"cmc": 0.0, "type_line": "Basic Land — Forest", "oracle_text": "({T}: Add {G}.)"}, ()),
]


def test_unevaluated_without_tags():
    s = score_components(_facts(DECK, tagged=False), PROF)
    assert s.status == "unevaluated" and s.total is None and s.components == [] and s.archetype is None
    assert any("tags" in n for n in s.notes)


def test_components_by_hand_with_combos_unavailable():
    s = score_components(_facts(DECK, reason="Spellbook unreachable"), PROF)
    by = {c.name: c for c in s.components}
    assert s.status == "partial" and by["combos"].score is None and "unreachable" in by["combos"].detail
    assert by["fast_mana"].count == 2 and by["fast_mana"].score == pytest.approx(10 * 2 / 6, abs=1e-3) and by["fast_mana"].contributors == ["Mana Crypt", "Sol Ring"]
    assert by["tutors"].count == 4 and by["tutors"].score == pytest.approx(5.0)
    assert by["interaction"].count == 6 and by["interaction"].score == pytest.approx(5.0)
    assert by["card_advantage"].count == 3 and by["card_advantage"].score == pytest.approx(2.5)
    # curve: avg MV of 17 nonland cards = (4+1+0+2+8+6+3+9)/17 = 33/17 ≈ 1.941 → curve_part 10; ramp_total 3 → ramp_part 2.5
    assert by["curve"].score == pytest.approx(0.6 * 10 + 0.4 * 2.5, abs=1e-3)
    evaluated = [c for c in s.components if c.score is not None]
    expected = sum(c.weight * c.score for c in evaluated) / sum(c.weight for c in evaluated)
    assert s.total == pytest.approx(expected, abs=1e-3)
    assert s.archetype == "midrange"   # no combo lines (Spellbook unavailable), interaction 6 < 12, 1 creature, avg MV < 4


def test_combos_component_and_combo_archetype():
    s = score_components(_facts(DECK, combos=_two_card_combos()), PROF)
    by = {c.name: c for c in s.components}
    assert s.status == "ok" and by["combos"].count == pytest.approx(1.0 * 1 + 0.5 * 1) and by["combos"].score == pytest.approx(10 * 1.5 / 4)
    assert by["combos"].contributors == ["Basalt Monolith + Forsaken Monument", "A + B + C"]
    assert s.archetype == "combo" and "1 two-card" in s.archetype_reason
    assert s.total == pytest.approx(sum(c.weight * c.score for c in s.components), abs=1e-3)


def test_big_mana_and_control_archetypes():
    big = DECK[:1] + [("Cultivate", 12, {"cmc": 3.0, "type_line": "Sorcery"}, ("land-ramp", "ramp")),
                      ("Ulamog", 10, {"cmc": 10.0, "type_line": "Legendary Creature — Eldrazi"}, ())]
    s = score_components(_facts(big, reason="off"), PROF)
    assert s.archetype == "big-mana"
    control = DECK[:1] + [("Counterspell", 6, {"cmc": 2.0, "type_line": "Instant"}, ("counterspell",)),
                          ("Swords", 8, {"cmc": 1.0, "type_line": "Instant"}, ("removal",))]
    assert score_components(_facts(control, reason="off"), PROF).archetype == "control"


def test_missing_archetype_cutoff_raises_when_that_rule_is_reached():
    # avg MV >= 4, ramp >= 10, no combo/stax/control/creature match -> reaches the big-mana rule,
    # whose cutoff we've deleted from the profile's archetype dict.
    big = DECK[:1] + [("Cultivate", 12, {"cmc": 3.0, "type_line": "Sorcery"}, ("land-ramp", "ramp")),
                      ("Ulamog", 10, {"cmc": 10.0, "type_line": "Legendary Creature — Eldrazi"}, ())]
    facts = _facts(big, reason="off")
    prof = replace(PROF, archetype={k: v for k, v in PROF.archetype.items() if k != "big_mana_min_avg_mv"})
    with pytest.raises(KeyError, match="big_mana_min_avg_mv"):
        score_components(facts, prof)


def test_to_dict_is_json_shaped():
    d = score_components(_facts(DECK, combos=_two_card_combos()), PROF).to_dict()
    assert d["profile"] == "v1" and isinstance(d["components"], list) and d["components"][0]["contributors"] is not None
