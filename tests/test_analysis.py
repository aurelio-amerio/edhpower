from datetime import UTC, datetime

from edhpower import __version__
from edhpower.analysis import Analysis, analyse
from edhpower.config import load_config
from edhpower.decklist import parse_decklist
from edhpower.facts import build_facts
from edhpower.scryfall import CardData, Resolution

from .conftest import full_tag_cache, make_card


def _facts(tagged=True):
    cards = [make_card("Commander", cmc=4.0, type_line="Legendary Creature"), make_card("Sol Ring", cmc=1.0, oracle_text="{T}: Add {C}{C}."),
             make_card("Forest", cmc=0.0, type_line="Basic Land — Forest", oracle_text="({T}: Add {G}.)")]
    res = Resolution({c["name"]: CardData.from_scryfall(c) for c in cards}, [], 0, None)
    cache = full_tag_cache(**{"mana-rock": ["Sol Ring"], "ramp": ["Sol Ring"]}) if tagged else None
    return build_facts(parse_decklist("1 Commander\n\n1 Sol Ring\n30 Forest\n"), res, None, "offline", "t.txt", tag_cache=cache)


def test_analyse_bundles_every_number_and_stamps_config():
    a = analyse(_facts(), now=datetime(2026, 9, 10, tzinfo=UTC), iterations=20)
    assert isinstance(a, Analysis) and a.bracket.minimum_bracket == 2
    assert a.curve.profile == "edhpowerlevel-2026-08" and a.components.status == "partial"
    assert a.tipping.target >= 2 and a.freshness.now == "2026-09-10T00:00:00Z"
    d = a.to_dict()
    assert set(d) == {"tool", "config", "facts", "payoffs", "bracket", "scores", "tipping", "sim", "narrative", "freshness"}
    assert d["tool"] == {"name": "edhpower", "version": __version__} and d["config"] == load_config().stamp()
    assert d["scores"]["curve"]["power_level"] == a.curve.power_level and d["scores"]["components"]["total"] == a.components.total
    assert d["facts"]["schema_version"] == 2


def test_analyse_without_tags_marks_dependents_unevaluated():
    a = analyse(_facts(tagged=False), iterations=20)
    assert a.components.status == "unevaluated"
    assert next(c for c in a.bracket.criteria if c.name == "tutors").status == "unevaluated"
    assert a.tipping.fast_mana == 1   # fast mana is numeric, not tag-based, so the tipping point still sees Sol Ring


def test_analyse_runs_the_sim_with_the_tipping_target_and_stamps_it():
    a = analyse(_facts(), iterations=25)
    assert a.sim is not None and a.sim.iterations == 25 and a.sim.sim_version == load_config().sim.version
    assert a.sim.clocks["tipping_target"].label.startswith(f"{a.tipping.target} mana available")
    assert a.to_dict()["sim"]["iterations"] == 25 and a.to_dict()["config"]["sim_version"] == 2
    assert {f.kind for f in a.narrative.findings} >= {"bracket", "tipping", "clocks"}


def test_analyse_can_skip_the_sim():
    a = analyse(_facts(), run_sim=False)
    assert a.sim is None and a.to_dict()["sim"] is None
    assert any(f.kind == "simulation" for f in a.narrative.findings)


def test_analysis_carries_payoffs_once():
    from edhpower.analysis import analyse
    from edhpower.payoffs import DeckPayoffs, detect
    from .conftest import fixture_facts
    facts = fixture_facts("ulalek-bracket3-v2")
    a = analyse(facts, iterations=10)
    assert isinstance(a.payoffs, DeckPayoffs) and a.payoffs == detect(facts)
    assert a.to_dict()["payoffs"] == a.payoffs.to_dict()
    assert a.sim is not None and a.sim.payoffs == a.payoffs.by_category
    assert a.config["sim_version"] == 2
