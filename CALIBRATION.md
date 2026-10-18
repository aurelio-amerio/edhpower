# Calibration table

Reference numbers per deck and date. The curve model is a faithful port, so its delta against
edhpowerlevel.com is attributable (price vendor, printing, rank drift, the site's override list).
The component model, tipping point and simulator have no external anchor and are compared for
direction only. This is a reference table, not a set of assertions — `tests/test_golden.py`
pins our own numbers.

**Comparison rule: only compare numbers produced by the same `config_version` and `sim_version`.**
Both are stamped into the JSON output (`config.stamp()`) and printed in the human report. A
scoring-constant or engine change bumps one or both, and a number produced under one version is
not directly comparable to a number produced under another — see the two engine corrections noted
under *Simulator (sim v1, 20 000 games)* below for a concrete case of numbers moving between
versions.

**Provenance caveat: these rows are computed from the frozen `.facts.json` fixtures, and a fixture
carries whatever card profiles the extractor produced on the day it was frozen.** That is
deliberate — frozen inputs are what make `tests/test_golden.py` meaningful — but it means a row is
not always what a live run of the same decklist reports today. Concretely: `precon-eldrazi-unbound`,
`ulalek-bracket3-v2`, `ulalek-b5` and `zhulodok-bracket3` were frozen before triggered "adds" text
stopped counting as a mana ability, so in them Forsaken Monument and From Beyond still read as mana
sources (`mana_per_activation = 1`); `ulalek-bracket4-v2`, frozen after, reads 0. For a deck running
such cards the stale profiles run about a turn fast — the `ulalek-bracket3-v2` row reports 7 mana at
T7 and the first MV 7+ spell at T9, where a live 0.3.0 run of the same list gives T8 and T10
(`deck/b3/v2/ulalek-b3-v2-benchmarks.md`, 2026-09-11). Treat this table as the cross-deck reference
at *fixed inputs*, and a live run as the reference for a deck. Re-freezing the four older fixtures
would move their goldens and is a deliberate future change, not a fix to slip in.

How to fill the external columns: paste the same decklist into https://edhpowerlevel.com and
https://scrollvault.net/tools/commander-bracket on the same day, and record what they show.
Note the price vendor the site used. Leave a cell as `—` rather than guessing.

| deck | date | edhpower | config | curve power | curve bracket est. | component total | archetype | official bracket | tipping | sim commander (median) | sim 7 mana | sim MV7+ threat | sim 40 combat | sim combo (reached by T12) | sim lines (simulated/total) | edhpowerlevel score | edhpowerlevel bracket | scrollvault bracket | scrollvault tipping | price source (ours) | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| zhulodok-bracket3 | 2026-09-10 | 0.3.0 | 1 / edhpowerlevel-2026-08 / v1 / sim 1 | 4.66 | 1 | 5.77 | creature-based | 3 | T4 (p=0.81, target 6) | T5 | T6 | T7 | T9 | 0% (0 lines) | 0/0 | — | — | — | — | Scryfall USD, default printing | avg MV 5.94, efficiency 0.547 — the lowest curve power of the four despite 742.5 total impact; 9 untagged, 6 cards without a USD price, 1 without an EDHREC rank; bracket-est 1 because power 4.66 < the first breakpoint 4.7 |
| ulalek-bracket3-v2 | 2026-09-11 | 0.3.0 | 1 / edhpowerlevel-2026-08 / v1 / sim 1 | 7.74 | 4 | 6.61 | combo | 3 | T3 (p=0.97, target 4) | T5 | T7 | T9 | T11 | 7% | 1/2 | — | — | — | — | Scryfall USD, default printing | avg MV 4.23, efficiency 0.850, impact 832.8; 2 Spellbook lines included (Basalt Monolith + Forsaken Monument is the kept late-game line); 10 untagged, 8 without a USD price |
| ulalek-b5 | 2026-09-10 | 0.3.0 | 1 / edhpowerlevel-2026-08 / v1 / sim 1 | 10.00 | 1 (model quirk, read as 5) | 9.07 | combo | 4 | T1 (p=0.88, target 2) | T6 | T8 | >T12 | >T12 | 20% | 3/3 | — | — | — | — | Scryfall USD, default printing | avg MV 2.15, efficiency 1.013, impact 1060.5; 15 Game Changers, 3 combo lines, early-combo review flag; 19 untagged, 7 without a USD price. **Bracket estimate is a faithful-port artifact** — see below |
| precon-eldrazi-unbound | 2026-09-10 | 0.3.0 | 1 / edhpowerlevel-2026-08 / v1 / sim 1 | 5.19 | 2 | 4.31 | creature-based | 2 | T4 (p=0.83, target 5) | T5 | T6 | T9 | T9 | 0% (0 lines) | 0/0 | — | — | — | — | Scryfall USD, default printing | avg MV 4.61, efficiency 0.724, impact 593.3; 0 Game Changers, 0 combo lines, every bracket criterion `ok`; 19 untagged, 5 without a USD price |
| ulalek-bracket4-v2 | 2026-09-11 | 0.3.0 | 1 / edhpowerlevel-2026-08 / v1 / sim 1 | 9.68 | 5 | 9.24 | combo | 4 | T3 (p=0.96, target 3) | T6 | T8 | >T12 | >T12 | 41% | 9/17 | — | — | — | — | Scryfall USD, default printing | avg MV 2.84, efficiency 0.976, impact 988.2; 14 Game Changers, 17 Spellbook lines included (91 almost-included), 9 of the 17 survive simulator selection (the rest are over the per-deck line cap or need a template the sim does not resolve); 18 untagged, 8 without a USD price |

Deck sources: `tests/fixtures/decks/*.txt` (copies; the package never reads the repo's `deck/` tree).
The precon list comes from EDHREC's precon page for Eldrazi Unbound (Commander Masters, 2023),
fetched 2026-09-10; the bracket-5 list is the repo's Moxfield export with five printed flavour
names replaced by their Oracle names (recorded in the file's trailing comments).

## Observed orderings and findings

Direction, as asserted by `tests/test_fixtures.py::test_contrast_lists_rank_in_the_expected_direction`:

- curve power: precon 5.19 < ulalek-b3 7.74 < ulalek-b5 10.00 ✔
- component total: precon 4.31 < zhulodok 5.77 < ulalek-b3 6.61 < ulalek-b5 9.07 ✔
- official minimum bracket: precon 2 ≤ ulalek-b3 3 ≤ ulalek-b5 4 ✔ (the b5 list is bracket 5 by
  declaration; 4 is the floor the published criteria actually force)
- tipping: b5 T1 ≤ precon T4 ✔

Two results are worth recording rather than smoothing:

1. **The curve model rates the precon (5.19) above the tuned Zhulodok bracket-3 list (4.66).**
   Not a bug: Zhulodok is a cascade payoff deck with average MV 5.94 against the precon's 4.61,
   and the model's efficiency term (0.547 vs 0.724) punishes that harder than the extra impact
   (742.5 vs 593.3) rewards it. The component model, which reads the functional profile instead
   of the curve, orders them the other way round (5.77 vs 4.31) — which is why both scores are
   reported side by side and never blended. The direction test therefore compares the precon
   against the *Ulalek* bracket-3 list, not against Zhulodok.
2. **`curve_bracket_estimate` is 1 for ulalek-b5 despite a curve power of 10.00.** The site's
   interpolation helper returns 0 for a value exactly equal to the last breakpoint (pinned in
   `tests/test_curve.py::test_interpolate_matches_the_site_helper`), and the power score is
   capped at 10.00, which is exactly the last entry of `bracket_curve`. We clamp the result to
   a minimum of 1, so a maxed-out deck reads as bracket 1. The port is faithful, so the quirk is
   kept; read a curve power of 10.00 as bracket 5. Zhulodok's estimate of 1 is *not* a quirk —
   its power of 4.66 is genuinely below the first breakpoint (4.7).

`untagged` counts of 9–19 per deck are cards carrying none of the 21 tracked oracle-tag slugs
(vanilla or near-vanilla creatures, Lightning Greaves, Skittering Cicada, Peter Parker's Camera),
not a misbehaving slug: every slug fetched its full advertised card count, and `tags_status` is
`ok` in all four fixtures. An untagged card contributes nothing to the component score rather
than being scored 0 with confidence — a missing input never becomes a confident number.

**The bracket-5 deck's component total (9.07) is therefore a floor, not a like-for-like number.**
Its 19 untagged cards include real interaction and untap engines — Voltaic Key, Manifold Key,
Unwinding Clock, Strionic Resonator, Clock of Omens, Silence, Orim's Chant, Noxious Revival,
Seedborn Muse — which fall outside the 21 verified slugs and so are counted in no component.
Read it as "at least 9.07", and do not compare it against the other three decks as if all four
had equal tag coverage.

**The Mox Opal gap is live in a shipped golden.** `is_fast_mana` does not consult a
`special_behaviours` entry's `requires` param, so Mox Opal (`requires = "metalcraft"` in
`special_behaviours.toml`) counts as unconditional fast mana rather than a conditional one.
`ulalek-b5`'s `fast_mana` list contains it, which puts that component at cap 6/6 = 10.0; the
strict reading (excluding Mox Opal) gives 5/6 → 8.33, about 0.33 off the component total (at
weight 0.20). Not fixed here — flagging it so the gap doesn't read as a silent inaccuracy.

**Three of six components sit at their cap for all four reference decks.** `interaction` is
10.0 for every deck (counts 18–30 against a cap of 12); `card_advantage` is 10.0 for three of
four; `tutors` is 10.0 for three of four. That is 30% of the weight (interaction + card_advantage
+ tutors) effectively constant across the reference set, so the component total's discrimination
between these four decks comes almost entirely from `fast_mana`, `combos` and `curve`. The
`removal` tag (which feeds `interaction`) is very broad and is the main driver of that cap. A
reader should know this before over-reading the headline component total as measuring the full
six-component spread.

### Simulator (sim v1, 20 000 games)

Measured on this machine (2026-09-11), `--from-facts` against the five frozen fixtures at the
production default of 20 000 iterations: 20 000 games take 6.5–8.4 s per deck on this machine
(precon 6.51s, zhulodok 8.38s, ulalek-b3 7.46s, ulalek-b4 8.14s, ulalek-b5 7.26s).

**Commander-castable median.** Observed: zhulodok T5 = precon T5 = ulalek-bracket3-v2 T5, then
ulalek-bracket4-v2 T6 = ulalek-b5 T6 — the two highest-bracket, highest-combo-count lists are
the slowest to cast their commander, not the fastest. This is the opposite direction from the
predicted `b5 ≤ b4 ≤ b3 ≤ precon`: report what the simulator actually shows, not what was
expected. (The three Ulalek lists all run Ulalek as commander at the same MV, so the difference
is entirely land/ramp shape, not commander cost.)

**7-mana-available median, the three Ulalek lists only.** ulalek-bracket3-v2 reaches 7 mana
fastest (T7), with ulalek-bracket4-v2 and ulalek-b5 tied slowest (T8 each) despite ulalek-b5
running the fewest lands (27, against 36 for both b3 and b4) and the most fast mana (6, against
5 and 2) — land count, not fast-mana count, dominates a raw "7 mana available" goldfish clock
with no opponent, consistent with the b5-vs-precon caveat below.

**The b5-vs-precon caveat.** The plan predicted `ulalek-b5` would reach 7 mana by turn 5 more
often than `precon-eldrazi-unbound`. It does not: measured **0.256667 (b5) vs 0.353333 (precon)
at N=300**, and stable at N=3000. The cause is land count, not power level — b5 runs **27 lands
to the precon's 38**, and a goldfish with no opponents rewards raw land count for a "7 mana by
T5" question regardless of how much fast mana or how low a curve the rest of the deck carries.
`tests/test_sim.py::test_contrast_decks_goldfish_in_the_expected_direction` asserts the measured
direction (`precon.clocks["mana_threshold"].by_turn[5] > b5.clocks["mana_threshold"].by_turn[5]`)
with this reasoning captured in a code comment, so nobody re-derives it from scratch.

**Two engine corrections that moved these numbers (Task 6).** Both were corrections to the
simulator's own engine code, not tuning changes, and both are worth knowing before comparing any
of the sim figures above against an earlier run of the same fixtures:

- A mana **doubler** now adds one unit per source tapped for colourless mana, rather than
  doubling the source itself. This moved `mana_by_turn`, the `mana_threshold` clock, and the
  `tipping_target` clock for every fixture running a doubler (e.g. Forsaken Monument).
- The **`threat` clock** (`MV 7+ spell cast from hand`) now stamps for high-MV instants and
  sorceries, not only permanents. This matters because All Is Dust (MV 7) is in the
  `zhulodok-bracket3` list, and four of the five fixtures carry MV7+ instants or sorceries
  (every fixture except `ulalek-b5`; All Is Dust alone accounts for four of them) that would
  previously never have registered on this clock.

**Comparison against the retired name-table simulator.** `TODO.md` (2026-09-09) reported "any
combo online 17% by T6 / 51% by T10" for ulalek-bracket4-v2 and "2% / 7%" for ulalek-bracket3-v2;
`CLAUDE.md` reported, for ulalek-bracket3-v2, "median commander turn 4, 7 mana by T5 in 53% of
games, first haymaker median T6". Sim v1 measures, on the same two fixtures: ulalek-bracket4-v2
combo-line-assembled 14% by T6 / 30% by T10; ulalek-bracket3-v2 combo-line-assembled 2% by T6 /
5% by T10; ulalek-bracket3-v2 commander median T5, 7 mana available by T5 in 26% of games, first
MV7+ threat (the closest analogue to "first haymaker") median T9. These numbers do not match the
retired figures and are not meant to: the old simulator was colour-blind (it paid any mana for
any cost) and drove its model off a hand-maintained card-name table rather than `CardProfile` /
`SpecialBehaviour` fields. The old figures are retired, not reproduced — sim v1's colour-aware,
data-driven model is the new baseline and the two are not directly comparable.

**Known limits of sim v1** (each a source of systematic bias, not noise):

- Mana payment is greedy by colour; it does not hold up a wrong-coloured source hoping for a
  better later play.
- Interaction (counterspells, removal, board wipes) is never cast — the goldfish has nothing to
  interact with.
- Tutors dig only for a simulated Spellbook combo line; a tutor with no line to fetch is held
  rather than fetching a generic threat, which under-counts tutor-into-threat play.
- Land-ramp spells (Nature's Lore, Three Visits, etc.) fetch any 1-mana land, tapped, regardless
  of what the deck actually wants.
- Command Tower-style lands are read as five-colour sources regardless of the commander's actual
  colour identity.
- Cheat-into-play, reanimation, extra combats and copy effects are not modelled.
- Commander tax is not modelled.
- The Mox Opal `requires` gap (see above) is fixed in the simulator's mana model but still open
  in the static `fast_mana` component.
