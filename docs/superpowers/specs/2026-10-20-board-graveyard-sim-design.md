# Board, graveyard and a shared win clock for the goldfish simulator

**Date:** 2026-10-20. **Status:** stages 1–2 implemented (sim v4, 2026-10-21). Plan in
`docs/superpowers/plans/`.

## Problem

The simulator (sim v2) plays one land per turn, has no graveyard, creates no tokens and counts
combat damage as the printed power of nontoken creatures. Decks whose engine is lands, tokens or
the graveyard get a clock that is far too slow, and read as idle. The Necrobloom list
(`~/github/necrobloom-deck/v3/decklist.txt`) is the motivating case: it ramps into its
commander on turn 3–4 (the simulator gets that right), then dredges lands back every turn,
makes a Plant or a 2/2 Zombie on every land drop, and wins by returning every land in the
graveyard to the battlefield at once and swinging with the tokens. Sim v2 reports "40 combat
damage at T11" and "casts nothing in 40% of games from T8", both artefacts of what it leaves
out, not of how the deck plays.

The second problem is the headline number. The clocks today (commander, 7 mana, MV7+ threat,
40 combat damage to one opponent, combo) are each a floor on one route to a win. For comparing
decks with different strategies there is no single number that means "this deck wins on turn
N".

## Decisions taken with the user

1. **A win is lethal to the table.** Three opponents at 40 life. Combat (creatures and tokens,
   with anthems and pumps), drain effects and infinite combos with a payoff all count toward it.
2. **The headline comparison number is the win turn**, reported as the median and a fast-games
   figure. Deck-specific counts (tokens, Zombies) are diagnostics, not scores.
3. **The engine stays generic.** Landfall, tokens, graveyard, dredge, extra land drops, land
   recursion, pumps and reanimation are implemented as game rules usable by any deck. Which
   card does what comes from oracle-text patterns and the `special_behaviours.toml` table. No
   card names in the engine, as today.
4. **Three stages**, each shippable on its own: (1) board and damage, (2) graveyard and lands,
   (3) reanimation and draw engines.
5. **For the Necrobloom deck the numbers that matter**, in order: total combat damage from
   creatures and tokens, Zombies by turn, the size of the biggest single swing (pumps included),
   and whether big threats get reanimated.
6. **Coverage is shown prominently.** A deck the simulator understands poorly must say so,
   because its clock is not comparable with a well-covered deck's.

## Goals

- A `win` clock: first turn the table is dead by any modelled route. Median plus the 5th
  percentile ("fast games") per deck.
- Tokens as real permanents that attack, with their creature type known so the report can
  count them per type.
- Landfall and ETB triggers that create tokens, add counters, make mana or drain opponents.
- Static anthems and one-turn pump spells counted in combat, pumps held for a lethal swing.
- A graveyard zone: milled, sacrificed and discarded cards go there; cards can come back.
- Dredge replacing the draw; extra land drops; playing lands from the graveyard; returning
  many lands from graveyard to battlefield at once; self-sacrificing lands (fetches, horizons).
