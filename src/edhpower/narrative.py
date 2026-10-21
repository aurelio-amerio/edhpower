"""Narrative findings: sentences derived from numbers the analysis already computed. Not a model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from edhpower.bracket import BracketVerdict
from edhpower.config import NarrativeConfig
from edhpower.facts import DeckFacts
from edhpower.scorers.components import ComponentScore
from edhpower.scorers.curve import CurveScore
from edhpower.sim import SimResult
from edhpower.tipping import TippingPoint


@dataclass
class Finding:
    kind: str
    text: str


@dataclass
class Narrative:
    findings: list[Finding]
    idle_window: tuple[int, int] | None
    weakest: list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["idle_window"] = list(self.idle_window) if self.idle_window else None
        return d


def idle_window(idle_by_turn: dict[int, float], threshold: float) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    start: int | None = None
    for t in sorted(idle_by_turn):
        if t >= 2 and idle_by_turn[t] >= threshold:
            start = t if start is None else start
            if best is None or t - start > best[1] - best[0]:
                best = (start, t)
        else:
            start = None
    return best


def _turn(t: int | None, max_turn: int) -> str:
    return f"T{t}" if t is not None else f">T{max_turn}"


def build_narrative(facts: DeckFacts, bracket: BracketVerdict, curve: CurveScore, components: ComponentScore,
                    tipping: TippingPoint, sim: SimResult | None, cfg: NarrativeConfig) -> Narrative:
    findings: list[Finding] = []

    floors = [c for c in bracket.criteria if c.floor is not None]
    for c in floors:
        findings.append(Finding("bracket", f"Bracket {bracket.minimum_bracket} is forced by {c.name} ({', '.join(c.triggers) or c.detail})"))
    if not floors:
        findings.append(Finding("bracket", f"No official criterion raises the floor: minimum bracket {bracket.minimum_bracket}"))
    for c in bracket.criteria:
        if c.status == "unevaluated":
            findings.append(Finding("bracket", f"{c.name} could not be evaluated"))

    weakest: list[str] = []
    if components.status == "unevaluated":
        findings.append(Finding("components", f"Component model unevaluated (tags: {facts.tags_status})"))
    else:
        scored = sorted((r for r in components.components if r.score is not None), key=lambda r: (r.score, r.name))
        weakest = [r.name for r in scored[: cfg.lowest_components]]
        parts = ", ".join(f"{r.name} {r.score:.1f}/10 ({r.count:g} of cap {r.cap:g})" for r in scored[: cfg.lowest_components])
        findings.append(Finding("components", f"Weakest components: {parts}"))
        if components.total is not None:
            gap = abs(curve.power_level - components.total)
            if gap >= cfg.scorer_gap:
                findings.append(Finding("scorers", f"The two scorers disagree: curve model {curve.power_level:.2f} vs component model {components.total:.2f} (gap {gap:.1f}); the curve model rewards price and popularity, the component model reads function"))
            else:
                findings.append(Finding("scorers", f"The two scorers agree within {gap:.1f} points ({curve.power_level:.2f} vs {components.total:.2f})"))

    window: tuple[int, int] | None = None
    if sim is None:
        findings.append(Finding("simulation", "Simulation skipped (--no-sim): tipping, idle, combo and clock findings are unavailable"))
        return Narrative(findings, None, weakest)

    win = sim.clocks["win"]
    m, wr = win.median, sim.win_route
    if m is None:
        hint = f"no win by T{sim.max_turn} in half the games"
    elif m < 6:
        hint = "earlier than Bracket 3 decks usually close (T6): a Bracket 4 hint, or the model is counting something twice"
    elif m <= 8:
        hint = "typical of an uncontested Bracket 3 deck (T6–T8)"
    else:
        hint = "later than Bracket 3 decks usually close (T8)"
    findings.append(Finding("win", f"Median win {_turn(m, sim.max_turn)} (fast games {_turn(win.fast, sim.max_turn)}), via combat {wr['combat']:.0%} / combo {wr['combo']:.0%}; {hint}"))

    n = sim.nonland_count
    if n > 0:
        copies = {e.name: e.count for e in facts.entries if not e.is_commander}
        k = sum(copies.get(u, 1) for u in sim.unmodelled)
        if k / n >= cfg.unmodelled_share:
            shown = ", ".join(sim.unmodelled[:4]) + (f", … (+{len(sim.unmodelled) - 4})" if len(sim.unmodelled) > 4 else "")
            findings.append(Finding("coverage", f"{k} of {n} nonland cards have no modelled effect ({shown}); every clock is a floor and the deck is not comparable with a well-covered list"))

    sim_target = sim.clocks["tipping_target"].median
    text = (f"Closed-form tipping point {_turn(tipping.turn, tipping.max_turn)} for {tipping.target} mana; "
            f"the simulation reaches {tipping.target} mana in half the games by {_turn(sim_target, sim.max_turn)}")
    if tipping.turn is not None and sim_target is not None and abs(tipping.turn - sim_target) >= 2:
        text += f", a gap of {abs(tipping.turn - sim_target)} turn(s) — the closed form ignores colours, mulligans and enters-tapped lands"
    findings.append(Finding("tipping", text))

    window = idle_window(sim.idle_by_turn, cfg.idle_share)
    if window:
        findings.append(Finding("idle", f"The deck casts nothing in at least {cfg.idle_share:.0%} of games during turns {window[0]}–{window[1]}"))
    else:
        findings.append(Finding("idle", f"No turn window after turn 1 has the deck idle in {cfg.idle_share:.0%} or more of games"))

    if sim.combos_status != "ok":
        findings.append(Finding("combos", "Combo clocks unevaluated: Spellbook was unavailable"))
    elif not sim.lines_simulated and not sim.lines_skipped:
        findings.append(Finding("combos", "No Spellbook lines to simulate"))
    else:
        k, s = len(sim.lines_simulated), len(sim.lines_skipped)
        combo = sim.clocks["combo"]
        text = (f"{k} of {k + s} Spellbook line(s) simulated; a line is assembled by {_turn(combo.median, sim.max_turn)} in half the games "
                f"and in {combo.reached:.0%} of games by T{sim.max_turn}")
        if sim.lines_skipped:
            shown = "; ".join(f"{x.label} ({x.reason})" for x in sim.lines_skipped[:3])
            more = f" … (+{s - 3} more)" if s > 3 else ""
            text += f"; not simulated: {shown}{more}"
        findings.append(Finding("combos", text))
        gaps = [row["label"] for row in sim.line_status if row["status"] == "no_payoff"]
        if gaps:
            findings.append(Finding("combos", f"{len(gaps)} infinite engine(s) have no payoff in this deck: {'; '.join(gaps[:3])}" + (f" … (+{len(gaps) - 3} more)" if len(gaps) > 3 else "")))
        locks = [x.label for x in sim.lines_skipped if x.reason == "lock only"]
        if locks:
            findings.append(Finding("combos", f"{len(locks)} lock line(s) excluded from the combo clock: {'; '.join(locks[:3])}" + (f" … (+{len(locks) - 3} more)" if len(locks) > 3 else "")))

    c = sim.clocks
    findings.append(Finding("clocks", (f"Medians: commander {_turn(c['commander'].median, sim.max_turn)}, {c['mana_threshold'].label} "
                                      f"{_turn(c['mana_threshold'].median, sim.max_turn)}, {c['threat'].label} {_turn(c['threat'].median, sim.max_turn)}, "
                                      f"{c['combat'].label} {_turn(c['combat'].median, sim.max_turn)}, {c['lethal_table'].label} {_turn(c['lethal_table'].median, sim.max_turn)}")))
    return Narrative(findings, window, weakest)
