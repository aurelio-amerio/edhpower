# Sim stage 1: board and damage (sim v3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The goldfish simulator reads each card's Forge script, creates tokens from landfall/ETB triggers, counts anthems, counters and held pumps in combat, kills three 40-life opponents, reports a `win` clock with a fast-games column and per-turn board diagnostics, flags poorly covered decks exactly, and pins the Necrobloom list as a golden fixture.

**Architecture:** `forge.py` fetches and caches one Card-Forge script per card at a pinned commit and `facts.py` stores it (schema 3). `sim/effects.py` turns a card (table entry first, Forge script second) into `Effect` records; `sim/model.py` attaches them to `SimCard` and lists unmodelled cards; `sim/engine.py` fires them on events and runs combat against three life totals; `sim/__init__.py` aggregates the new clocks and rows; report and narrative print them. No card names in `sim/`.

**Tech Stack:** Python 3.12, dataclasses, `re`, `tomllib`, `unicodedata`, existing `HttpClient`; pytest via `uv run pytest -q` from the repo root.

**Spec:** `docs/superpowers/specs/2026-10-20-board-graveyard-sim-design.md` (stage 1 section, the Forge source section, and everything they reference).

## Global Constraints

- No card names in `src/edhpower/sim/`; per-card knowledge lives in `src/edhpower/data/special_behaviours.toml` and every table-sourced card is listed in the report.
- Forge scripts are fetched at run time from `raw.githubusercontent.com/Card-Forge/forge/<commit>/forge-gui/res/cardsfolder/<initial>/<slug>.txt`, commit pinned in `scoring.toml` `[forge] commit = "33aecdd6adac36a42af9eab75d2e654626a0e7db"`, cached under `<cache_dir>/forge/<commit>/<slug>.txt`; nothing from Forge is committed to this repo except short script excerpts inside tests.
- `DeckFacts` `SCHEMA_VERSION = 3`; `--from-facts` rejects 2 with the existing message; fixtures re-frozen once (Task 0).
- `[sim] version = 3`; goldens re-baselined once, in the last task, with `uv run python tests/golden_update.py`.
- Determinism: same decklist and iteration count → same numbers.
- Simplifications must make the clock later, never earlier, and each one is a `note:` in the sim block.
- Tokens and creatures attack only if `entered < turn` (no haste).
- TDD: failing test first in every task; `uv run pytest -q` green before every commit; commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Runtime: 20 000 games on the Necrobloom fixture under 2 minutes.

## Review Focus

1. A landfall trigger whose `ValidCard$` is `Land.OppCtrl` or `Land` (any controller) must not fire on our land drops — negative test in Task 2.
2. A card in the table gets **only** the table's effects, never the script's as well — test in Task 2.
3. One 100-power attacker must not kill three opponents in one swing — test in Task 4.
4. Spellbook unavailable: `win` still `ok`, from `lethal_table` alone — test in Task 5.
5. Forge 404 for a card (new set, renamed file) must not abort the run: the card is unmodelled, the run continues — test in Task 0.

---

### Task 0: `forge.py` fetcher, facts schema 3, fixture re-freeze

