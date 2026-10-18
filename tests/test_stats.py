from edhpower.scryfall import CardData
from edhpower.stats import color_identity_violations, game_changers, mana_curve, pip_counts, price_totals

from .conftest import make_card


def C(name, **kw) -> CardData:
    return CardData.from_scryfall(make_card(name, **kw))


def test_mana_curve_buckets_and_averages():
    deck = [
        (C("Wastes", type_line="Basic Land", cmc=0.0), 18),
        (C("Sol Ring", cmc=1.0), 1),
        (C("Thought-Knot Seer", cmc=4.0, type_line="Creature — Eldrazi"), 1),
        (C("Ulamog", cmc=10.0, type_line="Legendary Creature — Eldrazi"), 1),
        (C("Emrakul", cmc=15.0, type_line="Legendary Creature — Eldrazi"), 1),
    ]
    s = mana_curve(deck)
    assert s.land_count == 18 and s.nonland_count == 4
    assert s.buckets == {"0": 0, "1": 1, "2": 0, "3": 0, "4": 1, "5": 0, "6": 0, "7+": 2}
    assert s.avg_cmc_nonland == 7.5 and s.median_cmc_nonland == 7.0


def test_mana_curve_with_no_nonlands():
    s = mana_curve([(C("Wastes", type_line="Basic Land", cmc=0.0), 5)])
    assert s.avg_cmc_nonland is None and s.median_cmc_nonland is None


def test_pip_counts_handles_colourless_hybrid_phyrexian_generic():
    deck = [
        (C("Ulalek", mana_cost="{C/W}{C/U}{C/B}{C/R}{C/G}"), 1),
        (C("Kozilek", mana_cost="{8}{C}{C}"), 1),
        (C("Bolt", mana_cost="{R}"), 2),
        (C("Gitaxian Probe", mana_cost="{U/P}"), 1),
        (C("Walker", mana_cost="{X}{2}{G}{G}"), 1),
    ]
    assert pip_counts(deck) == {"W": 0, "U": 1, "B": 0, "R": 2, "G": 2, "C": 2, "hybrid": 5}


def test_price_totals_count_missing_and_use_copies():
    deck = [
        (C("A", prices={"usd": "2.00", "eur": "1.50"}, edhrec_rank=10), 2),
        (C("B", prices={"usd": None, "eur": "0.10"}, edhrec_rank=None), 1),
    ]
    t = price_totals(deck)
    assert t.usd == 4.0 and t.eur == 3.1
    assert t.missing_usd == 1 and t.missing_eur == 0 and t.missing_edhrec == 1


def test_price_totals_all_missing_is_none():
    t = price_totals([(C("A", prices={"usd": None, "eur": None}), 1)])
    assert t.usd is None and t.eur is None


def test_color_identity_violations():
    deck = [(C("Wastes", color_identity=[]), 1), (C("Unsealing", color_identity=["U"]), 1), (C("Bolt", color_identity=["R"]), 1)]
    assert color_identity_violations(deck, set()) == ["Bolt", "Unsealing"]
    assert color_identity_violations(deck, {"U"}) == ["Bolt"]


def test_game_changers_sorted():
    deck = [(C("Mana Vault", game_changer=True), 1), (C("Ancient Tomb", game_changer=True), 1), (C("Sol Ring"), 1)]
    assert game_changers(deck) == ["Ancient Tomb", "Mana Vault"]
