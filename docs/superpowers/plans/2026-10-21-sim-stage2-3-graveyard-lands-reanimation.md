# Sim stages 2 and 3: graveyard, lands, reanimation (sim v4, v5) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The goldfish simulator gains a graveyard zone and the land engine built on it (mill, dredge, extra land drops, lands played from the graveyard, mass land return, fetch lands, self-sacrificing lands, upkeep land sacrifice, Cultivator-style chains) in stage 2 (sim v4), then reanimation, land-milled and dies triggers, triggered draw and a `reanimate` clock in stage 3 (sim v5); the Necrobloom fixture's `win` median is checked by hand against the spec's Bracket-3 window after each stage.

**Architecture:** `sim/effects.py` extends the Forge vocabulary with the new triggers and actions and gains an activation-cost field; `sim/mana.py` parses activation costs; `sim/model.py` gives effect-bearing instants and sorceries a `spell` role; `sim/engine.py` adds the graveyard, a land step that plays several lands from hand or graveyard, a draw step that may dredge, upkeep triggers, activated abilities paid from leftover mana, and per-action play policies; `sim/__init__.py`, report and config carry the new rows, notes and constants. Two sim-version bumps, two golden re-baselines. No card names in `sim/`.

**Tech Stack:** Python 3.12, dataclasses, `re`, `tomllib`; pytest via `uv run pytest -q` from the repo root (`uv` must run outside the sandbox, see the stage 1 ledger).

**Spec:** `docs/superpowers/specs/2026-10-20-board-graveyard-sim-design.md` (stages 2 and 3, the Effects, Zones, Play policy and Clocks sections, the Forge source section). Stage 1 plan and its rulings ledger: `docs/superpowers/plans/2026-10-21-sim-stage1-board-and-damage.md`, `.superpowers/sdd/2026-10-21-sim-stage1-board-and-damage/progress.md` (R1–R19).

## Global Constraints

- No card names in `src/edhpower/sim/`; per-card knowledge lives in `src/edhpower/data/special_behaviours.toml` and every table-sourced card is listed in the report.
- Forge scripts are read from `FactEntry.forge_script` (schema 3, unchanged); fixtures are not re-frozen in either stage. Script excerpts in tests are pasted verbatim from commit `33aecdd6adac36a42af9eab75d2e654626a0e7db` (the fixture facts hold them; `tests/test_sim_effects.py` already has the stage 1 constants).
- `[sim] version` becomes 4 at the end of stage 2 (Task 6) and 5 at the end of stage 3 (Task 9); goldens re-baselined once per stage with `uv run python tests/golden_update.py`; the `golden_for` key set is unchanged.
- Determinism: same decklist and iteration count → same numbers.
- Every simplification makes the clock later, never earlier, and is a `note:` in the sim block: lands returned from the graveyard enter tapped; fetched lands enter tapped and are 1-mana lands; lands entering together enter one at a time (a distinct-names condition sees the earlier ones only); a draw granted by a trigger is a plain draw (never a dredge); no maximum hand size.
- The reader fails closed: every `T:`/`A:`/`S:`/`K:`/`R:` line, sub-ability, cost part or count it does not understand goes to `unread`; stage 1's rules (R9 keywords, Unless/Condition keys, Charm/Branch) stay.
- TDD: failing test first in every task; `uv run pytest -q` green before every commit; commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Runtime: 20 000 games on the Necrobloom fixture under 2 minutes.
- Open user decisions from stage 1 (memory note `sim-v3-open-decisions`): the GPL Forge scripts inside `tests/fixtures/*.facts.json` (R19) and the benchmark copy into `~/github/necrobloom-deck/v3/` (R15). Neither blocks this plan; this plan writes benchmark blocks into `CALIBRATION.md` and leaves the other-repo copy to the user.

## Review Focus

1. A dredge with fewer cards in the library than its number must draw instead (rules 702.52), never deck or crash — test in Task 5.
2. A free fetch land replayed from the graveyard (play-from-graveyard source on board) must use one land drop per replay, so the loop is bounded by `land_drops` — test in Task 4.
3. An upkeep land sacrifice with no land on the battlefield sacrifices the permanent itself, and a land sacrifice never strands the last source of a colour the hand needs — test in Task 4.
4. A milled-lands-to-battlefield trigger (stage 3) returns exactly the lands of that mill, once, even when the mill was caused by a dredge — test in Task 8.
5. A reanimation spell with a sacrifice cost is not cast when nothing can be sacrificed, and never sacrifices the only creature it would bring back value with (a token first) — test in Task 8.

---

## Stage 2 — graveyard and lands (sim v4)

### Task 1: Effects vocabulary — stage 2 triggers, actions, activation costs, table entries

**Files:**
- Modify: `src/edhpower/sim/effects.py`, `src/edhpower/sim/mana.py`, `src/edhpower/data/special_behaviours.toml`
- Test: `tests/test_sim_effects.py`, `tests/test_sim_mana.py`, `tests/test_profile.py`

**Interfaces:**
- Produces:
  ```python
  # sim/mana.py
  @dataclass(frozen=True)
  class ActivationCost:
      mana: ManaCost            # parse_cost of the mana parts ("3 G" -> "{3}{G}"); parse_cost("") when none
      tap: bool                 # "T"
      sacrifice_self: bool      # Sac<N/CARDNAME>
      sacrifice_lands: int      # Sac<N/Land>
      sacrifice_creatures: int  # Sac<N/Creature>  (stage 3 uses it; parsed from stage 2)
  def parse_activation_cost(text: str) -> ActivationCost   # space-separated Forge parts; PayLife<N> accepted and ignored (life is not a resource); any other part ("X", "Discard<…>", "AddCounter<…>", "Sac<1/Forest;Plains/…>", "Sac<1/Creature.Other/…>") -> ValueError naming the part

  # sim/effects.py
  TRIGGERS = ("landfall", "etb", "creature_etb", "token_created", "static", "cast", "activated", "upkeep", "land_sacrificed")
  ACTIONS = ("token", "counters", "anthem", "pump", "mana", "drain", "mill", "dredge", "extra_land",
             "play_lands_from_graveyard", "return_lands", "return_lands_to_hand", "fetch", "sacrifice_land",
             "chain_lands_from_hand")
  class Effect: ... cost: str = ""   # new, last field: activation or additional cost in Forge spelling ("3 G Sac<1/CARDNAME>"); "" = none
  # n: int | str — "lands" (stage 1), "all" (return_lands: every land card in the graveyard)
  # type: for dredge "" = this card has dredge n (K:Dredge), "lands" = land cards in your graveyard have dredge n
  #       (the spec's table example spells this `grants = "lands"`; it is written `type = "lands"`, the stage 1 scope field)
  class CardEffects: ... land_search: bool = False   # the reader found a library→battlefield/hand land search (ramp fields are meaningful)
  ```