**Files:**
- Create: `src/edhpower/forge.py`
- Modify: `src/edhpower/facts.py:18-30,104-190`, `src/edhpower/cli.py:32-48,100-145`, `src/edhpower/config.py` (new `ForgeConfig`), `src/edhpower/data/scoring.toml` (new `[forge]` table)
- Modify: `tests/fixtures/*.facts.json` (re-frozen), `tests/conftest.py:90-95` (`sim_facts` gains `scripts: dict[str, str] | None = None`)
- Test: `tests/test_forge.py`, `tests/test_facts.py`, `tests/test_cli.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  ```python
  # forge.py
  FORGE_RAW = "https://raw.githubusercontent.com/Card-Forge/forge/{commit}/forge-gui/res/cardsfolder/{initial}/{slug}.txt"
  class ForgeError(Exception): ...                      # unreachable / non-404 failure
  def forge_slug(name: str) -> str                      # "Azusa, Lost but Seeking" -> "azusa_lost_but_seeking"; "Walk-In Closet // Forgotten Cellar" -> "walk_in_closet_forgotten_cellar"
  class ForgeClient:
      def __init__(self, http: HttpClient, cache_dir: Path, commit: str, progress: Callable[[str], None] | None = None) -> None
      def fetch(self, name: str) -> str | None          # cached text, or None on 404 (cached as an empty marker file so a 404 is not re-asked)
      def fetch_many(self, names: Iterable[str]) -> dict[str, str | None]
  # facts.py
  SCHEMA_VERSION = 3
  class FactEntry: ... forge_script: str | None = None
  def build_facts(..., forge_scripts: dict[str, str | None] | None = None, forge_commit: str | None = None, forge_unavailable_reason: str | None = None) -> DeckFacts
  # facts.fetched gains "forge_commit": str | None and "forge_status": "ok" | "<reason>"; facts.fetched["forge_missing"]: comma-joined names with no script
  # config.py
  @dataclass(frozen=True) class ForgeConfig: commit: str; min_interval: float
  ScoringConfig.forge: ForgeConfig        # [forge] commit = "33aecdd6…", min_interval = 0.1
  # cli.py
  --no-forge   # skip Forge; forge_status = "skipped (--no-forge)"
  ```
- Slug rule: NFKD → drop combining marks → lower → replace `-` and ` ` with `_` → drop every character not in `[a-z0-9_]` → collapse `__` → for `A // B` apply to each face and join with `_`. Initial = first character of the slug.
- The HTTP `Accept` header is JSON today; `ForgeClient` must read the raw text, so it uses `http._send` via a new `HttpClient.get_text(url) -> tuple[int, str]` (no JSON parse, same pacing and retry).

- [ ] **Step 1: Write failing tests** in `tests/test_forge.py`: `test_forge_slug` (the five verified names above plus `"Thespian's Stage" → "thespians_stage"`, `"Jötun Grunt" → "jotun_grunt"`, `"Lim-Dûl the Necromancer" → "lim_dul_the_necromancer"`, `"Six" → "six"`); `test_fetch_caches_text` (fake `send` returning 200 once → second `fetch` makes no request); `test_404_returns_none_and_is_cached` (Review Focus 5; one request total across two calls); `test_500_raises_forge_error`; `test_fetch_many_preserves_order_and_nones`. In `tests/test_facts.py`: `test_schema_version_is_3_and_entries_carry_scripts`, `test_load_facts_rejects_schema_2`. In `tests/test_config.py`: `test_forge_config_pinned` (`cfg.forge.commit` is 40 hex chars). In `tests/test_cli.py`: `test_no_forge_flag_sets_status` and `test_forge_unreachable_degrades_with_note` (exit 0, `fetched["forge_status"]` starts with `"Forge unreachable"`).
- [ ] **Step 2: Run** `uv run pytest tests/test_forge.py tests/test_facts.py tests/test_config.py tests/test_cli.py -q` — FAIL.
- [ ] **Step 3: Implement** `forge.py`, `HttpClient.get_text`, the config table, the facts fields, and the CLI wiring (after Scryfall resolution, before tags: `ForgeClient(http, cache_dir / "forge" / commit, commit, progress).fetch_many(resolved names)` inside `try/except (ForgeError, OSError)` → reason string). Progress line format `forge: {i}/{n} {name}` to stderr like the tag fetcher.
- [ ] **Step 4: Re-freeze the fixtures**: for each `tests/fixtures/*.facts.json`, run `uv run python - <<'EOF'` that loads it with a one-off schema-2 reader (copy `load_facts` body with the version check removed), fetches scripts for every entry via `ForgeClient` into the real cache, writes schema-3 facts with `save_facts`. Also create `tests/fixtures/necrobloom-v3.facts.json` the same way from `~/github/necrobloom-deck/v3/analysis.json["facts"]` and copy `~/github/necrobloom-deck/v3/decklist.txt` to `tests/fixtures/decks/necrobloom-v3.txt`. Record in the commit message how many entries per fixture have `forge_script is None` (expected: 0 for all six; if not, list them).
- [ ] **Step 5: Run** `uv run pytest -q` — PASS except `test_golden.py` (fixture facts re-frozen with identical scoring inputs → goldens unchanged; if any golden moves here, the re-freeze altered a field it should not have — stop and compare the two facts files).
- [ ] **Step 6: Commit** `feat(forge): fetch Card-Forge scripts at a pinned commit; facts schema 3; fixtures re-frozen with scripts; necrobloom-v3 fixture added`.