- A "lands with different names" count (Necrobloom's Zombie threshold, Field of the Dead).
- Reanimation of creatures from the graveyard; "whenever a land is milled, draw" engines.
- A coverage warning in the findings when a large share of the deck's nonland cards have no
  modelled effect.
- Golden fixtures extended with the Necrobloom list so a landfall deck is pinned.

## How the deck is meant to play (the owner's notes, 2026-10-20)

"The deck primer" below means these notes, given in conversation; there is no file. They
describe the archetype in general, so some cards named are not in the v3 list.

1. Ramp into a turn-3 Necrobloom, ideally with fetch lands and surveil lands.
2. Dredge lands back to hand to make land drops and fill the graveyard with more lands.
3. Use the tokens from Necrobloom and utility lands to stall while dredging.
4. Put all the dredged lands into play at once with landfall payoffs out (Aftermath Analyst,
   Splendid Reclamation, Scapeshift-style effects, Cultivator Colossus chains).
5. Fill the board with Zombies and swing for the win.

Interactions the owner relies on that this design does **not** model, to be listed in the
report's `not modelled:` line: cracking a fetch or horizon land and dredging it straight back
with Necrobloom (the land is sacrificed as a cost before the draw); the Gitrog Monster loop
(fetch → dredge → a milled land → another draw → dredge again); Sylvan Library replacing three
draws with dredges; Field of the Dead counting lands that enter simultaneously with it;
Cultivator Colossus + a dredge source chaining through the whole graveyard (the chain is
modelled but capped); fetching tapped surveil lands over basics when mana is not needed; life
management (fetches, shocks, horizons, Glacial Chasm, Yawgmoth); Room cards.

## Non-goals

- Opponents, blockers, interaction, removal. Still a goldfish.
- Life as a resource: fetch, shock and horizon-land damage, Glacial Chasm, Zuran Orb, Yawgmoth.
- The stack tricks listed above: Gitrog fetch-land loops, Sylvan Library dredge tricks,
  Field of the Dead simultaneous-ETB counting, Room cards.
- Scute Swarm's exponential copying, Avenger-style scaling beyond a simple "N tokens where N =
  lands you control" (the latter is in scope; copies are not).
- Haste. Tokens and creatures attack the turn after they enter.
- Changing the curve or component scorers. Only the simulator, its report block, narrative
  findings and the JSON change.

## Anti-goals (would make this a failure even if it works)

- Deck-specific logic in the engine: a heuristic that only makes sense for Necrobloom, a card
  name in `engine.py`, a "landfall mode" switch. Every rule must be stated for any deck.
- Silent assumptions: a card with an effect the simulator cannot read must appear in the report
  as unmodelled, never be assumed to do nothing quietly, never be assumed free.
- Breaking determinism: same decklist and iteration count must give the same numbers.
- A win clock that is faster than reality by construction (e.g. counting a pump every turn, or
  counting tokens that entered this turn). Where a simplification is needed, choose the one that
  makes the clock later, and note it.

## Constraints

- `DeckFacts` schema goes 2 → 3 once (stage 1) to carry the Forge script per entry; the five
  fixtures are re-frozen then and not again. Everything else new is derived at `build_sim_deck`
  time from `CardData` and the script.
- `special_behaviours.toml` stays the single table of per-card overrides; every card read from
  it is listed in the report (existing convention).
- `sim.version` bumps once per stage (3, 4, 5) because each stage changes the meaning of the
  clocks; goldens are re-baselined at each bump with `tests/golden_update.py`. The "only compare
  numbers from the same `sim_version`" rule in the eldrazi repo's CLAUDE.md already covers this.
- TDD throughout, per repo convention: unit tests on synthetic `SimCard`s for each mechanic,
  real oracle text for each pattern, goldens for the end-to-end numbers.
- Runtime: 20 000 games must stay around a minute for a 100-card deck. Tokens are counted, not
  simulated individually where a count suffices.

## Architecture

### Effects: what a card does (`sim/effects.py`, new)

A `SimCard` gains `effects: tuple[Effect, ...]`. An `Effect` is `(trigger, action, params,
condition)`:

- `trigger` ∈ `landfall` | `etb` (this permanent enters) | `creature_etb` (another creature
  enters) | `static` | `cast` (spell resolves) | `activated` (with a mana cost) | `upkeep` |
  `land_milled` | `dies`.
- `action` ∈ `token` (n, power, toughness, type) | `counters` (n, on: self | tokens | type) |
  `anthem` (+p/+t, scope: all | tokens | type) | `pump` (+p/+t until end of turn, scope) |
  `mana` (n, colours; Lotus Cobra, treasures) | `drain` (n, each_opponent) | `draw` (n) |
  `mill` (n) | `extra_land` (n) | `play_lands_from_graveyard` | `dredge` (n; on self or granted
  to lands) | `return_lands` (from graveyard to battlefield: all | n; tapped) |
  `return_lands_to_hand` (n) | `reanimate` (target: creature | permanent, MV filter) |
  `sacrifice_land` (self; or one land) | `fetch` (self-sacrifice, then a basic or typed land) |
  `chain_lands_from_hand` (Cultivator Colossus).
- `condition` optional: `distinct_lands >= N`, `lands >= N`, `tokens >= N`.

Effects come from two sources, in precedence order, exactly as mana behaviour does today:

1. **The table.** `special_behaviours.toml` entries gain an `effects` list. `kind` becomes
   optional for cards that only have effects. Example entries, which are also the acceptance
   list for the Necrobloom deck:

   ```toml
   [cards."The Necrobloom"]
   effects = [
     { on = "landfall", do = "token", n = 1, power = 0, toughness = 1, type = "Plant" },
     { on = "landfall", do = "token", n = 1, power = 2, toughness = 2, type = "Zombie",
       when = "distinct_lands >= 7", replaces = 0 },      # replaces the Plant above
     { on = "static", do = "dredge", n = 2, grants = "lands" },
   ]
   note = "Plant per land drop, Zombie at seven distinct lands; lands in graveyard get dredge 2"

   [cards."Avenger of Zendikar"]
   effects = [
     { on = "etb", do = "token", n = "lands", power = 0, toughness = 1, type = "Plant" },
     { on = "landfall", do = "counters", n = 1, on_type = "Plant" },
   ]

   [cards."Cultivator Colossus"]
   effects = [{ on = "etb", do = "chain_lands_from_hand" }]

   [cards."The Gitrog Monster"]
   effects = [
     { on = "upkeep", do = "sacrifice_land", n = 1 },
     { on = "land_milled", do = "draw", n = 1 },
     { on = "static", do = "extra_land", n = 1 },
   ]
   ```

2. **Forge card scripts** (decided with the user 2026-10-21, replacing the oracle-text
   patterns first drafted here). The Card-Forge project
   (`github.com/Card-Forge/forge`, `forge-gui/res/cardsfolder/<initial>/<slug>.txt`, GPL-3.0)
   has one script per card in a typed mini-language that already separates trigger, condition
   and effect, e.g. The Necrobloom:

   ```
   T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Land.YouCtrl | Execute$ TrigBranch | TriggerZones$ Battlefield | …
   SVar:TrigBranch:DB$ Branch | BranchConditionSVar$ X | BranchConditionSVarCompare$ GE7 | TrueSubAbility$ DBZombie | FalseSubAbility$ DBPlant
   SVar:DBPlant:DB$ Token | TokenScript$ g_0_1_plant | TokenOwner$ You
   SVar:DBZombie:DB$ Token | TokenScript$ b_2_2_zombie | TokenOwner$ You
   SVar:X:Count$Valid Land.YouCtrl$DifferentCardNames
   S:Mode$ Continuous | AffectedZone$ Graveyard | Affected$ Land.YouOwn | AddKeyword$ Dredge:2 | …
   ```

   Every shape this design needs is a small, fixed vocabulary of that language: `T:Mode$
   ChangesZone … ValidCard$ Land.YouCtrl` (landfall) / `Card.Self` (ETB) / `Creature.Other+
   YouCtrl` (creature ETB); `DB$ Token | TokenScript$ <colour>_<p>_<t>_<type> | TokenAmount$ X`;
   `DB$ PutCounterAll | ValidCards$ Creature.<Type>`; `S:Mode$ Continuous | Affected$
   Creature.(token+)?YouCtrl | AddPower$ N` (anthem) and the same on `A:SP$ PumpAll` (pump);
   `DB$ Mana | Produced$ Any`; `DB$ LoseLife | Defined$ Player.Opponent`; `K:Dredge:N` and
   `AddKeyword$ Dredge:N` with `AffectedZone$ Graveyard`; `S:Mode$ Continuous | Affected$ You |
   AddKeyword$ AdditionalLandDrop` or `MayPlay`-style land-from-graveyard statics; `A:SP$
   ChangeZoneAll | Origin$ Graveyard | Destination$ Battlefield | ChangeType$ Land`; `A:SP$
   ChangeZone | Origin$ Graveyard | Destination$ Hand | ValidTgts$ Land | TargetMax$ N`;
   `ChangeNum$ N` on a library→battlefield land search (Harrow = 2); `Cost$ … Sac<1/Land>`;
   `A:AB$ ChangeZone | Cost$ T Sac<1/CARDNAME> | Origin$ Library | ChangeType$ Land.Basic`
   (fetch); `Count$Valid Land.YouCtrl` / `$DifferentCardNames` for the two conditions. The
   reader (`sim/effects.py`) understands that vocabulary and nothing else; every `T:`, `A:`, `S:`
   line it does not understand makes the card **unmodelled**, so coverage is exact rather than
   heuristic.

   Fetching: `forge.py` (new) fetches `raw.githubusercontent.com/Card-Forge/forge/<commit>/
   forge-gui/res/cardsfolder/<initial>/<slug>.txt` per card through the existing `HttpClient`,
   at a commit pinned in `scoring.toml` (`[forge] commit`), cached under
   `EDHPOWER_CACHE_DIR/forge/<commit>/`. Slug = NFKD-ASCII-folded name, lower-cased, punctuation
   (`' , . : ! ? "`) dropped, spaces and hyphens → `_`, DFC faces joined with `_` (verified:
   `azusa_lost_but_seeking`, `thespians_stage`, `jotun_grunt`, `lim_dul_the_necromancer`,
   `walk_in_closet_forgotten_cellar`). A 404 is recorded as "no script", not an error. The script
   text is stored on each `FactEntry` (`forge_script: str | None`) so `--from-facts` stays
   offline; `facts.fetched["forge_commit"]` records the pin. **`DeckFacts` schema becomes 3**
   and the five fixtures are re-frozen once by fetching their scripts. Forge unreachable
   degrades like the tag cache: table-only effects, a note, and the component/curve scores
   untouched; `--no-forge` skips it on purpose.

   Licence: the scripts are read at run time as data, exactly like Scryfall's; nothing from
   Forge is vendored into this MIT repo.

   A card the scripts describe but the table also lists uses the table entry only.

The existing `payoffs.py` detection stays as the combo-payoff check on oracle text; the new
effects module is the simulator's view. Where they overlap (landfall drain, token makers) the
report must show the same cards; a disagreement is a test failure, not a note.

### Zones and board (`sim/engine.py`)

- `Game` gains `graveyard: list[str]`, `land_drops: int` (per turn, 1 + extras), and
  three opponent life totals.
- Tokens are `Perm`s with a synthetic `SimCard` (name = `<type> token`, `is_creature`,
  `power`, `subtypes = {type}`, no cost, role `token`). A `Perm` gains `counters: int` and
  `entered` already exists for summoning sickness.
- Distinct land names on the battlefield are a set maintained on enter/leave.
- Events: `_land_entered(perm)` fires every `landfall` effect on the board (and increments a
  per-turn landfall counter for diagnostics); `_creature_entered`; `_milled(name)` fires
  `land_milled` when the card is a land; `_to_graveyard(name)` for sacrifice, death and spells
  that resolved (instants and sorceries now go to the graveyard, not nowhere).
- Draw step: if a dredge is available (a card with `dredge` in the graveyard, or a land in the
  graveyard while a `grants = "lands"` dredge source is on the battlefield) **and** the hand holds
  fewer lands than this turn's land drops, dredge the best land by `_land_priority` and mill N;
  otherwise draw. Dredge never replaces the opening hand.
- Land step: play up to `land_drops` lands, from hand first, then from the graveyard when a
  `play_lands_from_graveyard` source is on the battlefield. A fetch land is cracked on entry
  (the deck primer's "crack on the opponent's turn" is irrelevant to a goldfish); the fetched
  land enters tapped (floor) and the fetch goes to the graveyard.
- Combat (end of turn, as today): every creature and token that entered before this turn
  attacks. Damage per attacker = printed power + counters + anthems + this turn's pumps.
  Attackers are assigned greedily, largest first, to the opponent with the most life left; drain
  effects hit every opponent (or one, per `each_opponent`). A game-level `damage_by_turn`
  records the turn's total.

### Play policy (general rules, in `MAIN_ORDER` terms)

- `return_lands` (mass return) is cast when the graveyard holds at least
  `[sim] mass_return_min_lands` lands (default 4) and a `landfall` effect source is on the
  battlefield; or unconditionally on the last two turns. Otherwise held.
- `pump` is cast only if this turn's projected damage with it kills the table or the last
  living opponent... (builder: define "makes lethal"); otherwise held. Anthems are permanents
  and follow the normal role order.
- `reanimate` is cast when the graveyard holds a creature with MV ≥ `threat_mv` or power ≥
  `[sim] reanimate_min_power` (default 4); target = highest MV. Victimize-style sacrifice costs
  are paid with the lowest-power creature or a token.
- `chain_lands_from_hand` on ETB plays every land in hand tapped, firing landfall for each; with
  a dredge source on the battlefield the chain also dredges between lands, bounded by the lands
  in the graveyard. Cap chain length at `[sim] chain_cap` (default 20) for runtime.
- `extra_land` sources raise `land_drops` while on the battlefield.
- Ramp spells (`ramp_spell` role) put as many lands onto the battlefield as their oracle text
  says (`two basic land cards` → 2; Harrow, Springbloom Druid, Entish Restoration), each through
  `_land_entered` so landfall fires per land. Today's `_fetch_land` puts exactly one; that count
  is read from the text in stage 1. "One onto the battlefield and one into your hand"
  (Cultivate, Kodama's Reach) puts the second land in hand from stage 1 as well; it is just a
  card added to the hand.
- `upkeep sacrifice_land` sacrifices the lowest-priority land (not the only one of a needed
  colour); if no land, the permanent is sacrificed, as the card says.

### Clocks and diagnostics (`sim/__init__.py`, `GameRecord`)

- New clocks: `lethal_table` (all three opponents at 0 by combat or drain), `win` =
  min(`lethal_table`, `lethal_combo`), `reanimate` (first creature returned from graveyard to
  battlefield). The existing `combat` clock keeps its name and its meaning (cumulative 40
  unblocked damage to a single focused opponent, today's `self.damage >= 40` counter) so it
  stays comparable with sim-v2 rows in the calibration table; it is a separate counter from the
  three greedy-assigned life totals, not derived from them.
- `[sim]` config: `lethal_damage` becomes `life_per_opponent = 40` and `opponents = 3`.
- Per-turn averages added next to `mana_by_turn` / `idle_by_turn`: `damage_by_turn`,
  `board_power_by_turn`, `lands_by_turn`, `graveyard_lands_by_turn`, and
  `tokens_by_turn: dict[type, dict[turn, float]]` (one row per token type seen, e.g. Zombie,
  Plant). `max_swing`: median across games of the largest single-turn damage.
- Report: the clock table gains the `win` row first, with `median` and a new `fast` column (5th
  percentile) for every clock. A `tokens on board` row per type. `damage this turn` and
  `board power` rows. `coverage:` line gains `unmodelled: N (names…)`.
- JSON: every new number, plus `effects_sources: {table: [...], pattern: [...], none: [...]}`.
- Narrative findings: `[win]` "Median win T9, fast games T6, via combat in 80% / combo in 20%";
  `[coverage]` when `unmodelled / nonland ≥ [narrative] unmodelled_share` (default 0.25):
  "N of M nonland cards have no modelled effect; every clock is a floor and the deck is not
  comparable with a well-covered list". The existing `[idle]` finding is kept.

### What "unmodelled" means

A nonland, non-token card is **unmodelled** when it has no effect the engine applies: its Forge
script has lines the reader did not turn into an effect or mana behaviour and none it did, or
every effect read is one the engine never applies (stage 1: an instant/sorcery `cast` effect
other than pump), and the table has no entry for it. A card with no script (404) is unmodelled
unless the table covers it. Instants and sorceries with no effect are `held` as today and count
as unmodelled. Vanilla creatures are modelled (they attack).

A card is **partial** when some effect is read and applied but some line, mode, branch or
non-pump spell effect is not. Partial cards are listed separately in the report (`partial:`)
and are not in the unmodelled count. (Amended at stage 1, ruling R1.)

## Stages

Each stage is its own plan, its own sim version and golden re-baseline, and leaves the suite
green. Stage boundaries were agreed with the user.

### Stage 1 — board and damage (sim v3)

Effects module with `token`, `counters`, `anthem`, `pump`, `mana`, `drain` on `landfall`, `etb`,
`creature_etb`, `static`, `cast`; tokens as permanents; three opponents and the `lethal_table`,
`win`, `first_opponent` clocks; fast-games column; per-turn diagnostics; coverage finding;
Necrobloom fixture frozen and pinned. Lands still one per turn, no graveyard. The Necrobloom
clock moves a little (Plant/Zombie per natural land drop); token decks in general move a lot.

### Stage 2 — graveyard and lands (sim v4)

Graveyard zone; instants/sorceries to graveyard; `mill`, `dredge`, `extra_land`,
`play_lands_from_graveyard`, `return_lands`, `return_lands_to_hand`, `fetch`, `sacrifice_land`,
`chain_lands_from_hand`, `upkeep` trigger, distinct-land condition. The Necrobloom engine comes
alive here; this is the stage to compare against the primer's description of a good game.

### Stage 3 — reanimation and draw engines (sim v5)

`reanimate`, `land_milled` trigger, `dies` trigger (World Shaper), `draw` on triggers, the
`reanimate` clock. Graveyard-filling from stage 2 is the prerequisite.

## Testing

- `tests/test_sim_effects.py`: one positive and one negative per script shape, with Forge
  script text pasted from the pinned commit (The Necrobloom, Avenger of Zendikar, Rampaging
  Baloths, Felidar Retreat, Scute Swarm, Intangible Virtue, Overrun, Lotus Cobra, Retreat to
  Hagra; stage 2: Life from the Loam, Azusa, Ramunap Excavator, Splendid Reclamation, Harrow,
  Evolving Wilds, Horizon Canopy; stage 3: Dread Return, The Gitrog Monster; negatives: an
  opponent's-land trigger, Mirkwood Bats, Six — attack-triggered mill is outside the vocabulary
  and must come out unmodelled).
- `tests/test_forge.py`: slug mapping for the names above, cache hit/miss, 404 → `None`,
  unreachable → `ForgeError`.
- `tests/test_sim_engine.py`: synthetic decks per mechanic: a landfall token maker plus lands
  gives N tokens by turn N+1 and they attack from the next turn; the Zombie threshold flips at
  seven distinct names and not with seven Forests; dredge replaces the draw only when the hand
  lacks a land; mass return fires only with a landfall source out; a pump is held until lethal;
  greedy assignment kills three opponents from 120 cumulative only when the swing shape allows;
  determinism (two runs equal).
- `tests/test_golden.py`: six fixtures (five existing plus `necrobloom-v3`), re-baselined per
  stage. Expectation to check by hand at stage 2, from the owner: an uncontested Bracket-3 deck
  wins around T6–T8, so Necrobloom's `win` median should land there; a median before T6 is a
  Bracket-4 hint (and the fixture is Bracket 3 by construction), so a faster number means
  something is counting twice, not that the deck is better than thought. The same rule of thumb
  becomes a `[win]` narrative line: "median win TN: typical of Bracket 3 (T6–T8)" / "earlier
  than Bracket 3 decks usually close (T6)"; it never sets a bracket floor.
- `tests/test_report.py` / `test_narrative.py`: the new rows and findings render and are present
  in the JSON.

## Calibration

After each stage, run all six fixture decks at 20 000 games and record `win` median and fast in
the calibration table (the eldrazi repo's `edhpower/CALIBRATION.md` columns, or a new
`CALIBRATION.md` in this repo if that file does not exist here — builder to check). The
Necrobloom benchmark goes in `~/github/necrobloom-deck/v3/` next to the decklist, as the
eldrazi repo does with its `*-benchmarks.md`.

## Calls made by the author (not decided with the user)

- Fast-games figure is the 5th percentile, matching scrollvault's "ceiling" so the two can be
  compared by hand.
- Three life totals with greedy largest-first assignment, rather than "cumulative ≥ 120", so a
  single huge creature cannot kill three players in one swing.
- Fetched lands enter tapped; fetches are cracked immediately.
- Dredge only when the hand lacks a land for this turn's drops; never on the opening hand.
- Mass return threshold 4 lands and a landfall source on board; cast anyway on the last two
  turns.
- Pumps held for a lethal swing; anthems cast on curve.
- One sim version per stage.
- The Necrobloom v3 list becomes a golden fixture.
- `kind` in `special_behaviours.toml` becomes optional when `effects` is present.
- Forge scripts are fetched live at a pinned commit and stored in the facts, not vendored;
  the repo stays MIT (user's choice 2026-10-21, with "fetch live" preferred over keeping a
  local index current).

## Left to the builder

- The exact regexes and how they split faces, in the style of `payoffs.py`.
- Whether `payoffs.py` and `effects.py` share one pattern source (they must not disagree).
- Representation details: `Perm.counters`, the synthetic token `SimCard`, how `effects` ride
  on `SimCard` without breaking `asdict`/JSON.
- `_land_priority` extensions for fetches and horizon lands.
- Order of simultaneous landfall triggers (does not change any number here).
- Where the primer's unmodelled interactions are listed in the report (a `not modelled:` line
  per stage is enough).