- Reader vocabulary added (everything else stays unread):
  - `S:Mode$ Continuous | Affected$ You | AdjustLandPlays$ N` → `Effect("static", "extra_land", N)`.
  - `S:Mode$ Continuous | Affected$ Land.YouOwn|Land.YouCtrl | MayPlay$ True | AffectedZone$ Graveyard` → `Effect("static", "play_lands_from_graveyard")`. `Affected$ Land.TopLibrary+YouCtrl | AffectedZone$ Library` stays unread; a static whose only non-frame key is `MayLookAt` is ignorable.
  - `K:Dredge:N` → `Effect("static", "dredge", N)`; `S:Mode$ Continuous | AffectedZone$ Graveyard | Affected$ Land.YouOwn | AddKeyword$ Dredge:N` → `Effect("static", "dredge", N, type="lands")`.
  - `ChangeZoneAll | ChangeType$ Land.YouCtrl|Land.YouOwn | Origin$ Graveyard | Destination$ Battlefield` (any of `SP$`/`DB$`/`AB$`, `Tapped$` ignored) → `Effect(on, "return_lands", "all")`.
  - `ChangeZone | Origin$ Graveyard | Destination$ Battlefield | ValidTgts$ Land.YouCtrl|Land.YouOwn` → `Effect(on, "return_lands", TargetMax or 1)`.
  - `ChangeZone | Origin$ Graveyard | Destination$ Hand | ValidTgts$ Land.YouCtrl|Land.YouOwn | TargetMax$ N` → `Effect(on, "return_lands_to_hand", N)`; `ValidTgts$ Card.YouCtrl` (any card) stays unread.
  - `DB$ Mill | Defined$ You | NumCards$ N` → `Effect(on, "mill", N)`; `Optional$ True` is accepted (the goldfish always mills).
  - Land search outside `A:SP$` (today's `_ramp`): `A:AB$ ChangeZone | Cost$ C | Origin$ Library | Destination$ Battlefield | ChangeType$ <land types>` → `Effect("activated", "fetch", n, cost=C)`; the same shape as a trigger's execute (`AB$`/`DB$ ChangeZone` with an optional `Cost$`) → `Effect(<trigger>, "fetch", n, cost=C)`. `n` = `ChangeNum$` (default 1); `ChangeType$ EACH A & B` → number of `&` parts; `ChangeType$ Land` (any land) is accepted (the engine still finds a 1-mana land). `Cost$` must parse with `parse_activation_cost` (so `PayLife<1>` fetches read; `Sac<1/Forest;Plains/…>` does not); a mana part in a **triggered** fetch's cost → unread.
  - `_ramp` extensions for `A:SP$`: a first step `SP$ Sacrifice | Defined$ You | SacValid$ Land` counts one sacrificed land (Roiling Regrowth, Entish Restoration); `ChangeNum$ X` with `SVar:X:Count$Compare <Y> GE<k>.<a>.<b>` → `min(a, b)` and an unread line `"ChangeNum$ X read as <min>"` (the floor); any other non-integer `ChangeNum$` → not a ramp (unread), never 0; a `Destination$ Hand` step counts only with `Origin$ Library`. `CardEffects.land_search = True` when `_ramp` found a search.
  - `T:Mode$ Phase | Phase$ Upkeep | ValidPlayer$ You | TriggerZones$ Battlefield | Execute$ X` → trigger `upkeep` (`Phase`, `ValidPlayer` join `_TRIGGER_KEYS`). Execute `DB$ Sacrifice | UnlessPayer$ You | UnlessCost$ Sac<N/Land>` with no `Defined`/`SacValid` → `Effect("upkeep", "sacrifice_land", N)` (sacrifice N lands, else this permanent) — the one `Unless*` shape the reader accepts.
  - `T:Mode$ ChangesZone | Origin$ Battlefield | Destination$ Graveyard | ValidCard$ Land.YouCtrl | TriggerZones$ Battlefield` → trigger `land_sacrificed` (fires once per land of yours that goes from the battlefield to the graveyard).
  - `A:SP$ Effect | StaticAbilities$ X` where `SVar:X` is `Mode$ Continuous | Affected$ You | AdjustLandPlays$ N` → `Effect("cast", "extra_land", N)` (this turn); its `SubAbility$` chain is read as usual (`DB$ Draw` is unread until stage 3).
  - `A:AB$ Mana` stays skipped; `K:Cycling`, `K:TypeCycling` stay ignored.
- Table: `_TABLE_KEYS += {"cost"}`; `cost` must parse; `n = "all"` only with `do = "return_lands"`; `type = "lands"` only with `do = "dredge"`. New entry, exactly as the spec's example (the Repeat loop in its script is outside the vocabulary):
  ```toml
  [cards."Cultivator Colossus"]
  effects = [{ on = "etb", do = "chain_lands_from_hand" }]
  note = "puts every land in hand onto the battlefield tapped, drawing (or dredging) after each; the script's Repeat loop is outside the reader's vocabulary"
  ```
  Header comment lists the stage 2 triggers, actions and the `cost` key.

- [ ] **Step 1: Write failing tests** in `tests/test_sim_mana.py`: `test_parse_activation_cost` (`"3 G Sac<1/CARDNAME>"` → mana `parse_cost("{3}{G}")`, `sacrifice_self`; `"T PayLife<1> Sac<1/CARDNAME>"` → `tap`, `sacrifice_self`, mana `parse_cost("")`; `"Sac<1/Land>"` → `sacrifice_lands == 1`; `"2 T Sac<1/CARDNAME>"`; `""` → all empty); `test_parse_activation_cost_rejects_unknown` (`"X T"`, `"T Sac<1/Forest;Plains/Forest or Plains>"`, `"Discard<1/Card>"` → `ValueError` naming the part).
  In `tests/test_sim_effects.py`, new verbatim constants `LIFE_FROM_THE_LOAM`, `AZUSA`, `RAMUNAP_EXCAVATOR`, `SPLENDID_RECLAMATION`, `EVOLVING_WILDS`, `MYRIAD_LANDSCAPE`, `KROSAN_VERGE`, `WINDSWEPT_HEATH`, `AFTERMATH_ANALYST`, `GITROG`, `TITANIA`, `ROILING_REGROWTH`, `ENTISH_RESTORATION`, `SPRINGBLOOM_DRUID`, `SAKURA_TRIBE_ELDER`, `EXPLORE`, `ORACLE_OF_MUL_DAYA`, `ANCIENT_GREENWARDEN`, `EXPLORATION`, `CRUCIBLE_OF_WORLDS`, `THE_MENDING_OF_DOMINARIA`, `ETERNAL_WITNESS`, `KNIGHT_OF_THE_RELIQUARY`, `THALIA_AND_GITROG` (all in the Necrobloom fixture facts except Windswept Heath, Exploration and Crucible of Worlds, fetched from the pinned commit) and tests:
  - `test_loam_returns_lands_and_has_dredge`: effects `== (Effect("cast", "return_lands_to_hand", 3), Effect("static", "dredge", 3))`, `unread == ()`.
  - `test_extra_land_statics`: Azusa → `(Effect("static", "extra_land", 2),)`; Exploration → n 1; Oracle → `extra_land` 1 plus exactly one unread (the top-of-library `MayPlay` static), `partial`.
  - `test_play_lands_from_graveyard`: Ramunap and Crucible → `(Effect("static", "play_lands_from_graveyard"),)`, `unread == ()`; Greenwarden → the same effect plus the Panharmonicon static unread.
  - `test_mass_return`: Splendid → `(Effect("cast", "return_lands", "all"),)`; Aftermath Analyst → `(Effect("etb", "mill", 3), Effect("activated", "return_lands", "all", cost="3 G Sac<1/CARDNAME>"))`, `unread == ()`.
  - `test_fetch_lands`: Evolving Wilds → `(Effect("activated", "fetch", 1, cost="T Sac<1/CARDNAME>"),)`; Myriad → n 2, cost `"2 T Sac<1/CARDNAME>"`; Krosan Verge → n 2; Windswept Heath → cost `"T PayLife<1> Sac<1/CARDNAME>"`; all `unread == ()`.
  - `test_triggered_and_creature_fetches`: Springbloom → `(Effect("etb", "fetch", 2, cost="Sac<1/Land>"),)`; Sakura-Tribe Elder → `(Effect("activated", "fetch", 1, cost="Sac<1/CARDNAME>"),)`.
  - `test_ramp_with_sacrifice_step`: Roiling Regrowth → `ramp_to_battlefield == 2`, `ramp_sacrifice_lands == 1`, `land_search`, `effects == ()`; Entish → `(2, 0, 1)`, one unread mentioning `read as 2`; Harrow and Cultivate unchanged (`land_search` True); Loam and Splendid `land_search` False.
  - `test_gitrog_stage2`: `(Effect("upkeep", "sacrifice_land", 1), Effect("static", "extra_land", 1))`, `len(unread) == 1` (the ChangesZoneAll trigger), `partial`.
  - `test_titania`: `(Effect("etb", "return_lands", 1), Effect("land_sacrificed", "token", 1, 5, 3, "Elemental"))`.
  - `test_explore_stage2`: `(Effect("cast", "extra_land", 1),)` plus the `DBDraw` sub-ability unread, `partial`.
  - Negatives: Mending → `effects == ()`, unread non-empty (`K:Chapter`); Eternal Witness → `()`; Knight → `()` with both lines unread; Thalia and Gitrog → `extra_land` 1 only, `partial`; a hand-edited `AZUSA.replace("Affected$ You", "Affected$ Player")` → unread; a hand-edited Springbloom with `Cost$ 1 Sac<1/Land>` → unread (mana in a triggered cost).
  - Table: `parse_effects_table([{"on": "activated", "do": "return_lands", "n": "all", "cost": "3 G Sac<1/CARDNAME>"}])` round-trips; `n = "all"` with `do = "token"` → `ValueError`; `cost = "X"` → `ValueError`; `test_profile.py::test_colossus_table_entry` (`load_special_behaviours()["Cultivator Colossus"].effects == (Effect("etb", "chain_lands_from_hand"),)`, `kind is None`).
- [ ] **Step 2: Run** `uv run pytest tests/test_sim_effects.py tests/test_sim_mana.py tests/test_profile.py -q` — FAIL.
- [ ] **Step 3: Implement** `parse_activation_cost`, the vocabulary, `land_search`, the table checks and the entry.
- [ ] **Step 4: Run** `uv run pytest -q --deselect tests/test_golden.py` — PASS (`sim_unmodelled_count` goldens move because cards such as Azusa now carry effects; re-baselined in Task 6; the fixture agreement test is untouched).
- [ ] **Step 5: Commit** `feat(sim): stage 2 effects vocabulary — graveyard, land drops, fetches, upkeep; activation costs`.

---

### Task 2: Model — the `spell` role, every effect applied, coverage

**Files:**
- Modify: `src/edhpower/sim/model.py`, `src/edhpower/report.py:171` (coverage line)
- Test: `tests/test_sim_model.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `CardEffects.land_search`, `Effect.cost`.
- Produces:
  ```python
  ROLES += ("spell",)        # instant/sorcery whose cast effects the engine applies (not a pump-only spell)
  def _role(p, card, special, is_spell, tags_ok, cfg, fx: CardEffects) -> str
  ```
  Precedence (new rules in **bold**): land → engine/rock specials → dork/rock → one_shot → reducer → **ramp_spell: `land-ramp` tag, `is_spell`, `fx.land_search`** → **draw_spell: `draw_count > 0`, `is_spell`, no applied non-pump cast effect** → tutor → threat → creature → **spell: `is_spell` and any `cast` effect with `do != "pump"`** → held → permanent. `applied_by_engine` is deleted: stage 2 applies every effect (`cast draw` does not exist yet). `unmodelled` = `source != "table" and not effects and not land_search and (unread or source == "none")`; `partial` = `(effects or land_search) and unread`. `never_cast` counts `held` spells only (unchanged). Coverage dict gains `"spell": 0`; report coverage line gains `· spells {cov['spell']}` before `held`.

- [ ] **Step 1: Write failing tests**: `test_spell_role_for_effect_bearing_spells` (Loam script → role `spell`, not `draw_spell` although `draw_count` is 1; Splendid with a `land-ramp` tag → `spell`, not `ramp_spell`; Harrow with the tag → `ramp_spell`; Overrun → `held`); `test_cast_effects_are_modelled_now` (rewrite `test_spell_with_only_non_pump_cast_effects_is_unmodelled`: `Cast Tokens`, `Cast Drain`, `Token Trinket` are **not** unmodelled and have role `spell`; `Pump And Token` is `spell`, Overrun stays `held`; the never-cast note is absent because no held spell without a pump remains); `test_entish_is_partial_not_unmodelled` (ramp found + unread); `test_report_coverage_line_has_spells`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q --deselect tests/test_golden.py` — PASS (goldens move: unmodelled counts drop; re-baselined in Task 6).
- [ ] **Step 5: Commit** `feat(sim): spell role for effect-bearing instants and sorceries; every read effect is applied`.

---

### Task 3: Engine — graveyard zone, sacrifice, mill, cast effects on resolution, spell policies, mass return

**Files:**
- Modify: `src/edhpower/sim/engine.py`, `src/edhpower/config.py`, `src/edhpower/data/scoring.toml`
- Test: `tests/test_sim_engine.py`, `tests/test_config.py`

**Interfaces:**
- Config: `[sim] mass_return_min_lands = 4` → `SimConfig.mass_return_min_lands: int` (version stays 3 until Task 6).
- Produces (on `Game`):
  ```python
  self.graveyard: list[str]
  def _gy_lands(self) -> list[str]                       # land names in the graveyard
  def _to_graveyard(self, name: str) -> None
  def _sacrifice(self, perm: Perm) -> None               # board → graveyard; a land also runs _lands_left() and fires land_sacrificed effects of every other board permanent
  def _sacrifice_lands(self, n: int) -> int               # as today's choice rule, each victim through _sacrifice; returns how many went
  def _mill(self, n: int) -> list[str]                    # top n (library.pop(), like _draw) → graveyard; returns the names
  def _put_land(self, name: str, tapped: bool, zone: str) -> Perm   # zone ∈ "hand" | "graveyard" | "library"; removes from it, appends the Perm, _land_entered
  def _return_lands(self, n: int | str) -> int            # graveyard lands → battlefield tapped, best _land_priority first, "all" = every one; returns how many
  def _return_lands_to_hand(self, n: int) -> int
  def _spell_wanted(self, c: SimCard) -> bool
  def _pay_additional(self, cost: ActivationCost, source: Perm | None) -> bool   # the non-mana parts of a triggered effect's cost: sacrifice lands (via _sacrifice_lands) and self; False when they cannot be paid, and then nothing is sacrificed
  ```
  `MAIN_ORDER` inserts `"spell"` after `"ramp_spell"`; `CHEAPEST_FIRST` gains `"spell"`. `_try_role("spell")` = `_castable("spell")` filtered by `_spell_wanted`, first one cast.
  `_resolve`: a spell of any role (`c.is_spell`) ends in the graveyard. Order inside `_resolve` for spells: role work as today (`one_shot` mana, `ramp_spell` search, `draw_spell` draw), then every `cast` effect with `do != "pump"` fired with `source=None`, then `_to_graveyard(name)`. Pumps keep firing only from `_try_pump`.
  `_fire` additions: `mill` → `_mill(n)`; `return_lands` → `_return_lands(n)`; `return_lands_to_hand`; `fetch` → `_pay_additional(parse_activation_cost(e.cost), source)` then `_fetch_land()` × n (skip the effect when the cost cannot be paid); `token`/`counters`/… unchanged. `_fire(effect, source)` keeps its signature; `source` is used by `_pay_additional` (`sacrifice_self`) and by `sacrifice_land` in Task 4.
  Policies (`_spell_wanted`, true when any applied non-pump cast effect of the card says so):
  - `return_lands`: `len(_gy_lands()) >= 1` and (`len(_gy_lands()) >= cfg.mass_return_min_lands` and `_triggered("landfall")` non-empty, or `turn >= cfg.max_turn - 1`).
  - `return_lands_to_hand`: `_gy_lands()` non-empty and the hand holds fewer lands than next turn's drops (`1 + Σ static extra_land on board`).
  - `mill`: always.
  - `extra_land`: added in Task 4 with the land-drop fields.
  - `fetch` (cast, none in the vocabulary) and `chain_lands_from_hand`: never a cast policy.
  `_sacrifice_lands` keeps the "do not strand a wanted colour" rule and now also skips a land whose `activated fetch` is still crackable when another land qualifies (a fetch is worth two landfalls).

- [ ] **Step 1: Write failing tests** (synthetic cards through `_fx_deck`/`_staged`; scripts from Task 1's constants; `SPLENDID_C`, `LOAM_C`, `ANALYST_C`, `TITANIA_C` card dicts as in stage 1): `test_config_mass_return_min_lands`; `test_resolved_spells_go_to_the_graveyard` (a `held`-free deck: Harrow resolved → `"Harrow" in g.graveyard`, the sacrificed land too); `test_sacrificed_land_fires_land_sacrificed` (Titania on board, Harrow cast → one Elemental token and the land in the graveyard); `test_mill_fills_the_graveyard_from_the_top` (Aftermath Analyst resolved → the three top library cards are the graveyard, in order); `test_mass_return_waits_for_four_lands_and_a_landfall_source` (Splendid in hand, 6 mana: 3 lands in graveyard + Baloths → not cast; 4 lands + Baloths → cast, 4 Beasts, lands tapped, Splendid in graveyard; 4 lands, no landfall source, turn 5 → not cast; turn `max_turn - 1` → cast); `test_return_lands_picks_best_priority_first` (Titania etb with a Forest and a tapped-entering dual in the graveyard, hand needing the dual's colour → the dual comes back); `test_loam_returns_three_lands_when_the_hand_lacks_one` (hand without a land, 4 lands in graveyard → 3 lands in hand, Loam in graveyard; hand with a land → held); `test_cast_effects_fire_on_resolution` (reuse stage 1's `CAST_TOKENS` script: resolving it makes its tokens); `test_triggered_fetch_pays_its_land_cost` (Springbloom with 2 lands on board → one sacrificed, two fetched tapped, 3 lands; with no land on board → nothing fetched, Druid still enters).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q --deselect tests/test_golden.py` — PASS.
- [ ] **Step 5: Commit** `feat(sim): graveyard zone, sacrifice and mill, cast effects on resolution, mass land return and land recursion policies`.

---

### Task 4: Engine — land drops, lands from the graveyard, fetch lands, activated abilities, upkeep

**Files:**
- Modify: `src/edhpower/sim/engine.py`
- Test: `tests/test_sim_engine.py`

**Interfaces:**
- Produces (on `Game`):
  ```python
  self.land_drops: int        # this turn: 1 + Σ n of static extra_land effects on the board at the land step, + cast extra_land this turn
  self.lands_played: int      # this turn
  def _land_step(self) -> None             # replaces _play_land: while lands_played < land_drops: a land from hand (today's priority), else from the graveyard when a play_lands_from_graveyard source is on the board (same priority), else stop; each via _put_land(…, tapped=card.enters_tapped, zone); then _crack_free_fetches()
  def _crack_free_fetches(self) -> None    # every untapped board land with an activated fetch whose cost has no mana and no creature sacrifice: _activate(perm, effect); repeat until none
  def _activate(self, perm: Perm, e: Effect) -> bool   # pay cost.mana from the pool (pay()), tap, _pay_additional (self/lands), then _fire(e, perm); False (nothing paid) when any part cannot be paid
  def _try_activated(self) -> bool         # main phase: the first board (perm, activated effect) whose policy holds and whose cost is payable; True when one fired
  def _upkeep(self) -> None                # upkeep effects of board permanents, board order; sacrifice_land n: _sacrifice_lands(n) and, when fewer lands existed than n, _sacrifice(source)
  ```
  `_land_priority`: a land with an `activated fetch` whose cost has no mana → 3 (a tapped land of a needed colour; it is two landfalls); otherwise unchanged.
  Activation policies (`_try_activated`, after `_try_one_shot` returns False, inside the main-phase loop): `fetch` — `perm.tapped` False when `cost.tap`; a creature with `cost.tap` needs `entered < turn`; mana payable → activate. `return_lands` — the Task 3 mass-return gate. Cast `extra_land`: `_spell_wanted` holds when the hand holds a land and `lands_played >= land_drops`; on resolution `land_drops += n` then `_land_step()` again.
  `take_turn` order: `turn += 1`, reset per-turn fields, `_untap()`, `_upkeep()`, `land_drops = 1 + Σ static extra_land` (computed here so the draw step of Task 5 can read it), draw (Task 5 replaces with `_draw_step`), `_land_step()`, `_produce(fresh=False)`, commander stamp, `_main_phase()`, pending payoffs, record, combat — as today otherwise.
  `GameRecord` gains `graveyard_lands_by_turn: list[int]`, `distinct_lands_by_turn: list[int]` (recorded in `_record_board`).

- [ ] **Step 1: Write failing tests**: `test_extra_land_statics_raise_the_drops` (Azusa on board, 3 lands in hand → 3 played, `landfall_by_turn[t] == 3`, Plants per Necrobloom commander = 3); `test_cast_extra_land_plays_another_land_this_turn` (Explore-shaped spell with `cast extra_land` resolved after the land step → second land played that turn); `test_lands_are_played_from_the_graveyard_only_without_a_land_in_hand` (Ramunap on board, graveyard Forest, hand Forest → hand first; next turn, hand empty → graveyard Forest played and removed from the graveyard; no Ramunap → not played); `test_free_fetch_is_cracked_on_entry` (Evolving Wilds played untapped → in graveyard, a tapped Forest from the library on board, `landfall_by_turn[t] == 2`, `_gy_lands() == ["Evolving Wilds"]`); `test_fetch_replay_loop_uses_a_drop_each_time` (Review Focus 2: Ramunap + Azusa (3 drops), Wilds in graveyard, empty hand → at most 3 fetches in the turn, each a landfall pair); `test_costed_fetch_waits_for_spare_mana` (Myriad Landscape untapped on board, 2 spare mana after the main phase → cracked, two 1-mana lands tapped; with 1 spare → not cracked); `test_creature_fetch_cracks_the_turn_it_enters` (Sakura-Tribe Elder cast → sacrificed, in graveyard, a tapped land fetched); `test_activated_mass_return_pays_and_sacrifices` (Aftermath Analyst on board, 4 lands in graveyard, Baloths, 5 mana → Analyst in graveyard, 4 lands back, `casts` unchanged); `test_upkeep_sacrifice_land_prefers_a_land_then_the_permanent` (Review Focus 3: Gitrog-shaped creature with 2 lands → one land gone, Gitrog stays; with the only land making the one colour the hand needs and another land that does not → the other land goes; with no land → Gitrog in graveyard); `test_fetch_priority_is_a_tapped_fixer`; `test_board_diagnostics_stage2` (`graveyard_lands_by_turn`, `distinct_lands_by_turn` lengths and one value each).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** `_play_land` is removed; `test_city_of_traitors_is_sacrificed_on_the_next_land_drop` is updated to call `_land_step()` and to find City in the graveyard.
- [ ] **Step 4: Run** `uv run pytest -q --deselect tests/test_golden.py` — PASS.
- [ ] **Step 5: Commit** `feat(sim): several land drops, lands from the graveyard, fetch lands, activated abilities, upkeep land sacrifice`.

---

### Task 5: Engine — dredge in the draw step, Cultivator chains

**Files:**
- Modify: `src/edhpower/sim/engine.py`, `src/edhpower/config.py`, `src/edhpower/data/scoring.toml`
- Test: `tests/test_sim_engine.py`, `tests/test_config.py`

**Interfaces:**
- Config: `[sim] chain_cap = 20` → `SimConfig.chain_cap: int`.
- Produces:
  ```python
  self.dredged: bool                                        # this turn's draw step was replaced
  def _dredge_choice(self, want_land: bool) -> tuple[str, int] | None   # (graveyard card to return to hand, cards to mill), or None
  def _draw_step(self) -> None                              # choice and len(library) >= n → move the card to hand, _mill(n), dredged = True; else _draw(1). Never on turn 1 (the opening hand is dealt by _opening_hand)
  def _chain_lands(self) -> None                            # up to cfg.chain_cap times: a land in hand (priority) → _put_land(tapped=True, "hand") without using a drop; then one draw: _dredge_choice(want_land=True) or _draw(1); stop when the hand holds no land
  ```
  `_dredge_choice(want_land)`: `want_land` is `hand lands < land_drops` at the draw step (`land_drops` is computed before the draw step, Task 4). When `want_land` is False → None. Otherwise, in this order: (a) a board permanent has `static dredge type="lands"` and `_gy_lands()` is non-empty → the best land by `_land_priority`, n = the largest such dredge; (b) a graveyard card with its own `static dredge` (type `""`) that is a `spell`-role card whose `_spell_wanted` holds now (Life from the Loam with a land in the graveyard and a land-less hand) → that card, its n. Dredge n is only taken when `len(library) >= n` (Review Focus 1); otherwise fall through to the next candidate or draw.
  `_fire`: `chain_lands_from_hand` → `_chain_lands()`.

- [ ] **Step 1: Write failing tests**: `test_config_chain_cap`; `test_dredge_replaces_the_draw_only_when_the_hand_lacks_a_land` (Necrobloom commander on board, Forest in graveyard, hand without a land, turn ≥ 2 → Forest in hand, library 2 shorter, `dredged`, no card drawn; hand with a land → normal draw, graveyard unchanged); `test_dredge_never_replaces_the_opening_hand` (turn 1 → `_draw_step` not called / hand size 7 after mulligan logic); `test_dredge_needs_enough_library` (Review Focus 1: library of 1, dredge 2 available → draws the 1 card, graveyard unchanged); `test_self_dredge_card_comes_back_when_it_would_be_cast` (Loam in graveyard with a land there and a land-less hand → Loam in hand, 3 milled; with a land in hand → drawn instead); `test_land_dredge_beats_self_dredge` (both available → the land); `test_chain_plays_every_land_in_hand_and_draws_between` (Colossus-shaped table card: 3 lands in hand, library of non-lands → 3 lands tapped on board, hand +3 drawn −3 lands, landfall 3, no drop used; with Necrobloom and lands in the graveyard, the chain's draws dredge lands and the chain continues, bounded by `chain_cap`); `test_chain_is_capped`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q --deselect tests/test_golden.py` — PASS.
- [ ] **Step 5: Commit** `feat(sim): dredge replaces the draw when a land is needed; Cultivator-style land chains`.

---

### Task 6: Stage 2 wrap — sim v4 rows, notes, not-modelled line, report, goldens, calibration, docs

**Files:**
- Modify: `src/edhpower/sim/__init__.py`, `src/edhpower/report.py`, `src/edhpower/data/scoring.toml:69`, `tests/fixtures/golden.json`, `tests/test_fixtures.py`, `CALIBRATION.md`, `README.md:87-165`, the spec's status line
- Test: `tests/test_sim.py`, `tests/test_report.py`, `tests/test_fixtures.py`, `tests/test_golden.py`

**Interfaces:**
- `[sim] version = 4` with the comment `4 (<date>): graveyard, dredge, land drops, fetches, land recursion`.
- `SimResult` gains `landfall_by_turn`, `graveyard_lands_by_turn`, `distinct_lands_by_turn: dict[int, float]` (averages like `lands_by_turn`). Report rows after `lands on battlefield`: `lands entering this turn`, `lands in graveyard`, `distinct land names`.
- `NOT_MODELLED` (sim v4) = `("fetch then dredge in one turn (Gitrog loop)", "Sylvan Library dredges", "Field of the Dead counting lands that enter with it", "Saga chapters", "attack triggers", "life as a resource", "Room cards", "reanimation", "blockers/interaction")`.
- Sim notes added (exact text): `"lands returned from the graveyard enter tapped, one at a time"`, `"fetch lands find a 1-mana land, tapped; free fetches are cracked the turn they enter"`, `"dredge replaces the draw only when the hand lacks a land for this turn's drops, never the opening hand"`, `f"mass land return is cast with {cfg.mass_return_min_lands}+ lands in the graveyard and a landfall source out, or on the last two turns"`, `"activated abilities are paid from mana left after the main phase"`, `"a draw granted by a trigger is a plain draw, never a dredge"`, `"no maximum hand size"`.
- `tests/test_fixtures.py::test_necrobloom_engine_is_alive_in_stage2` (500 games): `sim.graveyard_lands_by_turn[8] >= 1.0`, `sim.tokens_by_turn["Zombie"][12] > 3.4` (stage 1 measured 3.4 at 20 000 games; the engine must move it well past that), `"Life from the Loam" in sim.effects_sources["forge"]` and not in `sim.unmodelled`, `sim.effects_sources["table"] == []` (the Colossus entry is not in this deck).

- [ ] **Step 1: Write failing tests**: `test_sim.py::test_result_carries_stage2_rows` (the three new rows cover every turn; the seven notes present; `json.dumps(r.to_dict())`); `test_report.py` needles updated (`"lands in graveyard"`, `"distinct land names"`, the new `not modelled:` line verbatim); the fixture test above.
- [ ] **Step 2: Run** — FAIL; **implement**; `uv run pytest -q --deselect tests/test_golden.py` — PASS.
- [ ] **Step 3: Bump** `[sim] version = 4`; **re-baseline** `uv run python tests/golden_update.py`. Check by hand, per the spec's Testing section: Necrobloom `sim_win_median` expected in T6–T8 (500 games); earlier than T6 means something counts twice — stop, find it (candidates: a land entering through `_return_lands` firing landfall twice, a free fetch cracked twice, dredge returning a card that also stays in the graveyard) and fix before re-baselining. The five Eldrazi decks' `sim_combat_median` and `sim_win_median` must be unchanged or later (they have no graveyard engine); `sim_unmodelled_count` drops where their instants/sorceries now resolve. Record every deck's old → new `win`/`combat`/`unmodelled` values in the commit message.
- [ ] **Step 4: Run** `uv run pytest -q` — PASS, full suite.
- [ ] **Step 5: End-to-end** `uv run edhpower --from-facts tests/fixtures/necrobloom-v3.facts.json --iterations 20000`: under 2 minutes; `lands in graveyard` and `distinct land names` rows present; `unmodelled` must no longer list Azusa, Aftermath Analyst, Ramunap Excavator, Oracle of Mul Daya, Life from the Loam, Splendid Reclamation, Roiling Regrowth, Titania, Springbloom Druid, Sakura-Tribe Elder, Explore, Evolving Wilds (a land: never listed), and must still list The Mending of Dominaria, Eternal Witness, Knight of the Reliquary, Insidious Roots, Zuran Orb, Six, Hedge Shredder, World Shaper, Dread Return, Victimize, Sun Titan, Eerie Ultimatum (stage 3 or out of scope). Paste the sim block into `CALIBRATION.md` under a new `## Simulator (config 1, sim v4, <date>, 20 000 games)` table (same columns as the v3 one, v3 rows kept) plus a `### necrobloom-v3 benchmark (sim v4)` section with the full block and stamp line; tell the user the copy to `~/github/necrobloom-deck/v3/benchmarks-sim4.md` is theirs to make (R15).
- [ ] **Step 6: Docs**: README's simulation section describes the graveyard, land step (drops, graveyard play, fetches), dredge rule, mass-return policy, activated abilities, the `spell` role, the new rows, and a `sim v4 (<date>)` sentence in the version paragraph; spec status → `stages 1–2 implemented (sim v4, <date>)`.
- [ ] **Step 7: Commit** `sim v4: golden re-baseline; calibration and docs`.

---

## Stage 3 — reanimation and draw engines (sim v5)

### Task 7: Effects vocabulary — reanimate, draw, land-milled and dies triggers

**Files:**
- Modify: `src/edhpower/sim/effects.py`, `src/edhpower/data/special_behaviours.toml`
- Test: `tests/test_sim_effects.py`, `tests/test_profile.py`

**Interfaces:**
- Produces:
  ```python
  TRIGGERS += ("land_milled", "dies")
  ACTIONS += ("reanimate", "draw")
  class Effect: ... mv_max: int = 0   # new, after `cost`: reanimate target filter, 0 = no cap
  # n: "milled" (return_lands of the lands of the triggering mill)
  # type for reanimate: "creature" | "permanent" (lands included)
  ```
- Reader vocabulary added:
  - `T:Mode$ ChangesZoneAll | ValidCards$ Land.YouOwn | Origin$ Library | Destination$ Graveyard | TriggerZones$ Battlefield` → trigger `land_milled` (once per mill with at least one land); `ValidCards$ Land.YouOwn+!token` accepted. `Origin$ Any` → **two** effects, `land_milled` and `land_sacrificed`, with the same action.
  - `T:Mode$ ChangesZone | Origin$ Battlefield | Destination$ Graveyard | ValidCard$ Card.Self` → trigger `dies`.
  - `Draw | Defined$ You (or absent) | NumCards$ N (default 1)` as `DB$`/`SP$`/`AB$` → `Effect(on, "draw", N)`; `A:AB$ Draw | Cost$ C` → `Effect("activated", "draw", N, cost=C)` (Horizon Canopy); `Optional$` accepted.
  - `ChangeZoneAll | ChangeType$ Card.TriggeredCards | Origin$ Graveyard | Destination$ Battlefield` on a `land_milled` trigger → `Effect("land_milled", "return_lands", "milled")`.
  - `ChangeZone | Origin$ Graveyard | Destination$ Battlefield | ValidTgts$ Creature | Creature.YouCtrl | Creature.YouOwn` → `Effect(on, "reanimate", TargetMax or 1, type="creature")`; `ValidTgts$ Permanent.YouCtrl+cmcLE<N>` or `Permanent.cmcLE<N>+YouCtrl` → `type="permanent", mv_max=N`; `ValidTgts$ Permanent.YouCtrl` → `mv_max=0`. `GainControl$`, `RememberLKI$`, `ChangeNum$ 1`, `TgtPrompt$` ignored. `ChangeType$ Permanent.YouOwn | DifferentNames$ True` (Eerie Ultimatum) stays unread.
  - A `LoseLife`/`GainLife`/`DealDamage` step with `Defined$ You` inside a read chain is ignored (life is not a resource), not unread; a top-level `A:AB$ GainLife` stays unread (Zuran Orb does nothing for a goldfish, but the reader does not know that).
  - `K:Flashback:…` stays unread (partial), as do `Attacks` triggers and `K:Crew`.
- Table: `mv_max` key; `n = "milled"` only with `do = "return_lands"` on `on = "land_milled"`; new entry:
  ```toml
  [cards."Victimize"]
  effects = [{ on = "cast", do = "reanimate", n = 2, type = "creature", cost = "Sac<1/Creature>" }]
  note = "sacrifice a creature, return two creature cards tapped; the script's 'if you do' condition is outside the reader's vocabulary"
  ```

- [ ] **Step 1: Write failing tests** with verbatim constants `DREAD_RETURN`, `SUN_TITAN`, `SEVINNES_RECLAMATION`, `WORLD_SHAPER`, `HEDGE_SHREDDER`, `HORIZON_CANOPY`, `REANIMATE` (fetched from the pinned commit), `EERIE_ULTIMATUM`, `INSIDIOUS_ROOTS`, `CORRUPTED_CONVICTION`: Gitrog (full) → `(upkeep sacrifice_land 1, static extra_land 1, Effect("land_milled", "draw", 1), Effect("land_sacrificed", "draw", 1))`, `unread == ()`; Hedge Shredder → `(Effect("land_milled", "return_lands", "milled"),)` with the attack trigger and `K:Crew` unread, partial; World Shaper → `(Effect("dies", "return_lands", "all"),)`, partial; Dread Return → `(Effect("cast", "reanimate", 1, type="creature"),)`, Flashback unread, partial; Reanimate → the same effect with `unread == ()` (the LoseLife-You step ignored); Sun Titan → `(Effect("etb", "reanimate", 1, type="permanent", mv_max=3),)`, partial; Sevinne's → the same effect, partial (DBCopy condition, Flashback); Horizon Canopy → `(Effect("activated", "draw", 1, cost="1 T Sac<1/CARDNAME>"),)`, `unread == ()`; Explore (stage 3) → `(cast extra_land 1, cast draw 1)`, `unread == ()`; Corrupted Conviction → `(Effect("cast", "draw", 2, cost="B Sac<1/Creature>"),)`. Negatives: Eerie Ultimatum → `()`; Insidious Roots → `()` (graveyard-leave trigger and `AddAbility` static unread); a hand-edited Hedge Shredder with `ValidCards$ Land.OppCtrl` → unread. Table: Victimize entry loads; `n = "milled"` on `on = "etb"` → `ValueError`.
- [ ] **Step 2: Run** — FAIL; **implement**; `uv run pytest -q --deselect tests/test_golden.py` — PASS (necrobloom's `sim_unmodelled_count` moves as Gitrog, Shredder, Shaper, Dread Return, Sun Titan and Sevinne's leave the list; re-baselined in Task 9). Horizon Canopy sits here rather than in stage 2 because its only effect is a `draw`.
- [ ] **Step 3: Commit** `feat(sim): stage 3 effects vocabulary — reanimate, draw, land-milled and dies triggers`.

---

### Task 8: Engine — land-milled and dies triggers, draw, reanimation and its clock

**Files:**
- Modify: `src/edhpower/sim/engine.py`, `src/edhpower/config.py`, `src/edhpower/data/scoring.toml`
- Test: `tests/test_sim_engine.py`, `tests/test_config.py`

**Interfaces:**
- Config: `[sim] reanimate_min_power = 4` → `SimConfig.reanimate_min_power: int`.
- `CLOCKS += ("reanimate",)` (first creature returned from the graveyard to the battlefield by a `reanimate` action).
- Produces:
  ```python
  def _mill(self, n) -> list[str]        # now also: when the milled names hold a land, fire every land_milled effect of the board (board order) with milled=<those lands>
  def _fire(self, effect, source, milled: tuple[str, ...] = ()) -> None   # return_lands "milled" returns exactly the lands of `milled` still in the graveyard
  def _sacrifice(self, perm)             # now also: a creature fires its own dies effects (source=None) after reaching the graveyard
  def _reanimate_target(self, type_: str, mv_max: int, threshold: bool) -> str | None   # graveyard cards: "creature" = is_creature; "permanent" = not is_spell (lands included); mv_max > 0 caps cmc; threshold=True also requires cmc >= cfg.threat_mv or power >= cfg.reanimate_min_power; highest cmc, ties by name
  def _reanimate(self, name: str) -> None  # graveyard → battlefield: a land via _put_land(tapped=True, "graveyard"); otherwise a Perm (entered = turn), _creature_entered for creatures, etb effects for others; stamp "reanimate" when it is a creature
  def _pay_sacrifice_creatures(self, n: int) -> bool   # choose, per creature: a nontoken creature with a dies return_lands effect while _gy_lands() is non-empty, else the lowest-power token, else the lowest-power nontoken creature; False (nothing sacrificed) when fewer than n creatures
  ```
  `_pay_additional` pays `sacrifice_creatures` through `_pay_sacrifice_creatures`. `_fire` additions: `draw` → `_draw(n)` (plain draw); `reanimate` → `n` × `_reanimate(_reanimate_target(type, mv_max, threshold=False))` for triggers and activations; for the `cast` policy `threshold=True` decides whether the spell is wanted (`_spell_wanted`: an eligible target exists and, when the cost sacrifices creatures, `_pay_sacrifice_creatures` could pay — checked without paying), and the resolution then takes the highest-MV eligible target (threshold off). Activation policy for `draw`: the hand is empty, the pool pays. `land_sacrificed draw` fires per land through the Task 3 hook.

- [ ] **Step 1: Write failing tests**: `test_config_reanimate_min_power`; `test_land_milled_fires_once_per_mill_with_a_land` (Gitrog on board, mill 3 with 2 lands → 1 card drawn; mill 3 with no land → none); `test_milled_lands_return_exactly_once` (Review Focus 4: Hedge Shredder on board, a dredge milling 2 lands → both on the battlefield tapped, graveyard holds neither, landfall 2; Shredder plus Gitrog → the draw also fires); `test_dies_returns_lands` (World Shaper sacrificed to a Victimize-shaped table card with 3 lands in the graveyard → lands back, Shaper in graveyard, two creatures returned); `test_reanimate_policy_and_target` (Dread Return in hand, graveyard with a 2/2 and a 6/6 → cast, the 6/6 returns, `clocks["reanimate"] == turn`; graveyard with only the 2/2 → held); `test_sun_titan_returns_a_cheap_permanent_or_a_land` (etb with a fetch land and a 3-drop in the graveyard → the 3-drop (highest MV); with only the land → the land, tapped, landfall fires); `test_sacrifice_cost_prefers_a_token_and_refuses_when_empty` (Review Focus 5: Victimize-shaped spell, board with a token and a 5/5 → the token goes; board empty → not cast, hand unchanged); `test_horizon_land_draws_when_the_hand_is_empty` (Horizon-shaped land, empty hand, 1 spare mana → sacrificed, 1 card drawn; hand non-empty → kept); `test_triggered_draw_is_never_a_dredge` (Gitrog + Necrobloom, land-less hand, a land milled → the draw is a library card, the graveyard land stays).
- [ ] **Step 2: Run** — FAIL; **implement**; `uv run pytest -q --deselect tests/test_golden.py` — PASS.
- [ ] **Step 3: Commit** `feat(sim): land-milled and dies triggers, triggered draw, reanimation and the reanimate clock`.

---

### Task 9: Stage 3 wrap — sim v5 clock, not-modelled line, goldens, calibration, docs

**Files:**
- Modify: `src/edhpower/sim/__init__.py`, `src/edhpower/data/scoring.toml:69`, `tests/fixtures/golden.json`, `tests/test_fixtures.py`, `CALIBRATION.md`, `README.md`, the spec's status line
- Test: `tests/test_sim.py`, `tests/test_report.py`, `tests/test_fixtures.py`, `tests/test_golden.py`

**Interfaces:**
- `[sim] version = 5` with the comment `5 (<date>): reanimation, land-milled and dies triggers, triggered draw`.
- `clock_labels` gains `"reanimate": "creature returned from the graveyard to the battlefield"` after `lethal_combo`; `NOT_MODELLED` drops `"reanimation"`. Notes added: `"reanimation targets the highest-MV eligible card; a reanimation spell is cast only for a creature with MV {threat_mv}+ or power {reanimate_min_power}+"`, `"a sacrifice cost takes a creature whose death returns lands, else a token, else the smallest creature"`.
- `tests/test_fixtures.py::test_necrobloom_stage3_reanimates` (500 games): `sim.clocks["reanimate"].reached > 0`, `"The Gitrog Monster"` and `"World Shaper"` in `effects_sources["forge"]`, `"Victimize" in effects_sources["table"]`, `"Hedge Shredder" in sim.partial`.

- [ ] **Step 1: Write failing tests** (`test_sim.py`: the clock is in `clocks` with that label and `status == "ok"`; `test_report.py`: the `not modelled:` needle without reanimation; the fixture test) — FAIL; **implement**; `uv run pytest -q --deselect tests/test_golden.py` — PASS.
- [ ] **Step 2: Bump** `[sim] version = 5`; **re-baseline**; check by hand as in Task 6 Step 3 (Necrobloom `win` median still in T6–T8 or later-but-explained; never earlier than the v4 value by more than the reanimation and Gitrog draws can account for — record old → new per deck in the commit message). The Eldrazi decks' `win` must not move earlier.
- [ ] **Step 3: Run** `uv run pytest -q` — PASS, full suite.
- [ ] **Step 4: End-to-end** on the Necrobloom fixture at 20 000 games: under 2 minutes; `reanimate` row present; `unmodelled` must no longer list The Gitrog Monster, World Shaper, Hedge Shredder, Dread Return, Sun Titan, Sevinne's Reclamation, Victimize. Append the v5 table and benchmark block to `CALIBRATION.md`.
- [ ] **Step 5: Docs**: README (reanimation policy, the `reanimate` clock, the sacrifice-cost rule, `sim v5` sentence); spec status → `stages 1–3 implemented (sim v5, <date>)`.
- [ ] **Step 6: Commit** `sim v5: golden re-baseline; calibration and docs`.
