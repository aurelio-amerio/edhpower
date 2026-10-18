from datetime import UTC, datetime

from edhpower.decklist import parse_decklist
from edhpower.facts import build_facts
from edhpower.freshness import THRESHOLDS_DAYS, Freshness, assess_freshness
from edhpower.scryfall import CardData, Resolution

from .conftest import make_card

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _facts(fetched: dict):
    facts = build_facts(parse_decklist("1 Sol Ring\n"), Resolution({"Sol Ring": CardData.from_scryfall(make_card("Sol Ring"))}, [], 0, None), None, None, "t.txt")
    facts.fetched.update(fetched)
    return facts


def test_fresh_caches_have_ages_and_no_warnings():
    f = assess_freshness(_facts({"scryfall_cards_oldest": "2026-09-09T12:00:00Z", "scryfall_cards_newest": "2026-09-10T11:00:00Z",
                                 "scryfall_cards_unknown": 0, "tags_oldest": "2026-09-01T00:00:00Z", "spellbook": "2026-09-10T11:59:00Z"}), now=NOW)
    assert isinstance(f, Freshness) and f.ages_days["scryfall_cards"] == 1.0 and f.ages_days["tags"] == 9.5
    assert f.ages_days["spellbook"] < 0.01 and f.warnings == [] and f.now == "2026-09-10T12:00:00Z"


def test_stale_caches_warn_with_thresholds():
    f = assess_freshness(_facts({"scryfall_cards_oldest": "2026-08-01T00:00:00Z", "scryfall_cards_unknown": 0, "tags_oldest": "2026-07-01T00:00:00Z"}), now=NOW)
    assert THRESHOLDS_DAYS == {"scryfall_cards": 7, "tags": 30}
    assert any("card cache" in w and "40.5 days" in w and "7 days" in w for w in f.warnings)
    assert any("tag cache" in w and "30 days" in w for w in f.warnings)


def test_unknown_and_missing_stamps_are_reported_not_assumed():
    f = assess_freshness(_facts({"scryfall_cards_oldest": None, "scryfall_cards_unknown": 3, "tags_oldest": None, "spellbook": None}), now=NOW)
    assert f.ages_days["scryfall_cards"] is None and f.ages_days["tags"] is None
    assert any("3 cached card(s) carry no fetch date" in w for w in f.warnings)
    assert any("tag cache" in w and "no fetch date" in w for w in f.warnings)
    d = f.to_dict()
    assert set(d) == {"ages_days", "warnings", "now"}


def test_boundary_exactly_at_threshold_does_not_warn():
    # scryfall_cards threshold is 7 days, tags threshold is 30 days; "at or below" must not warn.
    f = assess_freshness(_facts({"scryfall_cards_oldest": "2026-09-03T12:00:00Z", "scryfall_cards_unknown": 0,
                                  "tags_oldest": "2026-08-11T12:00:00Z"}), now=NOW)
    assert f.ages_days["scryfall_cards"] == 7.0 and f.ages_days["tags"] == 30.0
    assert not any("card cache" in w for w in f.warnings)
    assert not any("tag cache" in w for w in f.warnings)


def test_boundary_just_over_threshold_warns():
    f = assess_freshness(_facts({"scryfall_cards_oldest": "2026-09-03T11:00:00Z", "scryfall_cards_unknown": 0,
                                  "tags_oldest": "2026-08-11T11:00:00Z"}), now=NOW)
    assert f.ages_days["scryfall_cards"] > 7.0 and f.ages_days["tags"] > 30.0
    assert any("card cache" in w and "7 days" in w for w in f.warnings)
    assert any("tag cache" in w and "30 days" in w for w in f.warnings)