---

### Task 1: `sim/effects.py` — Effect records from the table and from Forge scripts

**Files:**
- Create: `src/edhpower/sim/effects.py`
- Modify: `src/edhpower/profile.py:24-36` (`SpecialBehaviour` gains `effects`, `kind` optional), `src/edhpower/facts.py:147` (`special_hits` string for effects-only entries), `src/edhpower/data/special_behaviours.toml` (header, `version = 2`)
- Test: `tests/test_sim_effects.py`, `tests/test_profile.py`

**Interfaces:**
- Produces:
  ```python
  TRIGGERS = ("landfall", "etb", "creature_etb", "token_created", "static", "cast")
  ACTIONS = ("token", "counters", "anthem", "pump", "mana", "drain")

  @dataclass(frozen=True)
  class Effect:
      on: str; do: str
      n: int | str = 1            # "lands" = lands you control at resolution
      power: int = 0; toughness: int = 0
      type: str = ""              # token creature type; scope for anthem/pump/counters ("" all creatures, "tokens", or a creature type)
      each_opponent: bool = True
      when: str = ""              # "" | "distinct_lands >= N" | "lands >= N" | "tokens >= N"
      upgrade: "Effect | None" = None

  @dataclass(frozen=True)
  class CardEffects:
      effects: tuple[Effect, ...]
      source: str                 # "table" | "forge" | "none"
      unread: tuple[str, ...]     # Forge T:/A:/S: lines or sub-abilities (first 60 chars) the reader did not understand; () for table cards
      partial: bool = False       # some effect read, some choice/branch not (Charm, Branch, extra trigger)
      ramp_to_battlefield: int = 1
      ramp_to_hand: int = 0

  def effects_for(card: CardData, script: str | None, special: SpecialBehaviour | None) -> CardEffects
  def condition_holds(when: str, distinct_lands: int, lands: int, tokens: int) -> bool
  def parse_effects_table(raw: list[dict]) -> tuple[Effect, ...]
  def parse_script(text: str) -> ForgeScript    # lines -> fields; `ForgeScript(keywords: tuple[str,...], triggers: list[dict], abilities: list[dict], statics: list[dict], svars: dict[str, dict])`, each dict = the `Key$ Value` pairs split on " | "
  ```
