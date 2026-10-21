"""Human-readable report. Reads an Analysis; computes nothing new (every number, label and sentence is a field)."""

from __future__ import annotations

from edhpower.analysis import Analysis
from edhpower.payoffs import CATEGORY_LABELS
from edhpower.sim import NOT_MODELLED
from edhpower.stats import BUCKETS


def _hist(buckets: dict[str, int]) -> list[str]:
    width = max(buckets.values(), default=0)
    lines = []
    for b in BUCKETS:
        n = buckets.get(b, 0)
        bar = "#" * (n if width <= 40 else round(n * 40 / width))
        lines.append(f"  {b:>2} | {bar} {n}")
    return lines


def _truncated(items: list[str], limit: int, sep: str = ", ") -> str:
    shown = sep.join(items[:limit])
    return shown + (f"{sep}… (+{len(items) - limit})" if len(items) > limit else "")


def _names(names: list[str], limit: int = 8) -> str:
    return "none" if not names else _truncated(names, limit)


def _status_text(row: dict) -> str:
    res = "/".join(row["resources"]) or "no recognised product"
    if row["status"] == "direct":
        return "direct win"
    if row["status"] == "payoff":
        return f"{res} → {_names(row['candidates'], 3)}"
    if row["status"] == "no_payoff":
        fuel = row.get("fuel_only") or []
        if fuel:
            parts = []
            for f in fuel:
                needs = [CATEGORY_LABELS.get(n, n) for n in f["needs"]]
                needs_text = ", ".join(needs[:-1]) + (" or " if len(needs) > 1 else "") + needs[-1]
                parts.append(f"{_names(f['cards'], 3)} is fuel only: no {needs_text} in deck")
            return f"{res} → " + "; ".join(parts)
        return f"{res} → no payoff in deck"
    return res


