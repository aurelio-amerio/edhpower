# Idea: payoff-weighted combos component

**Status:** deferred (2026-10-18). Follow-up to the sim payoff gating work.

## What

Make the component model's `combos` part aware of whether each infinite Spellbook line has a
payoff in the deck. Today every `included` line counts: two-card lines at `combo_two_card_value`
(1.0), other lines at `combo_other_value` (0.5), capped at 4. An infinite-mana engine with no
mana sink, or an infinite-ETB engine with no ETB payoff, scores the same as a real win.

Proposed: a line whose produced resources have no matching payoff category in the deck counts at
a reduced value (for example half), and a lock-only line ("prevent all damage", "lock") counts
zero. The payoff detection is the same unit the simulator uses (Spellbook `produces` → resource
→ payoff category → deck cards).

## Why deferred

- Needs coefficient tuning: the combos part is already at cap for most tuned decks, so the
  reduced value only matters once the cap is no longer saturated. Which values discriminate
  usefully is an empirical question across the fixture decks.
- Re-baselines `tests/test_golden.py` and bumps `config_version` in `scoring.toml`.
- Scrollvault does not do this; its combo component is speed-weighted by piece mana value, not
  payoff-weighted. There is no external anchor for the coefficients.

## When to pick it up

After the sim payoff gating ships and the per-line payoff status is visible in the report, run
the five fixture decks plus the Necrobloom list and look at how many lines are payoff-less in
each. If the spread is informative, tune `combo_two_card_value` / `combo_other_value` and add a
`combo_no_payoff_value`; otherwise leave the component as is.
