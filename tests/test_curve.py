import pytest

from edhpower.config import load_config
from edhpower.decklist import front_face, parse_decklist
from edhpower.facts import build_facts
from edhpower.scorers.curve import BASIC_LAND_NAMES, CurveScore, interpolate, score_curve
from edhpower.scryfall import CardData, Resolution

from .conftest import make_card

PROF = load_config().curve


def _facts(cards: list[dict], text: str | None = None):
    text = text or ("1 " + cards[0]["name"] + "\n\n" + "\n".join(f"1 {c['name']}" for c in cards[1:]) + "\n")
    parsed = parse_decklist(text)
    res = Resolution({front_face(c["name"]): CardData.from_scryfall(c) for c in cards}, [], 0, None)  # keyed like the parser names them
    return build_facts(parsed, res, None, None, "t.txt")


def test_interpolate_matches_the_site_helper():
    assert interpolate(0, PROF.price_curve) == 0.0 and interpolate(-5, PROF.price_curve) == 0.0 and interpolate(None, PROF.price_curve) == 0.0
    assert interpolate(200, PROF.price_curve, 1.25) == pytest.approx(12.5)          # above the last breakpoint: (n-1)*step
    assert interpolate(1.0, PROF.price_curve, 1.25) == pytest.approx(1.75)          # segment 1: 1*1.25 + (1.0-0.5)/(1.5-0.5), fraction unscaled
    assert interpolate(100, PROF.price_curve, 1.25) == 0.0                           # site quirk: exactly the last breakpoint → 0
    assert interpolate(27000 - 1000, PROF.pop_curve, 0.75) == pytest.approx(7 * 0.75 + 700 / 900)
    assert interpolate(8, PROF.bracket_curve) == pytest.approx(3 + 0.3 / 1.55)
    assert interpolate(5.0, ()) == 0.0                                               # empty curve: de tolerates it, returns 0


def test_score_curve_small_deck_by_hand():
    cards = [
        make_card("Zhulodok, Void Gorger", cmc=6.0, type_line="Legendary Creature — Eldrazi"),      # price 1.00, rank 1000
        make_card("Sol Ring", cmc=1.0),                                                             # price 1.00, rank 1000
        make_card("Wastes", cmc=0.0, type_line="Basic Land", prices={"usd": "0.10", "eur": "0.05"}),
        make_card("Ancient Tomb", cmc=0.0, type_line="Land", prices={"usd": None, "eur": None}, edhrec_rank=None),
    ]
    s = score_curve(_facts(cards, "1 Zhulodok, Void Gorger\n\n1 Sol Ring\n2 Wastes\n1 Ancient Tomb\n"), PROF)
    by = {c.name: c for c in s.cards}
    assert by["Sol Ring"].price_part == pytest.approx(1.75, abs=1e-4) and by["Sol Ring"].pop_part == pytest.approx(6.0278, abs=1e-4)
    assert by["Sol Ring"].impact == pytest.approx(7.7778, abs=1e-4) and by["Sol Ring"].bucket == 1
    assert by["Wastes"].impact == pytest.approx(4.0) and by["Wastes"].is_land and by["Wastes"].count == 2
    assert by["Ancient Tomb"].impact == 0.0 and by["Ancient Tomb"].is_land
    assert s.missing_price == 1 and s.missing_rank == 1
    assert s.avg_cmc == pytest.approx(3.5) and s.tipping_bucket == 6
    assert s.efficiency == pytest.approx(0.65 + 0.45 * (6 - 4.75) / 4.25, abs=1e-6)
    assert s.total_impact == pytest.approx(2 * 7.7778 + 4.0, abs=1e-3) and s.nonland_impact == pytest.approx(2 * 7.7778, abs=1e-3)
    assert s.power_level == pytest.approx(s.total_impact * s.efficiency / 250, abs=1e-4)
    assert s.bracket_estimate == 1 and s.profile == "edhpowerlevel-2026-08"
    assert s.cards[0].impact >= s.cards[-1].impact
    assert any("EDHREC rank" in n for n in s.notes) and any("USD" in n for n in s.notes)