def _fmt(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def render_text(analysis: Analysis) -> str:
    facts, verdict = analysis.facts, analysis.bracket
    out: list[str] = []
    out.append(f"edhpower {facts.tool_version} — {facts.source_path}")
    out.append(f"Commander(s): {', '.join(facts.commanders) or '(none identified)'}")
    out.append(f"Cards: {facts.total_cards} resolved")
    out.append("")

    warnings = []
    warnings += [f"Warning: {w}" for w in facts.parse_warnings]
    warnings += [f"Parse error: {e}" for e in facts.parse_errors]
    if facts.unresolved:
        warnings.append("Unresolved: " + ", ".join(facts.unresolved))
    if facts.identity_violations:
        warnings.append("Colour-identity violations (identity " + ("".join(facts.commander_identity) or "colourless") + "): " + ", ".join(facts.identity_violations))
    warnings += [f"Warning: {w}" for w in analysis.freshness.warnings]
    if warnings:
        out.extend(warnings)
        out.append("")

    c = facts.curve
    out.append(f"Mana curve (non-land, {c.nonland_count} cards; {c.land_count} lands)")
    out.extend(_hist(c.buckets))
    out.append(f"  avg MV {c.avg_cmc_nonland}  median {c.median_cmc_nonland}")
    out.append("Pips: " + "  ".join(f"{k}={v}" for k, v in facts.pips.items()))
    p = facts.prices
    out.append(f"Prices: USD {_fmt(p.usd)}  EUR {_fmt(p.eur)}  (missing usd={p.missing_usd}, eur={p.missing_eur}, edhrec_rank={p.missing_edhrec})")
    out.append("")

    out.append(f"Game Changers ({len(facts.game_changers)}): " + (", ".join(facts.game_changers) or "none"))
    out.append("")

    if facts.combos is None:
        out.append(f"Combos: unavailable ({facts.combos_unavailable_reason})")
    else:
        cb = facts.combos
        out.append(f"Combos: {len(cb.included)} included, {cb.almost_included_count} almost (identity {cb.identity}, Spellbook tag {cb.spellbook_bracket_tag})")
        for line in cb.included:
            flags = cb.combo_flags.get(line.id)
            speed = f", speed {flags.speed}" if flags and flags.speed is not None else ""
            two = ", two-card" if flags and flags.definitely_two_card else ""
            tmpl = "; ".join(f"template: {t.name}" for t in line.templates) or "no templates"
            first = line.produces[0] if line.produces else "?"
            out.append(f"  - {' + '.join(line.piece_names)} [{line.bracket_tag}{speed}{two}] -> {first} ({tmpl})")
    out.append("")

    pc, pn, tp = facts.partition_counts, facts.partition, analysis.tipping
    out.append(f"Functional profile (tags: {facts.tags_status})")
    out.append(f"  lands {pc['lands']} (1-mana {tp.land_classes['one']}, 2-mana {tp.land_classes['two']}, utility {tp.land_classes['utility']})")
    out.append(f"  fast mana {pc['fast_mana']}: {_names(pn['fast_mana'])}")
    out.append(f"  rocks {pc['mana_rocks']} · dorks {pc['mana_dorks']} · land ramp {pc['land_ramp']} · rituals {pc['rituals']} · other ramp {pc['other_ramp']} · cost reducers {pc['cost_reducers']}")
    out.append(f"  tutors {pc['tutors']}: {_names(pn['tutors'])}")
    out.append(f"  counterspells {pc['counterspells']} · removal {pc['removal']} · board wipes {pc['board_wipes']} · cantrips {pc['cantrips']} · card advantage {pc['card_advantage']}")
    out.append(f"  extra turns {pc['extra_turns']} · mass land denial {pc['mass_land_denial']} · pitch spells {pc['pitch_spells']} · stax {pc['stax']} · creatures {pc['creatures']}")
    out.append(f"  special behaviours: {_names(facts.special_hits, 20)}")
    if facts.tags_status == "ok":
        out.append(f"  untagged ({len(facts.untagged)}): {_names(facts.untagged, 12)}")
    out.append("")

    cs, comp = analysis.curve, analysis.components
    out.append("Scores")
    out.append(f"  Curve model ({cs.profile}): power {cs.power_level:.2f} (bracket estimate {cs.bracket_estimate if cs.bracket_estimate is not None else 'n/a'})")
    out.append(f"    total impact {cs.total_impact:.1f} × efficiency {cs.efficiency:.3f}; avg MV (MDFC as land) {cs.avg_cmc}, {cs.tipping_share:.0%} of impact by MV {cs.tipping_bucket}; missing price {cs.missing_price}, rank {cs.missing_rank}")
    for n in cs.notes:
        out.append(f"    note: {n}")
    if comp.status == "unevaluated":
        out.append(f"  Component model ({comp.profile}): unevaluated")
    else:
        parts = " · ".join(f"{r.name} {_fmt(r.score, 1)}" for r in comp.components)
        out.append(f"  Component model ({comp.profile}): {_fmt(comp.total, 2)}/10 ({comp.status}) — {parts}")
        for r in comp.components:
            out.append(f"    {r.name:<15} count {r.count:g} / cap {r.cap:g} → {_fmt(r.score, 2)} × {r.weight:.2f}  {r.detail}")
        out.append(f"    archetype (informational): {comp.archetype} — {comp.archetype_reason}")
    for n in comp.notes:
        out.append(f"    note: {n}")
    out.append("")

    out.append("Tipping point")
    reached = f"{tp.threshold:.0%} reached on turn {tp.turn} (p={tp.probability:.2f})" if tp.turn is not None else f"{tp.threshold:.0%} not reached by turn {tp.max_turn} (p={tp.probability:.2f})"
    out.append(f"  target {tp.target} mana (functional avg MV {_fmt(tp.functional_avg_mv)}); {reached}")
    out.append("  " + "  ".join(f"T{t} {p:.2f}" for t, p in tp.curve.items()))
    out.append(f"  boosts: fast mana {tp.fast_mana} → +{tp.boosts['fast_mana']:.2f}; ramp {tp.ramp} → +{tp.boosts['ramp']:.2f} from turn {tp.ramp_boost_from_turn}")
    for n in tp.notes:
        out.append(f"  note: {n}")
    out.append("")

    sim = analysis.sim
    if sim is None:
        out.append("Goldfish simulation: skipped (--no-sim)")
    else:
        turns = list(range(2, sim.max_turn + 1))
        w = max([52, *(len(c.label) for c in sim.clocks.values())])   # the label column fits the longest clock label
        out.append(f"Goldfish simulation (sim v{sim.sim_version}, {sim.iterations} games, seed {sim.seed})")
        out.append(f"  {'clock':<{w}} {'median':<7} {'fast':<7} " + " ".join(f"T{t:<4d}" for t in turns))
        for c in sim.clocks.values():
            med = "unevaluated" if c.status != "ok" else (f"T{c.median}" if c.median is not None else f">T{sim.max_turn}")
            fast = "" if c.status != "ok" else (f"T{c.fast}" if c.fast is not None else f">T{sim.max_turn}")
            row = " ".join(f"{c.by_turn[t]:4.0%} " for t in turns) if c.status == "ok" else ""
            out.append(f"  {c.label:<{w}} {med:<7} {fast:<7} {row}")
        out.append(f"  {'avg mana produced':<{w}} {'':<7} {'':<7} " + " ".join(f"{sim.mana_by_turn[t]:4.1f} " for t in turns))
        out.append(f"  {'share of games casting nothing':<{w}} {'':<7} {'':<7} " + " ".join(f"{sim.idle_by_turn[t]:4.0%} " for t in turns))
        for label, series in [("damage this turn", sim.damage_by_turn), ("board power", sim.board_power_by_turn), ("lands on battlefield", sim.lands_by_turn),
                              ("lands entering this turn", sim.landfall_by_turn), ("lands in graveyard", sim.graveyard_lands_by_turn),
                              ("distinct land names", sim.distinct_lands_by_turn),
                              *((f"tokens: {k}", sim.tokens_by_turn[k]) for k in sorted(sim.tokens_by_turn))]:
            out.append(f"  {label:<{w}} {'':<7} {'':<7} " + " ".join(f"{series[t]:4.1f} " for t in turns))
        wr = sim.win_route
        out.append(f"  win route: combat {wr['combat']:.0%} · combo {wr['combo']:.0%} · none {wr['none']:.0%}")
        out.append(f"  biggest swing (median) {sim.max_swing_median}")
        shown = [f"{row['label']} [{_status_text(row)}]" for row in sim.line_status]
        out.append(f"  lines simulated: {_truncated(shown, 6, '; ') if shown else 'none'}")
        if sim.lines_skipped:
            out.append("  not simulated: " + _truncated([f"{s.label} ({s.reason})" for s in sim.lines_skipped], 6, "; "))
        relevant = {c for row in sim.line_status for c in row["categories"]}
        relevant |= {n for row in sim.line_status for f in row.get("fuel_only", []) for n in f["needs"]}
        cats = [c for c in CATEGORY_LABELS if c in relevant or sim.payoffs.get(c)]
        if cats:
            out.append("  payoffs: " + "; ".join(f"{CATEGORY_LABELS[c]}: {_names(sim.payoffs.get(c, []), 4) if sim.payoffs.get(c) else 'none'}" for c in cats))
        else:
            out.append("  payoffs: none detected, and no simulated line needs one")
        cov = sim.coverage
        out.append(f"  model coverage: lands {cov['land']} · rocks {cov['rock']} · dorks {cov['dork']} · one-shot {cov['one_shot']} · reducers {cov['reducer']} · ramp spells {cov['ramp_spell']} · draw spells {cov['draw_spell']} · tutors {cov['tutor']} · threats {cov['threat']} · creatures {cov['creature']} · engines {cov['engine']} · other permanents {cov['permanent']} · spells {cov['spell']} · held {cov['held']} · unmodelled {len(sim.unmodelled)}")
        src = sim.effects_sources
        eff = f"  effects: table {len(src['table'])} ({_names(src['table'], 4)}) · forge {len(src['forge'])} · unmodelled: {_names(sim.unmodelled, 4)}"
        if sim.partial:
            eff += f" · partial: {_names(sim.partial, 4)}"
        out.append(eff)
        out.append(f"  not modelled: {', '.join(NOT_MODELLED)}")
        for n in sim.notes:
            out.append(f"  note: {n}")
    out.append("")

    out.append("Findings")
    for f in analysis.narrative.findings:
        out.append(f"  - [{f.kind}] {f.text}")
    out.append("")

    out.append(f"Bracket — minimum bracket: {verdict.minimum_bracket}")
    for cr in verdict.criteria:
        floor = f" floor {cr.floor}" if cr.floor is not None else ""
        out.append(f"  {cr.name:<28} {cr.status:<11}{floor}  {cr.detail}")
        for t in cr.triggers:
            out.append(f"      - {t}")
    for n in verdict.notes:
        out.append(f"  note: {n}")
    out.append(f"  criteria source: {verdict.source_url} ({verdict.source_date})")
    out.append("")

    out.append(f"Data freshness (as of {analysis.freshness.now}; config {analysis.config['config_version']}, profiles {analysis.config['curve_profile']} / {analysis.config['components_profile']})")
    for key, age in analysis.freshness.ages_days.items():
        out.append(f"  {key}: {'unknown' if age is None else f'{age:.1f} days'}")
    for k, v in facts.fetched.items():
        out.append(f"  {k}: {v if v is not None else 'n/a'}")
    return "\n".join(out) + "\n"