- Reader vocabulary (stage 1), anything else → `unread`:
  - Trigger: `T:` with `Mode$ ChangesZone`, `Destination$ Battlefield`, and `ValidCard$` ∈ {`Land.YouCtrl` → `landfall`; `Card.Self` → `etb`; `Creature.Other+YouCtrl` / `Creature.YouCtrl+Other` → `creature_etb`}. Resolve `Execute$ <SVar>` and follow `SubAbility$`/`TrueSubAbility$`/`FalseSubAbility$` chains.
  - `DB$ Token | TokenScript$ <c>_<p>_<t>_<type>` → `token` (p, t, type title-cased; `TokenAmount$ X` with `SVar:X:Count$Valid Land.YouCtrl` → `n="lands"`, plain integer → n).
  - `DB$ Branch | BranchConditionSVar$ X | BranchConditionSVarCompare$ GE<N>` with `X = Count$Valid Land.YouCtrl$DifferentCardNames` → the False branch's token with `upgrade` = the True branch's token and `when = f"distinct_lands >= {N}"`; `Count$Valid Land.YouCtrl` → `lands >= N`. If only one branch is understood (Scute Swarm: True branch is `CopyPermanent`), that branch is the effect, unconditioned, and the other goes to `unread`.
  - `DB$ Charm | Choices$ A,B` (modal "choose one": Felidar Retreat, Retreat to Hagra) → the goldfish always picks the **first understood** choice in list order; the other choices go to `unread` so the report shows them, but they do not make the card unmodelled on their own (a `CardEffects.partial: bool = True` flag records it; `unmodelled` in Task 2 counts only cards with `effects == ()`).
  - `T:Mode$ TokenCreated | ValidPlayer$ You` → trigger `token_created` (added to `TRIGGERS`; Mirkwood Bats' drain is stage-1 relevant). `T:Mode$ Sacrificed` → `unread`.
  - `DB$ PutCounterAll | ValidCards$ Creature.<Type>+YouCtrl | CounterType$ P1P1 | CounterNum$ N` → `counters` (type); `ValidCards$ Creature.YouCtrl` → type `""`.
  - `S:Mode$ Continuous | Affected$ Creature.YouCtrl | AddPower$ P | AddToughness$ T` → `anthem` scope `""`; `Creature.token+YouCtrl` → `"tokens"`; `Creature.<Type>+YouCtrl` → that type.
  - `A:SP$ PumpAll | ValidCards$ Creature.YouCtrl | NumAtt$ +P | NumDef$ +T` → `pump` (`cast`).
  - `DB$ Mana | Produced$ Any|<colour>` (`Amount$` default 1) or `DB$ Token | TokenScript$ c_a_treasure_sac` on a trigger → `mana` n.
  - `DB$ LoseLife | Defined$ Player.Opponent|Opponent | LifeAmount$ N` → `drain` each_opponent (Retreat to Hagra is `LifeAmount$ 1`); `Defined$ TargetedPlayer` / `ValidTgts$ Opponent` → each_opponent False. `DB$ DealDamage | Defined$ Player.Opponent | NumDmg$ N` → same. A trailing `GainLife` sub-ability is ignored, not unread.
  - Ramp spells: walk the `A:SP$ ChangeZone` chain (`SubAbility$`): `ramp_to_battlefield` = Σ `ChangeNum$` (default 1) over steps with `Origin$ Library | Destination$ Battlefield` and a `ChangeType$ Land…`; `ramp_to_hand` = Σ over steps with `Destination$ Hand` and a land type. `Destination$ Library` steps (Cultivate's reveal) and `Cleanup` are ignored. Harrow → (2, 0); Cultivate → (1, 1); Rampant Growth → (1, 0).
  - Known-and-ignored lines (do not count as unread): `K:` keywords other than those read, `SVar:PlayMain1`, `SVar:AIPreference`, `SVar:BuffedBy`, `AI:`, `DeckHas`, `DeckHints`, `Oracle`, `Name`, `ManaCost`, `Types`, `PT`, `S:` with `CharacteristicDefining$ True`, and any static whose only effect is `AddKeyword$ Vigilance|Trample|…` (keywords on an anthem card are read with the anthem, not as unread).
- `SpecialBehaviour.kind: str | None`, `.effects: tuple[Effect, ...] = ()`; `facts.py:147` writes `f"{e.name} (effects)"` when `kind is None`.

- [ ] **Step 1: Write failing tests** in `tests/test_sim_effects.py` with Forge script text pasted verbatim from the pinned commit into module-level constants (`NECROBLOOM`, `AVENGER`, `BALOTHS`, `FELIDAR_RETREAT`, `SCUTE_SWARM`, `INTANGIBLE_VIRTUE`, `OVERRUN`, `LOTUS_COBRA`, `RETREAT_TO_HAGRA`, `HARROW`, `CULTIVATE`, `MIRKWOOD_BATS`, `SIX`, `GRIZZLY_BEARS`, plus a hand-edited `OPP_LANDFALL` = Baloths with `ValidCard$ Land.OppCtrl`):
  - Necrobloom → one effect `Effect("landfall","token",1,0,1,"Plant", upgrade=Effect("landfall","token",1,2,2,"Zombie", when="distinct_lands >= 7"))`; the dredge static is in `unread` (stage 2) so `source == "forge"` and `len(unread) == 1`.
  - Avenger → `(Effect("etb","token","lands",0,1,"Plant"), Effect("landfall","counters",1,type="Plant"))`, `unread == ()`.
  - Baloths → 4/4 Beast; Felidar Retreat → 2/2 Cat and the counters mode in `unread` (Forge's `Charm`/`GenericChoice`); Scute Swarm → 1/1 Insect, the copy branch in `unread`.
  - Intangible Virtue → `Effect("static","anthem",1,1,1,"tokens")`; Overrun → `Effect("cast","pump",1,3,3,"")`.
  - Lotus Cobra → `Effect("landfall","mana",1)`; Retreat to Hagra → `Effect("landfall","drain",1)` (first understood Charm choice is `DBLoseLife`, since `DBPump` targets a creature and is not in the vocabulary; `partial is True`).
  - Mirkwood Bats → `Effect("token_created","drain",1)` with the `Sacrificed` trigger in `unread`, `partial is True`.
  - Harrow → `ramp_to_battlefield == 2`; Cultivate → `(1, 1)`; Rampant Growth → `(1, 0)`.
  - Negatives: `OPP_LANDFALL` → `effects == ()` and the trigger in `unread`; Six → `()` with `unread` non-empty; Grizzly Bears → `()`, `unread == ()`, `source == "forge"`; `script=None` → `source == "none"`.
  - Table precedence: `effects_for(baloths_card, BALOTHS, SpecialBehaviour("Rampaging Baloths", None, 0, effects=(Effect("landfall","token",1,1,1,"Goat"),)))` → Goat only, `source == "table"`, `unread == ()`.
  - `condition_holds` three cases; `parse_effects_table` with an `upgrade` sub-table; unknown `on`/`do` → `ValueError` naming the key.
- [ ] **Step 2: Run** `uv run pytest tests/test_sim_effects.py -q` — FAIL.
- [ ] **Step 3: Implement** `effects.py` per the vocabulary; `profile.py` and `facts.py` changes; `tests/test_profile.py::test_effects_only_entry_has_no_kind` and `::test_entry_without_kind_or_effects_is_rejected`.
- [ ] **Step 4: Run** `uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(sim): effects module reading Forge scripts and the behaviours table`.

---

### Task 2: `sim/model.py` — effects on `SimCard`, token cards, exact unmodelled list

**Files:**
- Modify: `src/edhpower/sim/model.py`
- Test: `tests/test_sim_model.py`

**Interfaces:**
- Consumes: `effects_for(card, entry.forge_script, special)`, `CardEffects`.
- Produces:
  ```python
  class SimCard: ... effects: tuple[Effect, ...] = (); ramp_to_battlefield: int = 1; ramp_to_hand: int = 0
  ROLES += ("token",)
  def token_card(type_: str, power: int, toughness: int) -> SimCard   # name f"{type_} token", is_creature, role "token", cost parse_cost(""), produces frozenset()
  class SimDeck: ... effects_sources: dict[str, list[str]]   # {"table": [...], "forge": [...], "none": [...]} nonland non-commander names, sorted
                     unmodelled: tuple[str, ...]              # sorted: nonland, non-commander, source != "table", effects == () and (unread non-empty or source == "none")
                     partial: tuple[str, ...]                 # sorted: cards with effects and unread both non-empty
  ```
- `build_sim_deck` notes: when `unmodelled`: `f"{k} nonland card(s) have script lines the model does not read: {names[:4]}…"`; when `partial`: `f"{k} card(s) modelled in part (a mode or branch is skipped): {names[:4]}…"`; when `facts.fetched.get("forge_status") != "ok"`: `f"Forge scripts unavailable ({status}): effects come from the behaviours table only"`.

- [ ] **Step 1: Write failing tests** (`sim_facts(..., scripts={name: text})` from Task 0): `test_effects_ride_on_simcard` (Baloths script → `effects[0].do == "token"`, `effects_sources["forge"] == ["Rampaging Baloths"]`); `test_token_card_shape`; `test_unmodelled_is_exact` (Six → in `unmodelled`; Baloths, Grizzly Bears, a Forest, the commander → not; a card with `script=None` → in; Retreat to Hagra → in `partial`, not in `unmodelled`); `test_table_card_is_never_unmodelled`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Coverage dict gains `"token": 0`.
- [ ] **Step 4: Run** `uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(sim): SimCard.effects, token cards and the exact unmodelled list`.

---

### Task 3: Engine — tokens, triggers, counters, ramp counts, per-turn board diagnostics

**Files:**
- Modify: `src/edhpower/sim/engine.py`
- Test: `tests/test_sim_engine.py`

**Interfaces:**
- Produces (on `Game`): `self.distinct_lands: set[str]`, `Perm.counters: int = 0`, methods `_land_entered(perm) -> None`, `_creature_entered(perm) -> None`, `_fire(effect, source: Perm | None) -> None`, `_create_tokens(effect) -> None`, `_token_count() -> int`, `_anthem_bonus(card) -> int`, `_board_power() -> int` (Σ over board creatures/tokens with `entered < turn` of `power + counters + anthem`). `GameRecord` gains `tokens_by_turn: dict[str, list[int]]`, `board_power_by_turn: list[int]`, `lands_by_turn: list[int]`, `landfall_by_turn: list[int]`.
- Every land reaching the battlefield (`_play_land`, `_fetch_land`) passes through `_land_entered`; every nonland permanent through `_creature_entered` when it is a creature; every token batch through `_tokens_created(n)`, which fires `token_created` effects once per token. `_land_entered` updates `distinct_lands`, then fires `landfall` effects of every board permanent in board order, evaluating `when` with `condition_holds(e.when, len(distinct_lands), lands, _token_count())`; a token effect with `upgrade` uses the upgrade when its `when` holds. `etb` fires for the entering permanent; `creature_etb` for other board permanents. `landfall mana` → `_add_units(ANY_COLOR, n, from_tap=False)`. `counters` → +n on each board token/creature matching `type`. `ramp_spell` resolution calls `_fetch_land()` `ramp_to_battlefield` times and moves `ramp_to_hand` 1-mana lands from library to hand.

- [ ] **Step 1: Write failing tests** (scripts from Task 1's constants, decks via `_deck` with `scripts=`):
  - `test_landfall_token_maker_makes_one_token_per_land_drop` (Baloths cast T4 on a Forest deck → `tokens_by_turn["Beast"][4:7] == [0, 1, 2]`).
  - `test_tokens_attack_from_the_turn_after_they_enter`.
  - `test_zombie_threshold_needs_seven_distinct_names` (Necrobloom script as commander: 40 Forests → no Zombie ever; seven differently named basics-plus-duals → first Zombie the drop after the seventh distinct name).
  - `test_etb_tokens_scale_with_lands` (Avenger with 6 lands → 6 Plants); `test_landfall_counters_hit_tokens_of_type`.
  - `test_anthem_adds_to_tokens_only_when_scoped` (Virtue + 3 Beasts + Bears → `_board_power() == 3*5 + 2`).
  - `test_landfall_mana_enters_the_pool` (Cobra on board → `produced` one higher on the land-drop turn).
  - `test_creature_etb_fires_for_other_creatures_only`.
  - `test_token_created_drain_fires_per_token` (Mirkwood Bats + Avenger entering with 5 lands → each opponent loses 5).
  - `test_opponents_land_trigger_never_fires` (Review Focus 1).
  - `test_ramp_spell_puts_as_many_lands_as_its_script_says` (Harrow + Baloths on board → two Beasts); `test_ramp_spell_second_land_to_hand` (Cultivate → hand gains one land).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Token `Perm`s share one `token_card` per `(type, power, toughness)` cached on the `Game`. Diagnostics recorded at the end of `take_turn`.
- [ ] **Step 4: Run** `uv run pytest -q` — PASS; existing engine tests unchanged.
- [ ] **Step 5: Commit** `feat(sim): tokens, landfall/ETB triggers, counters, ramp counts and board diagnostics in the engine`.

---

### Task 4: Engine — three opponents, pumps held for lethal, win clocks; config

**Files:**
- Modify: `src/edhpower/sim/engine.py`, `src/edhpower/config.py:70-88,208-224`, `src/edhpower/data/scoring.toml:68-81,120-123`
- Test: `tests/test_sim_engine.py`, `tests/test_config.py`

**Interfaces:**
- Config: `[sim] version = 3`, `lethal_damage` → `life_per_opponent = 40`, new `opponents = 3`; `[narrative] unmodelled_share = 0.25`. `SimConfig.life_per_opponent`, `.opponents`; `NarrativeConfig.unmodelled_share`.
- `CLOCKS += ("lethal_table", "win")`. `Game.life: list[int]`; `self.damage` (focused counter for `combat`) unchanged. `GameRecord.damage_by_turn: list[int]`, `.max_swing: int`.
- `_combat()` replaces the two inline lines at the end of `take_turn`: attackers sorted by effective power descending, each assigned to the opponent with the most life left (ties: lowest index); `drain` effects fired during the turn already reduced `life`. `_try_pump() -> bool` runs in `_main_phase` after the role loop: cast the cheapest castable `cast pump` only if the projected swing with it (`_board_power() + pump.power × attackers`) kills at least one opponent who survives without it. `_stamp("lethal_table")` when all `life <= 0`; `_stamp("win")` on `lethal_table` or `lethal_combo`.

- [ ] **Step 1: Write failing tests**: `test_config_sim_v3_fields`; `test_single_huge_attacker_does_not_kill_the_table_in_one_swing` (Review Focus 3: `lethal_table` on the third attacking turn, `combat` on the first); `test_three_forty_power_attackers_kill_the_table_in_one_swing`; `test_pump_is_held_until_it_kills_someone`; `test_each_opponent_drain_hits_all_three`; `test_win_stamps_on_lethal_combo_too` (reuse this file's lethal-combo fixture); `test_damage_by_turn_and_max_swing`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** config, then engine.
- [ ] **Step 4: Run** `uv run pytest -q --deselect tests/test_golden.py` — PASS (goldens move on purpose; re-baselined in Task 7).
- [ ] **Step 5: Commit** `feat(sim): three opponents, lethal_table and win clocks, pumps held for lethal; sim v3 config`.

---

### Task 5: `sim/__init__.py` — aggregate the new clocks and rows

**Files:**
- Modify: `src/edhpower/sim/__init__.py`
- Test: `tests/test_sim.py`

**Interfaces:**
- `Clock.fast: int | None` = `sorted(padded)[int(0.05 * n)]`, `None` when `> max_turn`.
- `SimResult` gains `damage_by_turn`, `board_power_by_turn`, `lands_by_turn: dict[int, float]`; `tokens_by_turn: dict[str, dict[int, float]]`; `max_swing_median: int`; `win_route: dict[str, float]` (`combat` / `combo` / `none`, ties → combat); `effects_sources: dict[str, list[str]]`; `unmodelled: list[str]`.
- Labels: `win: "win (table lethal or lethal combo)"`, `lethal_table: f"lethal to the table ({opponents} × {life}, combat and drain)"`, `combat: f"{life} combat damage to one opponent (no blockers)"`. Dict order: `win`, `lethal_table`, then today's order.
- `win` is `ok` with Spellbook unavailable (Review Focus 4) and a note says it is `lethal_table` alone.
- Sim note becomes `"combat counts printed power, counters, anthems and pumps cast for lethal; tokens attack from the turn after they enter; no haste, no blockers"`.

- [ ] **Step 1: Write failing tests**: `test_clock_fast_is_fifth_percentile` (`[3]*95 + [1]*5` → `fast == 1`, `median == 3`); `test_result_carries_new_rows`; `test_win_ok_without_spellbook`; `test_same_deck_same_numbers`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q --deselect tests/test_golden.py` — PASS.
- [ ] **Step 5: Commit** `feat(sim): win and lethal_table clocks, fast column, board rows and win route in SimResult`.

---

### Task 6: Report and narrative

**Files:**
- Modify: `src/edhpower/report.py:138-165`, `src/edhpower/narrative.py:52-140`
- Test: `tests/test_report.py`, `tests/test_narrative.py`

**Interfaces:**
- Report sim block: `fast` column after `median`; rows `damage this turn`, `board power`, `lands on battlefield`, one `tokens: <Type>` row per type (sorted); `win route: combat 80% · combo 20% · none 0%`; `biggest swing (median) N`; coverage line appends `· unmodelled {k}`; a line `effects: table {k} ({names…}) · forge {k} · unmodelled: {names…}` (`_names(…, 4)`); a `note:` per sim note as today.
- Narrative: `Finding("win", f"Median win {_turn(m)} (fast games {_turn(f)}), via combat {c:.0%} / combo {k:.0%}; {hint}")` first among sim findings, `hint` = `"typical of an uncontested Bracket 3 deck (T6–T8)"` for `6 <= m <= 8`; `"earlier than Bracket 3 decks usually close (T6): a Bracket 4 hint, or the model is counting something twice"` for `m < 6`; `"later than Bracket 3 decks usually close (T8)"` for `m > 8`; `"no win by T{max} in half the games"` for `None`. Never touches the bracket verdict.
- `Finding("coverage", f"{k} of {n} nonland cards have no modelled effect ({names…}); every clock is a floor and the deck is not comparable with a well-covered list")` when `n > 0 and k / n >= cfg.unmodelled_share`; `n` counts copies, excludes commanders.
- `[clocks]` finding adds `lethal_table`.

- [ ] **Step 1: Write failing tests**: `test_report_prints_fast_column_and_board_rows` (`"fast"`, `"tokens: Zombie"`, `"win route:"`, `"unmodelled"`); `test_win_finding_hints_bracket3_window` (7 → "typical of"); `test_win_finding_flags_fast_median` (5 → "counting something twice"); `test_coverage_finding_threshold` (3 of 10 present; 2 of 10 absent; 0 nonland absent).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q --deselect tests/test_golden.py` — PASS.
- [ ] **Step 5: Commit** `feat(report): fast column, board rows, win route, win and coverage findings`.

---

### Task 7: Golden re-baseline, fixture checks, docs, benchmark

**Files:**
- Modify: `tests/golden_update.py:40-60`, `tests/fixtures/golden.json`, `tests/test_fixtures.py`, `README.md`, `docs/superpowers/specs/2026-10-20-board-graveyard-sim-design.md` (status line)
- Create: `~/github/necrobloom-deck/v3/benchmarks-sim3.md`

**Interfaces:**
- Golden keys added per deck: `sim_win_median`, `sim_win_fast`, `sim_lethal_table_median`, `sim_max_swing_median`, `sim_unmodelled_count`.
- `test_fixtures.py` parametrize gains `("necrobloom-v3", 1, 3)`; new `test_necrobloom_fixture_makes_zombies` (500 games → `tokens_by_turn["Zombie"][12] > 0`, `tokens_by_turn["Plant"][5] > 0`) and `test_necrobloom_effects_come_from_forge_not_table` (`"The Necrobloom"` and `"Avenger of Zendikar"` in `effects_sources["forge"]`, table list empty for this deck). No table entries are needed for this deck in stage 1; `special_behaviours.toml` is unchanged except the header.

- [ ] **Step 1: Write the two fixture tests; run** `uv run pytest tests/test_fixtures.py -q` — PASS (everything they need exists by now; if a test fails, the reader missed a shape — fix in `effects.py`, not with a table entry).
- [ ] **Step 2: Re-baseline**: `uv run python tests/golden_update.py`. Check the printed values: for the five pre-existing decks `sim_combat_median` must be unchanged or later; if earlier, stop and find the double count. Necrobloom at one land per turn: `sim_win_median` expected `None` or ≥ T9; record the actual values in the commit message.
- [ ] **Step 3: Run** `uv run pytest -q` — PASS, full suite.
- [ ] **Step 4: End-to-end** `uv run edhpower --from-facts tests/fixtures/necrobloom-v3.facts.json --iterations 20000`: runtime < 2 min; `tokens: Plant` and `tokens: Zombie` rows present; the `unmodelled` names are plausible (Six, Insidious Roots, Zuran Orb, Hedge Shredder expected; Avenger, Baloths, Felidar Retreat, Scute Swarm, Mirkwood Bats must not be there; Felidar Retreat, Retreat to Hagra, Scute Swarm, Mirkwood Bats expected under `partial`).
- [ ] **Step 5: Docs**: README gains the Forge source (what is fetched, the pin, `--no-forge`, cache path), the win clock, fast column, board rows and coverage line; spec status → `stage 1 implemented (sim v3, <date>)`; write the 20 000-game Necrobloom sim block to `~/github/necrobloom-deck/v3/benchmarks-sim3.md` with the stamp line (config 1, sim 3, Forge commit, seed).
- [ ] **Step 6: Commit** `sim v3: golden re-baseline with the Necrobloom fixture; docs` (edhpower), and a separate commit in `necrobloom-deck` for the benchmark file.
