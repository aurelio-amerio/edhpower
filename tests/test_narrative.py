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


def test_combos_findings_name_payoff_gaps_and_locks():
    from edhpower.sim import Clock, SimResult
    facts, bracket, curve, components, tipping, sim = _parts("ulalek-bracket3-v2", iterations=20)
    import dataclasses
    doctored = dataclasses.replace(
        sim,
        lines_simulated=["A + B", "C + D"],
        line_status=[{"label": "A + B", "status": "no_payoff", "resources": ["mana"], "categories": ["mana_sink"], "candidates": [], "hand_ok": False},
                     {"label": "C + D", "status": "payoff", "resources": ["etb"], "categories": ["etb_damage"], "candidates": ["E"], "hand_ok": False}],
        lines_skipped=[dataclasses.replace(sim.lines_skipped[0], reason="lock only")] if sim.lines_skipped else [],
    )
    text = "\n".join(f.text for f in build_narrative(facts, bracket, curve, components, tipping, doctored, CFG.narrative).findings if f.kind == "combos")
    assert "1 infinite engine(s) have no payoff in this deck: A + B" in text
    if sim.lines_skipped:
        assert "1 lock line(s) excluded from the combo clock" in text


def _with(sim, **kw):
    from dataclasses import replace
    clocks = dict(sim.clocks)
    if "median" in kw:
        clocks["win"] = replace(clocks["win"], median=kw.pop("median"))
    return replace(sim, clocks=clocks, **kw)


def _texts(**kw):
    f, b, c, comp, t, sim = _parts("ulalek-bracket3-v2")
    return [x for x in build_narrative(f, b, c, comp, t, _with(sim, **kw), CFG.narrative).findings]


def test_win_finding_hints_bracket3_window():
    win = next(x for x in _texts(median=7) if x.kind == "win")
    assert "Median win T7" in win.text and "typical of" in win.text


def test_win_finding_flags_fast_median():
    assert "counting something twice" in next(x for x in _texts(median=5) if x.kind == "win").text
    assert "later than" in next(x for x in _texts(median=10) if x.kind == "win").text
    assert "no win by T" in next(x for x in _texts(median=None) if x.kind == "win").text


def test_coverage_finding_threshold():
    assert any(x.kind == "coverage" for x in _texts(nonland_count=10, unmodelled=["a", "b", "c"]))
    assert not any(x.kind == "coverage" for x in _texts(nonland_count=10, unmodelled=["a", "b"]))
    assert not any(x.kind == "coverage" for x in _texts(nonland_count=0, unmodelled=["a"]))
    assert "3 of 10 nonland" in next(x for x in _texts(nonland_count=10, unmodelled=["a", "b", "c"]) if x.kind == "coverage").text
