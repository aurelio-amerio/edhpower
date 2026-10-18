"""One call that turns DeckFacts into every reported number. Pure; no network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from edhpower import __version__
from edhpower.bracket import BracketVerdict, evaluate_bracket
from edhpower.config import ScoringConfig, load_config
from edhpower.facts import DeckFacts
from edhpower.freshness import Freshness, assess_freshness
from edhpower.narrative import Narrative, build_narrative
from edhpower.payoffs import DeckPayoffs, detect
from edhpower.scorers.components import ComponentScore, score_components
from edhpower.scorers.curve import CurveScore, score_curve
from edhpower.sim import SimResult, simulate
from edhpower.tipping import TippingPoint, tipping_point


@dataclass
class Analysis:
    facts: DeckFacts
    payoffs: DeckPayoffs
    bracket: BracketVerdict
    curve: CurveScore
    components: ComponentScore
    tipping: TippingPoint
    sim: SimResult | None
    narrative: Narrative
    freshness: Freshness
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": {"name": "edhpower", "version": __version__},
            "config": dict(self.config),
            "facts": self.facts.to_dict(),
            "payoffs": self.payoffs.to_dict(),
            "bracket": self.bracket.to_dict(),
            "scores": {"curve": self.curve.to_dict(), "components": self.components.to_dict()},
            "tipping": self.tipping.to_dict(),
            "sim": self.sim.to_dict() if self.sim is not None else None,
            "narrative": self.narrative.to_dict(),
            "freshness": self.freshness.to_dict(),
        }


def analyse(facts: DeckFacts, config: ScoringConfig | None = None, now: datetime | None = None, *,
            iterations: int | None = None, run_sim: bool = True) -> Analysis:
    cfg = config or load_config()
    payoffs = detect(facts)
    bracket = evaluate_bracket(facts)
    curve = score_curve(facts, cfg.curve)
    components = score_components(facts, cfg.components)
    tipping = tipping_point(facts, cfg.tipping)
    sim = simulate(facts, cfg.sim, iterations if iterations is not None else cfg.sim.iterations, tipping.target, payoffs) if run_sim else None
    return Analysis(
        facts=facts,
        payoffs=payoffs,
        bracket=bracket,
        curve=curve,
        components=components,
        tipping=tipping,
        sim=sim,
        narrative=build_narrative(facts, bracket, curve, components, tipping, sim, cfg.narrative),
        freshness=assess_freshness(facts, now),
        config=cfg.stamp(),
    )
