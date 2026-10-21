# edhpower

Commander (EDH) deck power analysis. Given a decklist, reports mana-curve statistics,
a functional profile of the deck built from Scryfall oracle tags, detected combos
(Commander Spellbook), two power scores side by side, a tipping-point estimate, the
official WotC minimum bracket with the cards that trigger each criterion, a seeded
goldfish simulation with a win clock (table lethal or lethal combo) plus commander, mana,
threat, combat and combo clocks, and a findings block that reads those numbers back.

## Install

Not on PyPI yet; install straight from GitHub with [uv](https://docs.astral.sh/uv/):

    # run once without installing
    uvx --from git+https://github.com/aurelio-amerio/edhpower edhpower path/to/decklist.txt

    # or install the `edhpower` command permanently
    uv tool install git+https://github.com/aurelio-amerio/edhpower

From a clone, `uv run edhpower ...` and `uv run pytest -q` work directly.

## Usage

    uv run edhpower path/to/decklist.txt --json out.json

Options: `--commander NAME` (repeatable), `--json PATH`, `--facts-json PATH`,
`--from-facts PATH` (offline replay), `--allow-unresolved`, `--no-combos`, `--no-tags`,
`--refresh-tags`, `--no-forge`, `--cache-dir DIR`, `--iterations N` (default 20 000), `--no-sim`.

Exit codes: 0 ok · 1 usage/parse error (including no commander identified) · 2 unresolved card names · 3 a data source was unreachable or misconfigured.

## Decklist formats

- Plain: `1 Card Name` per line, `//` comments. The commander is the first line if it is
  followed by a blank line, or the entry after a `// Commander` comment. If no commander
  can be identified the run aborts; pass `--commander NAME` (repeatable for partners).
- Archidekt export: `1x Card Name (set) 123 [Category]`; `[Commander]` marks the commander.
- JSON: `{"commanders": ["..."], "main": [{"name": "...", "count": 1}]}`.

Double-faced cards may be written as `Front // Back` or just `Front`.

## What the report contains

- **Mana curve** — histogram, average and median MV of the non-land cards, pip counts, prices.
- **Game Changers and combos** — Spellbook lines with their bracket tag, speed and whether
  the line is definitely two cards.
- **Functional profile** — lands (by mana produced), fast mana, rocks, dorks, land ramp,
  rituals, cost reducers, tutors, interaction, card advantage, stax, creatures; the
  `special_behaviours` hits; and the untagged cards.
- **Power** — the two scores (below).
- **Tipping point** — the turn the deck is expected to reach its functional average mana value.
- **Bracket** — the minimum bracket implied by the official criteria, with the triggering cards.
- **Goldfish simulation** — the clock table: the `win` row first, then median turn, the `fast`
  column (the turn reached by the fastest 5% of games) and cumulative share by turn for each
  clock; board rows per turn (average mana, share of games casting nothing, damage this turn,
  board power, lands on battlefield, one `tokens: <type>` row per token type); the win route
  (combat / combo / none) and the biggest single-turn swing; which Spellbook lines were
  simulated and which were not and why; model coverage and the `effects:` line (how many cards'
  effects came from the table and from Forge, which cards are unmodelled and which are partial).
- **Findings** — bracket triggers, weakest components, scorer agreement, the win clock, a
  coverage warning when much of the deck is unmodelled, closed-form vs simulated tipping, idle
  window, combo summary, clock medians.
- **Data freshness** — cache ages and staleness warnings.

## The two power scores

They are reported side by side and never blended:

- **Curve model** — a faithful port of edhpowerlevel.com's published model: each card's impact
  is derived from its mana value, USD price and EDHREC rank, and the deck's power is
  `total impact × efficiency`. Because it is faithful, a difference against the site is
  attributable (price vendor, printing, rank drift, the site's own override list). It needs
  USD prices; cards without one are counted in `missing_price`.
- **Component model** — six capped components taken from the functional profile: fast mana,
  tutors, interaction, card advantage, combos, curve (which folds in ramp), each scaled against
  a cap and weighted. `stax` is not a component; it only feeds the informational archetype guess.
  Caps, weights and the tipping constants live in `src/edhpower/data/scoring.toml`; the file
  carries a `config_version` and named profiles, and the active profile names are stamped
  into every JSON output. The reported `archetype` is informational only.

The **tipping point** is a stated heuristic, not a simulation: the deck's functional average
mana value (clamped to 2–6 mana) versus a closed-form estimate of available mana per turn,
including land classes, fast mana and ramp (from turn 3), reported as the first turn whose
probability crosses 0.8. The goldfish simulation is the headline; the closed-form number is
kept as a cross-check and the findings block compares the two.

## The goldfish simulation

The simulation is seeded from the resolved decklist (the seed is a hash of the sorted
`(canonical name, count)` pairs, so reordering or commenting the decklist does not change a
single number — the seed is printed in the report). Each game is played on the play, with one
London mulligan for hands outside 2–5 lands, and no opponent. Colours are enforced in every
payment.

What is modelled comes from each card's `CardProfile`: lands by class, mana rocks, mana dorks,
one-shot mana (rituals and sacrifice sources), cost reducers with their scope, tutors digging
for combo pieces, land-ramp and draw spells, and the `special_behaviours` params — Monolith-style
untap engines, metalcraft, tron lands, creature-scaled lands, mana doublers, and City of
Traitors-style sacrifice-on-land-drop.

The combo model plays 2- and 3-card Spellbook `included` lines that carry no template — each
piece not yet on the battlefield is cast for its own parsed mana cost, with colours enforced and
board cost reductions applied, and Spellbook's `manaValueNeeded` is then paid as generic mana on
top (falling back to `parse_cost(manaNeeded)` when that field is not an integer). At most 8 two-
card and 6 three-card lines are simulated (`max_two_card_lines` / `max_three_card_lines` in
`scoring.toml`), most popular first; lines beyond those caps, and templated lines, are reported
as *not simulated* and never assumed to resolve — those caps are why a deck with 17 `included`
lines simulates 9 of them.

Card effects beyond mana — tokens, landfall and enters triggers, +1/+1 counters, anthems, pump
spells, drain — are read from each card's Card-Forge script (see *Data sources*). The reader
(`sim/effects.py`) understands a fixed vocabulary of script lines and nothing else: a card none
of whose lines it reads is **unmodelled**, a card with some lines read and some skipped is
**partial**, so coverage is exact rather than heuristic. The `special_behaviours` table
overrides a card's script where an entry carries `effects`. Tokens attack from the turn after
they enter; there are no blockers and no haste.

The table has three opponents at 40 life each (`opponents`, `life_per_opponent` in
`scoring.toml`); attackers are assigned greedily to the opponent with the most life, and drain
hits every opponent (or the one with the most life, when the script names one opponent). Each clock (`engine.CLOCKS`) reports a median turn, a `fast` turn and a
by-turn cumulative share:

- `win` — the first turn of `lethal_table` or `lethal_combo`: the headline comparison number.
- `lethal_table` — every opponent at 0 from combat and drain; `first_opponent` — the first one.
- `commander`, `mana_threshold`, `tipping_target`, `threat` — as in sim v2.
- `combat` — 40 cumulative combat damage to one opponent, counting effective power (printed
  power, counters, anthems, tokens and pumps cast for lethal); kept for comparison with sim v2
  rows, which counted printed power only.
- `combo`, `lethal_combo` — a simulated Spellbook line assembled (with a detected payoff, for
  the lethal one).

A game that never reaches a clock counts as turn 13 for the median; a clock is printed as `>T12`
when fewer than half of games reach it by turn 12. `fast` is the turn by which 5% of games have
reached the clock (the 5th percentile, comparable with scrollvault's "ceiling").

Known limits of sim v3 (each a source of systematic bias, not noise; the report's `note:` lines
add the effect-model simplifications):

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
- Combo payoffs are detected by oracle-text patterns (plus the `mana-sink` and
  `alternate-win-condition` tags for two categories). A payoff the patterns miss makes a real
  win read as "no payoff in deck"; the report lists what was detected so the gap is visible.

`[sim]` in `src/edhpower/data/scoring.toml` holds the simulator's tuning constants; `sim_version`
is stamped into the JSON alongside `config_version`. Golden tests run the simulator at 500 games;
production defaults to 20 000 (`--iterations` overrides either). sim v2 (2026-10-18) gates the lethal-combo clock on a detected payoff and drops lock-only lines from the combo clock; v1 and v2 combo numbers are not comparable. sim v3 (2026-10-21) adds Forge-read effects, tokens and triggers, three opponents and the `win`, `lethal_table` and `first_opponent` clocks; its `combat` clock counts tokens, counters, anthems and pumps, so a v3 combat median can be earlier than the v2 one for a token deck.

## Data sources and caching

- **Scryfall** for card data — `<cache-dir>/cards.jsonl`, one JSON line per card, each stamped
  with its own fetch date. Cards older than **7 days** raise a staleness warning, because
  prices, EDHREC ranks and Game Changer flags drift.
- **Scryfall oracle tags** for the functional profile — `<cache-dir>/tags/<slug>.json`, one file
  per slug (about 21 slugs, ~150 paged requests at 1 request/second on the first run, a few
  minutes). Subsequent runs read the cache. `--refresh-tags` refetches everything;
  `--no-tags` skips it, which makes the component score and the bracket `tutors` criterion
  `unevaluated` rather than zero. A tag cache older than **30 days** raises a staleness
  warning. A slug Scryfall does not recognise is a configuration error and aborts the run;
  it never becomes an empty tag set.
- **Card-Forge scripts** for card effects — one script per card, fetched from
  `raw.githubusercontent.com/Card-Forge/forge/<commit>/forge-gui/res/cardsfolder/<initial>/<slug>.txt`
  at the commit pinned in `scoring.toml` (`[forge] commit`), and cached as text under
  `<cache-dir>/forge/<commit>/<slug>.txt`; a new pin starts a new cache directory. A 404 is
  recorded as "no script", not an error. The script text is stored in the `DeckFacts`, so
  `--from-facts` stays offline. `--no-forge` skips the fetch; Forge unreachable degrades the
  same way: effects come from the behaviours table only, a note says so, and the curve and
  component scores are untouched.
- **Commander Spellbook** for combo lines and bracket flags (not cached; skipped with `--no-combos`).
- Game Changer membership comes from Scryfall's `game_changer` field, cross-checked with Spellbook.
- Spellbook does not report card names it fails to recognise (its bracket echo lists only a
  subset of the cards sent, not just flagged ones), so edhpower always sends Scryfall's canonical
  names and cannot detect a silently ignored card.

The cache directory is `$EDHPOWER_CACHE_DIR`, `--cache-dir`, or `~/.cache/edhpower`.

`src/edhpower/data/special_behaviours.toml` is a small explicit table for cards whose text the
generic extractor cannot read correctly (Ancient Tomb, Eldrazi Temple, Eye of Ugin, Gaea's Cradle,
Urza lands, Forsaken Monument, the untap engines). Every hit is listed in the report, so the
table's effect on a given deck is always visible.

The bracket is a **minimum** implied by the official deckbuilding criteria; Brackets 1 and 5
are self-declared. Criteria that cannot be evaluated (e.g. Spellbook unreachable, tags skipped)
are reported as `unevaluated`, never assumed satisfied.

## Offline replay, fixtures and calibration

`--facts-json PATH` writes the `DeckFacts` — every external input, with provenance — and
`--from-facts PATH` re-runs the whole analysis from it with no network. `DeckFacts` is at
**schema version 3** (version 3 carries each card's Forge script); `--from-facts` rejects any other version rather than guessing.

`tests/fixtures/*.facts.json` are frozen live runs of six sample Commander decks spanning
brackets 2 to 5 (a precon, two tuned bracket-3 lists, a bracket-4 list, a bracket-5 contrast and
`necrobloom-v3`, a bracket-3 lands-and-tokens list whose effects all come from Forge);
their decklists are under `tests/fixtures/decks/`, and the package reads nothing outside the
fixtures. `tests/test_golden.py` pins the analysis numbers for those fixtures,
including the simulator's medians at 500 games, so changing a scoring constant or the sim
engine fails the suite until the values are re-baselined on purpose:

    uv run python tests/golden_update.py

`CALIBRATION.md` records the simulator's reference numbers per fixture, sim version and date
(at 20 000 games).
