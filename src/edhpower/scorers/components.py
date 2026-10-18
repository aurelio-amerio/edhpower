"""Component model: six capped functional components from the partitioned DeckFacts counts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from edhpower.config import ComponentsProfile, Part
from edhpower.facts import DeckFacts

RAMP_KEYS = ("fast_mana", "mana_rocks", "mana_dorks", "land_ramp", "rituals", "other_ramp")


@dataclass
class ComponentResult:
    name: str
    count: float
    cap: float
    score: float | None
    weight: float
    detail: str
    contributors: list[str]


@dataclass
class ComponentScore:
    profile: str
    status: str
    components: list[ComponentResult]
    total: float | None
    archetype: str | None
    archetype_reason: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _capped(count: float, cap: float) -> float:
    return 10.0 * min(count, cap) / cap if cap > 0 else 0.0


def _result(name: str, count: float, part: Part, contributors: list[str], detail: str) -> tuple[ComponentResult, float]:
    """Returns the (rounded-for-display) ComponentResult alongside the unrounded raw score, so
    callers can accumulate the weight-normalised mean from full-precision parts — matching how
    curve.py keeps its accumulators unrounded and only rounds stored/returned values."""
    raw = _capped(count, part.cap)
    return ComponentResult(name, float(count), part.cap, round(raw, 3), part.weight, detail, sorted(contributors)), raw


def _combo_counts(facts: DeckFacts) -> tuple[int, int]:
    if facts.combos is None:
        return 0, 0
    two = sum(1 for line in facts.combos.included if (f := facts.combos.combo_flags.get(line.id)) is not None and f.definitely_two_card)
    return two, len(facts.combos.included)


def infer_archetype(facts: DeckFacts, prof: ComponentsProfile, ramp_total: float, interaction: float) -> tuple[str, str]:
    a = prof.archetype
    pc = facts.partition_counts
    two, lines = _combo_counts(facts)
    if two >= a["combo_min_two_card"] or (lines >= a["combo_min_lines"] and pc["tutors"] >= a["combo_min_tutors"]):
        return "combo", f"{two} two-card line(s), {lines} combo line(s), {pc['tutors']} tutor(s)"
    if pc["stax"] >= a["stax_min"]:
        return "stax", f"{pc['stax']} tax/hatebear piece(s)"
    if interaction >= a["control_min_interaction"] and pc["counterspells"] >= a["control_min_counterspells"]:
        return "control", f"{interaction:g} interaction piece(s) incl. {pc['counterspells']} counterspell(s)"
    if pc["creatures"] >= a["creature_min"]:
        return "creature-based", f"{pc['creatures']} creature(s)"
    avg = facts.curve.avg_cmc_nonland or 0.0
    if avg >= a["big_mana_min_avg_mv"] and ramp_total >= a["big_mana_min_ramp"]:
        return "big-mana", f"avg MV {avg} with {ramp_total:g} ramp piece(s)"
    return "midrange", "no archetype rule matched"


def score_components(facts: DeckFacts, prof: ComponentsProfile) -> ComponentScore:
    if facts.tags_status != "ok":
        return ComponentScore(prof.name, "unevaluated", [], None, None, "", [f"tags unavailable ({facts.tags_status}); the component model needs the tag partition"])
    pc, pn, parts = facts.partition_counts, facts.partition, prof.parts
    notes: list[str] = []
    results: list[ComponentResult] = []
    raw_scores: list[tuple[float, float]] = []  # (weight, unrounded score) for evaluated components only

    def add(result: ComponentResult, raw: float | None) -> None:
        results.append(result)
        if raw is not None:
            raw_scores.append((result.weight, raw))

    add(*_result("fast_mana", pc["fast_mana"], parts["fast_mana"], pn["fast_mana"], "non-land, MV ≤ 2, net mana on resolution ≥ MV"))
    add(*_result("tutors", pc["tutors"], parts["tutors"], pn["tutors"], "otag:tutor"))
    interaction = pc["counterspells"] + pc["removal"] + pc["board_wipes"]
    add(*_result("interaction", interaction, parts["interaction"], pn["counterspells"] + pn["removal"] + pn["board_wipes"],
                 f"counterspells {pc['counterspells']} + removal {pc['removal']} + board wipes {pc['board_wipes']}"))
    card_adv = pc["cantrips"] + pc["card_advantage"]
    add(*_result("card_advantage", card_adv, parts["card_advantage"], pn["cantrips"] + pn["card_advantage"],
                 f"cantrips {pc['cantrips']} + card advantage {pc['card_advantage']}"))

    if facts.combos is None:
        add(ComponentResult("combos", 0.0, parts["combos"].cap, None, parts["combos"].weight,
                            f"unevaluated: {facts.combos_unavailable_reason or 'combo data unavailable'}", []), None)
        notes.append("combos component unevaluated; the total is renormalised over the other components")
    else:
        two, lines = _combo_counts(facts)
        count = prof.combo_two_card_value * two + prof.combo_other_value * (lines - two)
        contributors = [" + ".join(line.piece_names) for line in facts.combos.included]
        raw = _capped(count, parts["combos"].cap)
        add(ComponentResult("combos", float(count), parts["combos"].cap, round(raw, 3), parts["combos"].weight,
                            f"{two} two-card line(s) × {prof.combo_two_card_value:g} + {lines - two} other line(s) × {prof.combo_other_value:g}", contributors), raw)

    avg = facts.curve.avg_cmc_nonland or 0.0
    span = prof.curve_avg_mv_worst - prof.curve_avg_mv_best
    curve_part = 10.0 * min(1.0, max(0.0, (prof.curve_avg_mv_worst - avg) / span)) if span > 0 else 0.0
    ramp_total = sum(pc[k] for k in RAMP_KEYS)
    ramp_part = _capped(ramp_total, prof.curve_ramp_cap)
    curve_score = (1 - prof.curve_ramp_share) * curve_part + prof.curve_ramp_share * ramp_part
    add(ComponentResult("curve", round(avg, 3), parts["curve"].cap, round(curve_score, 3), parts["curve"].weight,
                        f"avg MV {avg} (best {prof.curve_avg_mv_best:g}, worst {prof.curve_avg_mv_worst:g}) → {curve_part:.1f}; ramp {ramp_total:g}/{prof.curve_ramp_cap:g} → {ramp_part:.1f}",
                        []), curve_score)

    weight_sum = sum(w for w, _ in raw_scores)
    total = round(sum(w * s for w, s in raw_scores) / weight_sum, 3) if weight_sum else None
    status = "ok" if len(raw_scores) == len(results) else "partial"
    archetype, reason = infer_archetype(facts, prof, ramp_total, interaction)
    return ComponentScore(prof.name, status, results, total, archetype, reason, notes)