def test_reserved_list_price_is_scaled_and_modal_dfc_is_a_land():
    cards = [
        make_card("Commander", cmc=3.0, type_line="Legendary Creature"),
        make_card("Gaea's Cradle", cmc=0.0, type_line="Legendary Land", reserved=True, prices={"usd": "10.00", "eur": "9.00"}),
        make_card("Wandering Archaic // Explore the Vastlands", cmc=5.0, layout="modal_dfc", type_line="Creature — Avatar // Sorcery"),
    ]
    s = score_curve(_facts(cards), PROF)
    by = {c.name: c for c in s.cards}
    assert by["Gaea's Cradle"].price_part == pytest.approx(2.75, abs=1e-4)   # 10 × 0.2 = 2.0 → segment 2
    assert by["Wandering Archaic // Explore the Vastlands"].is_land and by["Wandering Archaic // Explore the Vastlands"].bucket == 0
    assert s.avg_cmc == pytest.approx(3.0)                                     # the MDFC is excluded from the nonland average
    assert any("modal" in n.lower() for n in s.notes)
    assert any("reserved-list" in n and "×0.2" in n for n in s.notes)


def test_reserved_list_note_is_absent_without_a_reserved_card():
    cards = [make_card("Commander", cmc=3.0, type_line="Legendary Creature"), make_card("Sol Ring", cmc=1.0)]
    s = score_curve(_facts(cards), PROF)
    assert not any("reserved-list" in n for n in s.notes)


def test_tipping_share_is_populated_from_the_profile():
    cards = [make_card("Commander", cmc=3.0, type_line="Legendary Creature"), make_card("Sol Ring", cmc=1.0)]
    s = score_curve(_facts(cards), PROF)
    assert s.tipping_share == PROF.tipping_share


def test_bracket_breakpoint_note_appears_when_power_hits_the_last_breakpoint():
    # A deck stacked with high-price, high-popularity nonland cards drives power to the cap (10.0),
    # exactly the last entry of bracket_curve — the site's interpolation quirk this note explains.
    cards = [make_card("Commander", cmc=3.0, type_line="Legendary Creature")]
    for i in range(60):
        cards.append(make_card(f"Bomb {i}", cmc=4.0, prices={"usd": "500.00", "eur": "450.00"}, edhrec_rank=1))
    s = score_curve(_facts(cards), PROF)
    assert s.power_level >= PROF.bracket_curve[-1]
    assert any("last bracket breakpoint" in n for n in s.notes)


def test_bracket_breakpoint_note_is_absent_below_the_cap():
    cards = [make_card("Commander", cmc=3.0, type_line="Legendary Creature"), make_card("Sol Ring", cmc=1.0)]
    s = score_curve(_facts(cards), PROF)
    assert s.power_level < PROF.bracket_curve[-1]
    assert not any("last bracket breakpoint" in n for n in s.notes)


def test_missing_rank_note_does_not_claim_a_site_delta():
    cards = [
        make_card("Commander", cmc=3.0, type_line="Legendary Creature"),
        make_card("Unranked Thing", cmc=2.0, edhrec_rank=None),
    ]
    s = score_curve(_facts(cards), PROF)
    rank_notes = [n for n in s.notes if "EDHREC rank" in n]
    assert rank_notes, "expected a note about the missing-rank card"
    assert not any("top bucket" in n.lower() for n in s.notes)  # the site scores unranked cards 0 too, not top-bucket
    assert any("count" in n.lower() for n in rank_notes)         # surfacing the count is our addition, and the note should say so


def test_basic_names_are_the_site_list():
    assert BASIC_LAND_NAMES == frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
                                          "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
                                          "Snow-Covered Mountain", "Snow-Covered Forest", "Snow-Covered Wastes"})


def test_to_dict_is_json_shaped():
    s = score_curve(_facts([make_card("Commander", cmc=3.0, type_line="Legendary Creature"), make_card("Sol Ring", cmc=1.0)]), PROF)
    d = s.to_dict()
    assert isinstance(d["cards"], list) and d["cards"][0]["name"] and "power_level" in d and isinstance(s, CurveScore)
