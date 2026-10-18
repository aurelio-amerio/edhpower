from edhpower.analysis import analyse
from edhpower.config import load_config
from edhpower.narrative import Narrative, build_narrative, idle_window

from .conftest import fixture_facts

CFG = load_config()


def _parts(name, iterations=60, run_sim=True):
    a = analyse(fixture_facts(name), iterations=iterations, run_sim=run_sim)
    return a.facts, a.bracket, a.curve, a.components, a.tipping, a.sim


def test_idle_window_finds_the_longest_run_from_turn_two():
    assert idle_window({1: 1.0, 2: 0.1, 3: 0.3, 4: 0.4, 5: 0.1, 6: 0.5, 7: 0.5, 8: 0.5}, 0.25) == (6, 8)
    assert idle_window({1: 1.0, 2: 0.3, 3: 0.3, 4: 0.0, 5: 0.3, 6: 0.3}, 0.25) == (2, 3)
    assert idle_window({1: 1.0, 2: 0.0, 3: 0.1}, 0.25) is None
    assert idle_window({}, 0.25) is None


def test_findings_cover_every_kind_with_a_sim():
    n = build_narrative(*_parts("ulalek-bracket3-v2"), CFG.narrative)
    assert isinstance(n, Narrative)
    kinds = [f.kind for f in n.findings]
    assert kinds.count("bracket") >= 1 and {"components", "scorers", "tipping", "idle", "combos", "clocks"} <= set(kinds) and "simulation" not in kinds
    text = "\n".join(f.text for f in n.findings)
    assert "is forced by game_changers" in text and "Ancient Tomb" in text
    assert "Weakest components: fast_mana" in text and len(n.weakest) == CFG.narrative.lowest_components
    assert "Closed-form tipping point T3 for 4 mana" in text
    assert "1 of 2 Spellbook line(s) simulated" in text and "not simulated: Ulalek, Fused Atrocity + Echoes of Eternity + Kozilek's Unsealing (templated" in text
    assert "Medians: commander T" in text
    d = n.to_dict()
    assert set(d) == {"findings", "idle_window", "weakest"} and all(set(f) == {"kind", "text"} for f in d["findings"])


def test_findings_without_a_sim():
    n = build_narrative(*_parts("precon-eldrazi-unbound", run_sim=False), CFG.narrative)
    kinds = {f.kind for f in n.findings}
    assert "simulation" in kinds and not ({"tipping", "idle", "combos", "clocks"} & kinds)
    assert n.idle_window is None
    assert any("No official criterion raises the floor: minimum bracket 2" in f.text for f in n.findings)


def test_scorer_disagreement_is_reported_when_the_gap_is_large():
    facts, bracket, curve, components, tipping, sim = _parts("zhulodok-bracket3")
    # zhulodok: curve 4.66 vs components 5.77 → gap 1.1 < 2.0 → "agree"
    text = "\n".join(f.text for f in build_narrative(facts, bracket, curve, components, tipping, sim, CFG.narrative).findings)
    assert "The two scorers agree within 1.1 points" in text
    from dataclasses import replace
    wide = replace(CFG.narrative, scorer_gap=1.0)
    text = "\n".join(f.text for f in build_narrative(facts, bracket, curve, components, tipping, sim, wide).findings)
    assert "The two scorers disagree: curve model 4.66 vs component model 5.77 (gap 1.1)" in text


def test_unevaluated_inputs_are_named_not_scored():
    import dataclasses
    facts = dataclasses.replace(fixture_facts("ulalek-bracket3-v2"), tags_status="skipped (--no-tags)", combos=None, combos_unavailable_reason="Spellbook unreachable")
    a = analyse(facts, iterations=30)
    text = "\n".join(f.text for f in a.narrative.findings)
    assert "Component model unevaluated (tags: skipped (--no-tags))" in text
    assert "Combo clocks unevaluated: Spellbook was unavailable" in text
    assert "two_card_combos could not be evaluated" in text
    assert "disagree" not in text and "agree within" not in text
