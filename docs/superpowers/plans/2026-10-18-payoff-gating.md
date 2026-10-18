# Payoff Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the goldfish simulator's combo clocks honest about whether an infinite engine can actually win: the lethal clock needs the payoff assembled, lock-only lines leave the combo clock, and the report names every engine with no payoff.

**Architecture:** A new pure module `payoffs.py` turns `DeckFacts` into a `DeckPayoffs` (payoff category → card names) using oracle-text patterns ported from scrollvault, with a Scryfall tag required as a check for two categories. `sim/combos.py` classifies each Spellbook line (direct / payoff / no_payoff / unmapped / lock_only) by mapping its `produces` text to resources and resources to payoff categories (table in `scoring.toml`). The engine stamps `lethal_combo` only when the payoff condition holds, re-checking fired lines each turn. Report, narrative and bracket surface the statuses.

**Tech Stack:** Python 3.12, stdlib `re`/`tomllib`/`dataclasses`, pytest. Run everything with `uv run`. Inside the Claude Code sandbox set `UV_CACHE_DIR=$TMPDIR/uv-cache` first.

**Spec:** `docs/superpowers/specs/2026-10-18-payoff-gating-design.md`

## Global Constraints

- No field is added to `DeckFacts`; `facts.SCHEMA_VERSION` stays 2. The only new facts content is the string `fetched["tag_table"]`.
- `sim.version` in `scoring.toml` becomes 2 in Task 7, and `tests/fixtures/golden.json` is regenerated once, in Task 10, never earlier.
- The official bracket floor never changes because of a payoff. The new bracket criterion is `review`, floor `None`.
- Every test asserts on real behaviour with real oracle text; no mocks. Oracle texts below were fetched from Scryfall on 2026-10-18 and must be used verbatim.
- Card names never appear in `src/edhpower/payoffs.py` or `src/edhpower/sim/*.py` (same rule as `sim/model.py`). Curated name lists are not ported; a missed card means a widened pattern.
- Every new note or finding string must say what was *not* evaluated and why, never score a missing input as 0 silently.
- Commit after every task with a message in the imperative; end each commit message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Run the full suite (`uv run pytest -q`) at the end of every task. From Task 7 until Task 10, exactly two tests are expected to fail: `tests/test_golden.py::test_golden_config_matches_current_config` and the parametrised `test_golden_values`; any other failure is a defect in the task.

## Review Focus

Inputs the spec implies but no task's tests would otherwise exercise; each line's test is added to the task named.

1. A double-faced card whose payoff text is on the back face (Task 3: `categories_for` joins all faces, test with a two-face `make_card`).
2. A Spellbook line whose `produces` is empty (Task 4: status `unmapped`, still simulated, never lethal).
3. A line whose piece is itself the payoff, e.g. the engine's own creature is the ETB payoff (Task 4: candidates include the piece; Task 5: lethal stamps at assembly).
4. A deck whose facts were built with `tags_status != "ok"` (Task 3: pattern-only detection plus a note naming both skipped categories).
5. A `landfall_tokens` card with no go-wide payoff in the deck (Task 4: candidates empty → status `no_payoff`, report says why).

---

### Task 1: `[sim.payoffs]` config block

**Files:**
- Modify: `src/edhpower/data/scoring.toml` (append under `[sim]`, before `[narrative]`)
- Modify: `src/edhpower/config.py:66-80` (`SimConfig`) and `:163-181` (`_sim_from`)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `SimConfig.payoff_resources: tuple[tuple[str, re.Pattern[str]], ...]`, `SimConfig.payoff_converts: dict[str, tuple[str, ...]]`, `SimConfig.payoff_chained: dict[str, tuple[str, ...]]`, `SimConfig.payoff_hand_ok: frozenset[str]`, `SimConfig.lock_only: re.Pattern[str]`. Patterns are compiled with `re.IGNORECASE`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_sim_payoffs_block_loads_and_compiles():
    import re
    s = load_config().sim
    names = [r for r, _ in s.payoff_resources]
    assert names == ["mana", "death", "etb", "tokens", "counters", "storm", "draw", "self_mill", "landfall"]
    assert all(isinstance(p, re.Pattern) for _, p in s.payoff_resources)
    assert s.payoff_converts["mana"] == ("mana_sink",)
    assert s.payoff_converts["tokens"] == ("go_wide", "etb_damage", "token_drain")
    assert s.payoff_converts["landfall"] == ("landfall_payoff", "landfall_tokens")
    assert s.payoff_chained == {"landfall_tokens": ("go_wide", "token_drain", "etb_damage")}
    assert s.payoff_hand_ok == frozenset({"mana"})
    assert s.lock_only.match("Prevent all damage that would be dealt to you")
    assert s.lock_only.match("Lock") and not s.lock_only.match("Infinite colorless mana")
    assert s.payoff_resources[0][1].search("infinite colorless mana")


def test_bad_payoff_pattern_raises_value_error():
    import tomllib
    from importlib import resources
    from edhpower import config as config_mod
    raw = tomllib.loads(resources.files("edhpower.data").joinpath("scoring.toml").read_text(encoding="utf-8"))
    raw["sim"]["payoffs"]["resources"][0]["pattern"] = "infinite (mana"
    with pytest.raises(ValueError, match="payoff pattern"):
        config_mod._sim_from(raw["sim"])


def test_convert_target_must_be_a_known_category_name():
    import tomllib
    from importlib import resources
    from edhpower import config as config_mod
    raw = tomllib.loads(resources.files("edhpower.data").joinpath("scoring.toml").read_text(encoding="utf-8"))
    raw["sim"]["payoffs"]["converts"]["mana"] = ["mana_sinkk"]
    with pytest.raises(ValueError, match="unknown payoff category"):
        config_mod._sim_from(raw["sim"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_config.py -q`
Expected: 3 failures, `AttributeError: 'SimConfig' object has no attribute 'payoff_resources'` and `KeyError: 'payoffs'`.

- [ ] **Step 3: Add the TOML block**

In `src/edhpower/data/scoring.toml`, after the `lethal_features = [...]` line and before `# ---- report narrative`, add:

```toml

[sim.payoffs]
# Spellbook `produces` text -> resource. First matching rule wins per feature; "near-infinite" is folded
# into "infinite" before matching. Patterns are case-insensitive regular expressions.
resources = [
  { resource = "mana",      pattern = "infinite [a-z, ]*mana\\b|infinite mana\\b" },
  { resource = "death",     pattern = "infinite death triggers|infinite creature sacrifice triggers" },
  { resource = "etb",       pattern = "infinite creature etb" },
  { resource = "tokens",    pattern = "infinite [a-z ]*creature tokens?" },
  { resource = "counters",  pattern = "infinite \\+1/\\+1 counters" },
  { resource = "storm",     pattern = "infinite (?:storm count|magecraft triggers)" },
  { resource = "draw",      pattern = "infinite card draw" },
  { resource = "self_mill", pattern = "infinite self-mill" },
  { resource = "landfall",  pattern = "infinite landfall triggers" },
]
# resource -> payoff categories (payoffs.CATEGORIES) that turn it into a win
[sim.payoffs.converts]
mana      = ["mana_sink"]
death     = ["drain"]
etb       = ["etb_damage"]
tokens    = ["go_wide", "etb_damage", "token_drain"]
counters  = ["counter_win"]
storm     = ["cast_damage"]
draw      = ["empty_library_win"]
self_mill = ["empty_library_win"]
landfall  = ["landfall_payoff", "landfall_tokens"]
# a category listed here is fuel: it counts only when the deck also has one of the listed categories
[sim.payoffs.chained]
landfall_tokens = ["go_wide", "token_drain", "etb_damage"]
[sim.payoffs.zones]
# resources whose payoff may sit in hand (with infinite mana you can cast it); all others need the battlefield
hand_ok = ["mana"]
# a line whose every produced feature matches this is a lock, not a combo (scrollvault __SELF_PROT)
lock_only = "^(?:lock|prevent all damage that would be dealt to (?:you|permanents you control|creatures you control|you and [^.]*)(?: during [^.]*| by sources you don't control)?|you have protection from everything(?: during [^.]*)?|you can't cast spells)$"
```

- [ ] **Step 4: Extend `SimConfig` and `_sim_from`**

In `src/edhpower/config.py` add `import re` at the top. Extend the dataclass:

```python
@dataclass(frozen=True)
class SimConfig:
    version: int
    iterations: int
    max_turn: int
    opening_hand: int
    mulligan_min_lands: int
    mulligan_max_lands: int
    mana_threshold: int
    threat_mv: int
    lethal_damage: int
    metalcraft_count: int
    max_two_card_lines: int
    max_three_card_lines: int
    lethal_features: tuple[str, ...]
    payoff_resources: tuple[tuple[str, re.Pattern[str]], ...]
    payoff_converts: dict[str, tuple[str, ...]]
    payoff_chained: dict[str, tuple[str, ...]]
    payoff_hand_ok: frozenset[str]
    lock_only: re.Pattern[str]
```

Add the category list next to `COMPONENT_NAMES` (the single source of truth; `payoffs.py` imports it):

```python
PAYOFF_CATEGORIES: tuple[str, ...] = ("mana_sink", "drain", "etb_damage", "go_wide", "token_drain", "counter_win",
                                      "cast_damage", "empty_library_win", "life_drain", "landfall_payoff", "landfall_tokens")
```

Add a helper and extend `_sim_from`:

```python
def _pattern(text: str, where: str) -> re.Pattern[str]:
    try:
        return re.compile(text, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"bad payoff pattern in {where}: {e}") from e


def _payoffs_from(raw: dict[str, Any]) -> dict[str, Any]:
    resources = tuple((str(r["resource"]), _pattern(str(r["pattern"]), f"resource '{r['resource']}'")) for r in raw["resources"])
    known = {r for r, _ in resources}
    converts: dict[str, tuple[str, ...]] = {}
    for res, cats in raw["converts"].items():
        if res not in known:
            raise ValueError(f"payoff converts: unknown resource '{res}'")
        for c in cats:
            if c not in PAYOFF_CATEGORIES:
                raise ValueError(f"payoff converts '{res}': unknown payoff category '{c}'")
        converts[str(res)] = tuple(str(c) for c in cats)
    chained: dict[str, tuple[str, ...]] = {}
    for cat, targets in raw["chained"].items():
        if cat not in PAYOFF_CATEGORIES or any(t not in PAYOFF_CATEGORIES for t in targets):
            raise ValueError(f"payoff chained '{cat}': unknown payoff category")
        chained[str(cat)] = tuple(str(t) for t in targets)
    hand_ok = frozenset(str(r) for r in raw["zones"]["hand_ok"])
    if not hand_ok <= known:
        raise ValueError(f"payoff hand_ok names unknown resources: {sorted(hand_ok - known)}")
    return {
        "payoff_resources": resources,
        "payoff_converts": converts,
        "payoff_chained": chained,
        "payoff_hand_ok": hand_ok,
        "lock_only": _pattern(str(raw["zones"]["lock_only"]), "lock_only"),
    }
```

and in `_sim_from` add `**_payoffs_from(raw["payoffs"]),` as the last argument of the `SimConfig(...)` call.

- [ ] **Step 5: Run the config tests, then the whole suite**

Run: `uv run pytest tests/test_config.py -q` → Expected: all pass.
Run: `uv run pytest -q` → Expected: all pass (the golden config stamp is unchanged; `sim_version` is still 1).

- [ ] **Step 6: Commit**

```bash
git add src/edhpower/data/scoring.toml src/edhpower/config.py tests/test_config.py
git commit -m "config: add [sim.payoffs] resource/payoff tables and compiled patterns

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: New tag slugs and `fetched["tag_table"]`

**Files:**
- Modify: `src/edhpower/tags.py:19-41` (`TAG_TABLE`)
- Modify: `src/edhpower/facts.py:172-181` (the `fetched` dict in `build_facts`)
- Test: `tests/test_tags.py`, `tests/test_facts.py`

**Interfaces:**
- Produces: `facts.fetched["tag_table"]` — a comma-joined, sorted string of the slugs in `TAG_TABLE` at build time, present only when `tags_status == "ok"`; otherwise the key is absent.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tags.py`:

```python
def test_payoff_slugs_are_in_the_verified_table():
    from edhpower.tags import TAG_TABLE
    assert TAG_TABLE["mana-sink"] == 1814 and TAG_TABLE["alternate-win-condition"] == 62
```

Append to `tests/test_facts.py` (reuse that file's existing `_facts`-style helpers; if none fits, build with `parse_decklist` + `Resolution` + `build_facts` exactly as `tests/test_bracket.py::_facts` does, adding `tag_cache=full_tag_cache()` from `conftest`):

```python
def test_fetched_records_the_tag_table_when_tags_are_ok():
    from edhpower.decklist import parse_decklist
    from edhpower.facts import build_facts
    from edhpower.scryfall import CardData, Resolution
    from edhpower.tags import TAG_TABLE
    from .conftest import full_tag_cache, make_card
    objs = [make_card("Sol Ring")]
    res = Resolution({o["name"]: CardData.from_scryfall(o) for o in objs}, [], 0, None)
    with_tags = build_facts(parse_decklist("1 Sol Ring\n"), res, None, "offline", "t.txt", tag_cache=full_tag_cache())
    assert with_tags.fetched["tag_table"] == ",".join(sorted(TAG_TABLE))
    assert "mana-sink" in with_tags.fetched["tag_table"].split(",")
    without = build_facts(parse_decklist("1 Sol Ring\n"), res, None, "offline", "t.txt")
    assert "tag_table" not in without.fetched
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_tags.py tests/test_facts.py -q`
Expected: `KeyError: 'mana-sink'` and `KeyError: 'tag_table'`.

- [ ] **Step 3: Implement**

In `src/edhpower/tags.py`, add to `TAG_TABLE` after `"copy-spell": 177,`:

```python
    "mana-sink": 1814,              # probed 2026-10-18; payoff check for activation-based sinks
    "alternate-win-condition": 62,  # probed 2026-10-18; payoff check for empty-library wins
```

Update the comment above the table to say the two payoff slugs were probed 2026-10-18.

In `src/edhpower/facts.py`, replace the `fetched={...}` literal in `build_facts` with:

```python
    fetched: dict[str, str | int | None] = {
        "scryfall_cards_oldest": resolution.fetched_oldest,
        "scryfall_cards_newest": resolution.fetched_newest,
        "scryfall_cards_unknown": resolution.fetched_unknown,
        "spellbook": combos.fetched_at if combos else None,
        "spellbook_api_version": combos.api_version if combos else None,
        "tags_oldest": tags_oldest,
        "tags_newest": tags_newest,
    }
    if tags_ok:
        fetched["tag_table"] = ",".join(sorted(TAG_TABLE))
```

and pass `fetched=fetched`. Add `from edhpower.tags import TAG_TABLE, TagCache` to the imports (check the existing import line and extend it).

- [ ] **Step 4: Run tests and the suite**

Run: `uv run pytest tests/test_tags.py tests/test_facts.py -q` → pass.
Run: `uv run pytest -q` → all pass. (`conftest.full_tag_cache` builds one empty set per `TAG_TABLE` slug, so the two new slugs are automatically present in every hand-built facts object.)

Note: the real tag cache on disk (`~/.cache/edhpower/tags/`) will now be reported incomplete until the two slugs are fetched; the CLI fetches missing slugs on the next run (about 11 pages at 1 request/s). No code change needed.

- [ ] **Step 5: Commit**

```bash
git add src/edhpower/tags.py src/edhpower/facts.py tests/test_tags.py tests/test_facts.py
git commit -m "tags: add mana-sink and alternate-win-condition slugs; record tag table in facts.fetched

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `payoffs.py` — detection unit

**Files:**
- Create: `src/edhpower/payoffs.py`
- Create: `tests/test_payoffs.py`

**Interfaces:**
- Consumes: `config.PAYOFF_CATEGORIES`, `facts.DeckFacts` (`entries[i].card.oracle_text`, `.card.mana_cost`, `.card.faces`, `profiles[name].tags`, `tags_status`, `fetched["tag_table"]`).
- Produces:

```python
TAG_CHECKS: dict[str, str] = {"mana_sink": "mana-sink", "empty_library_win": "alternate-win-condition"}
CATEGORY_LABELS: dict[str, str]  # category -> human label used by the report

@dataclass(frozen=True)
class DeckPayoffs:
    by_category: dict[str, list[str]]     # every category present as a key, sorted names, commanders included
    tag_checked: tuple[str, ...]          # categories whose tag check was applied
    notes: list[str]
    def cards_for(self, categories: Iterable[str]) -> list[str]   # union, sorted, deduplicated
    def to_dict(self) -> dict[str, Any]

def categories_for(card: CardData, tags: tuple[str, ...], tag_checked: frozenset[str]) -> frozenset[str]
def detect(facts: DeckFacts) -> DeckPayoffs
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_payoffs.py`:

```python
"""Payoff detection: real oracle text (Scryfall, 2026-10-18), one positive and one negative per category."""

from __future__ import annotations

from edhpower.config import PAYOFF_CATEGORIES
from edhpower.decklist import parse_decklist
from edhpower.facts import build_facts
from edhpower.payoffs import TAG_CHECKS, DeckPayoffs, categories_for, detect
from edhpower.scryfall import CardData, Resolution

from .conftest import full_tag_cache, make_card

ALL = frozenset(TAG_CHECKS)   # every tag check applied


def _card(name, text, cost="{2}", type_line="Artifact", **over):
    return CardData.from_scryfall(make_card(name, oracle_text=text, mana_cost=cost, type_line=type_line, **over))


BALLISTA = _card("Walking Ballista", "This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nRemove a +1/+1 counter from this creature: It deals 1 damage to any target.", cost="{X}{X}", type_line="Artifact Creature — Construct")
EXSANGUINATE = _card("Exsanguinate", "Each opponent loses X life. You gain life equal to the life lost this way.", cost="{X}{B}{B}", type_line="Sorcery")
HAILFIRE = _card("Torment of Hailfire", "Repeat the following process X times. Each opponent loses 3 life unless that player sacrifices a nonland permanent of their choice or discards a card.", cost="{X}{B}{B}", type_line="Sorcery")
PASSAGE = _card("Rogue's Passage", "{T}: Add {C}.\n{4}, {T}: Target creature can't be blocked this turn.", cost="", type_line="Land")
WOLF_RUN = _card("Kessig Wolf Run", "{T}: Add {C}.\n{X}{R}{G}, {T}: Target creature gets +X/+0 and gains trample until end of turn.", cost="", type_line="Land")
BLOOD_ARTIST = _card("Blood Artist", "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.", cost="{1}{B}", type_line="Creature — Vampire")
ZULAPORT = _card("Zulaport Cutthroat", "Whenever this creature or another creature you control dies, each opponent loses 1 life and you gain 1 life.", cost="{1}{B}", type_line="Creature — Human Rogue Ally")
TREMORS = _card("Impact Tremors", "Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.", cost="{1}{R}", type_line="Enchantment")
PURPHOROS = _card("Purphoros, God of the Forge", "Indestructible\nAs long as your devotion to red is less than five, Purphoros isn't a creature.\nWhenever another creature you control enters, Purphoros deals 2 damage to each opponent.\n{2}{R}: Creatures you control get +1/+0 until end of turn.", cost="{3}{R}", type_line="Legendary Enchantment Creature — God")
HOOF = _card("Craterhoof Behemoth", "Haste\nWhen this creature enters, creatures you control gain trample and get +X/+X until end of turn, where X is the number of creatures you control.", cost="{5}{G}{G}{G}", type_line="Creature — Beast")
BATS = _card("Mirkwood Bats", "Flying\nWhenever you create or sacrifice a token, each opponent loses 1 life.", cost="{3}{B}", type_line="Creature — Bat")
ASCENDANCY = _card("Simic Ascendancy", "{1}{G}{U}: Put a +1/+1 counter on target creature you control.\nWhenever one or more +1/+1 counters are put on a creature you control, put that many growth counters on this enchantment.\nAt the beginning of your upkeep, if this enchantment has twenty or more growth counters on it, you win the game.", cost="{G}{U}", type_line="Enchantment")
PINNACLE = _card("Helix Pinnacle", "Shroud (This enchantment can't be the target of spells or abilities.)\n{X}: Put X tower counters on this enchantment.\nAt the beginning of your upkeep, if there are 100 or more tower counters on this enchantment, you win the game.", cost="{G}", type_line="Enchantment")
GUTTERSNIPE = _card("Guttersnipe", "Whenever you cast an instant or sorcery spell, this creature deals 2 damage to each opponent.", cost="{2}{R}", type_line="Creature — Goblin Shaman")
ORACLE = _card("Thassa's Oracle", "When this creature enters, look at the top X cards of your library, where X is your devotion to blue. Put up to one of them on top of your library and the rest on the bottom of your library in a random order. If X is greater than or equal to the number of cards in your library, you win the game. (Each {U} in the mana costs of permanents you control counts toward your devotion to blue.)", cost="{U}{U}", type_line="Creature — Merfolk Wizard")
LAB_MAN = _card("Laboratory Maniac", "If you would draw a card while your library has no cards in it, you win the game instead.", cost="{2}{U}", type_line="Creature — Human Wizard")
JACE = _card("Jace, Wielder of Mysteries", "If you would draw a card while your library has no cards in it, you win the game instead.\n+1: Target player mills two cards. Draw a card.\n−8: Draw seven cards. Then if your library has no cards in it, you win the game.", cost="{1}{U}{U}{U}", type_line="Legendary Planeswalker — Jace")
VITO = _card("Vito, Thorn of the Dusk Rose", "Whenever you gain life, target opponent loses that much life.\n{3}{B}{B}: Creatures you control gain lifelink until end of turn.", cost="{2}{B}", type_line="Legendary Creature — Vampire Cleric")
HAGRA = _card("Retreat to Hagra", "Landfall — Whenever a land you control enters, choose one —\n• Target creature gets +1/+0 and gains deathtouch until end of turn.\n• Each opponent loses 1 life and you gain 1 life.", cost="{2}{B}", type_line="Enchantment")
OB_NIX = _card("Ob Nixilis, the Fallen", "Landfall — Whenever a land you control enters, you may have target player lose 3 life. If you do, put three +1/+1 counters on Ob Nixilis.", cost="{3}{B}{B}", type_line="Legendary Creature — Demon")
FIELD = _card("Field of the Dead", "This land enters tapped.\n{T}: Add {C}.\nWhenever this land or another land you control enters, if you control seven or more lands with different names, create a 2/2 black Zombie creature token.", cost="", type_line="Land")
SCUTE = _card("Scute Swarm", "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, create a token that's a copy of this creature instead.", cost="{2}{G}", type_line="Creature — Insect")
SOL_RING = _card("Sol Ring", "{T}: Add {C}{C}.", cost="{1}")


def test_mana_sink_x_spells_need_no_tag():
    assert categories_for(EXSANGUINATE, (), ALL) == {"mana_sink"}
    assert categories_for(HAILFIRE, (), ALL) == {"mana_sink"}


def test_mana_sink_activation_rule_requires_the_tag_when_checked():
    assert categories_for(BALLISTA, ("mana-sink",), ALL) == {"mana_sink"}
    assert categories_for(BALLISTA, (), ALL) == frozenset()
    assert categories_for(BALLISTA, (), frozenset()) == {"mana_sink"}   # tag check not applied → pattern decides


def test_mana_sink_negatives_even_with_the_tag():
    assert categories_for(PASSAGE, ("mana-sink",), ALL) == frozenset()
    assert categories_for(WOLF_RUN, ("mana-sink",), ALL) == frozenset()
    assert categories_for(SOL_RING, (), ALL) == frozenset()


def test_drain_death_triggers():
    assert categories_for(BLOOD_ARTIST, (), ALL) == {"drain"}
    assert categories_for(ZULAPORT, (), ALL) == {"drain"}
    assert "drain" not in categories_for(TREMORS, (), ALL)


def test_etb_damage():
    assert categories_for(TREMORS, (), ALL) == {"etb_damage"}
    assert categories_for(PURPHOROS, (), ALL) == {"etb_damage"}
    assert "etb_damage" not in categories_for(BLOOD_ARTIST, (), ALL)


def test_go_wide_accepts_both_word_orders():
    assert categories_for(HOOF, (), ALL) == {"go_wide"}
    overrun = _card("Overrun", "Creatures you control get +3/+3 and gain trample until end of turn.", cost="{2}{G}{G}{G}", type_line="Sorcery")
    assert categories_for(overrun, (), ALL) == {"go_wide"}
    assert "go_wide" not in categories_for(WOLF_RUN, ("mana-sink",), ALL)   # single target creature


def test_token_drain():
    assert categories_for(BATS, (), ALL) == {"token_drain"}
    assert "token_drain" not in categories_for(ZULAPORT, (), ALL)


def test_counter_win():
    assert categories_for(ASCENDANCY, ("alternate-win-condition",), ALL) == {"counter_win"}
    assert "counter_win" in categories_for(PINNACLE, ("alternate-win-condition", "mana-sink"), ALL)
    assert "counter_win" not in categories_for(BALLISTA, ("mana-sink",), ALL)


def test_cast_damage():
    assert categories_for(GUTTERSNIPE, (), ALL) == {"cast_damage"}
    assert "cast_damage" not in categories_for(PURPHOROS, (), ALL)


def test_empty_library_win_requires_the_tag_when_checked():
    for c in (ORACLE, LAB_MAN, JACE):
        assert categories_for(c, ("alternate-win-condition",), ALL) == {"empty_library_win"}, c.name
        assert categories_for(c, (), ALL) == frozenset(), c.name
        assert categories_for(c, (), frozenset()) == {"empty_library_win"}, c.name


def test_life_drain_has_no_tag_check():
    assert categories_for(VITO, (), ALL) == {"life_drain"}
    assert "life_drain" not in categories_for(EXSANGUINATE, ("lifedrain",), ALL)


def test_landfall_payoff_and_tokens():
    assert categories_for(HAGRA, (), ALL) == {"landfall_payoff"}
    assert categories_for(OB_NIX, (), ALL) == {"landfall_payoff"}
    assert categories_for(FIELD, (), ALL) == {"landfall_tokens"}
    assert categories_for(SCUTE, (), ALL) == {"landfall_tokens"}
    assert "landfall_payoff" not in categories_for(SCUTE, (), ALL)


def test_back_face_text_is_scanned():
    dfc = make_card("Front // Back", layout="modal_dfc", oracle_text="", mana_cost="",
                    card_faces=[{"name": "Front", "mana_cost": "{1}{B}", "type_line": "Sorcery", "oracle_text": "Draw a card."},
                                {"name": "Back", "mana_cost": "{3}{B}", "type_line": "Enchantment",
                                 "oracle_text": "Whenever another creature you control dies, each opponent loses 1 life."}])
    assert categories_for(CardData.from_scryfall(dfc), (), ALL) == {"drain"}


def _facts(cards, tags=None):
    text = "1 Grizzly Bears\n\n" + "".join(f"1 {c.name}\n" for c in cards)
    bears = CardData.from_scryfall(make_card("Grizzly Bears", type_line="Legendary Creature — Bear", mana_cost="{1}{G}", cmc=2.0))
    res = Resolution({c.name: c for c in [bears, *cards]}, [], 0, None)
    cache = full_tag_cache(**tags) if tags is not None else None
    return build_facts(parse_decklist(text), res, None, "offline", "t.txt", tag_cache=cache)


def test_detect_groups_cards_and_applies_both_tag_checks():
    p = detect(_facts([BALLISTA, EXSANGUINATE, ORACLE, TREMORS, SOL_RING], tags={"mana-sink": ["Walking Ballista"], "alternate-win-condition": ["Thassa's Oracle"]}))
    assert isinstance(p, DeckPayoffs)
    assert set(p.by_category) == set(PAYOFF_CATEGORIES)
    assert p.by_category["mana_sink"] == ["Exsanguinate", "Walking Ballista"]
    assert p.by_category["empty_library_win"] == ["Thassa's Oracle"]
    assert p.by_category["etb_damage"] == ["Impact Tremors"] and p.by_category["drain"] == []
    assert p.tag_checked == ("empty_library_win", "mana_sink") and p.notes == []
    assert p.cards_for(["etb_damage", "mana_sink"]) == ["Exsanguinate", "Impact Tremors", "Walking Ballista"]
    assert p.to_dict() == {"by_category": p.by_category, "tag_checked": ["empty_library_win", "mana_sink"], "notes": []}


def test_detect_without_tags_is_pattern_only_and_says_so():
    p = detect(_facts([BALLISTA, ORACLE]))
    assert p.by_category["mana_sink"] == ["Walking Ballista"] and p.by_category["empty_library_win"] == ["Thassa's Oracle"]
    assert p.tag_checked == ()
    assert len(p.notes) == 1 and "tags not requested" in p.notes[0] and "mana_sink" in p.notes[0] and "empty_library_win" in p.notes[0]


def test_detect_with_facts_that_predate_a_slug_degrades_loudly():
    facts = _facts([BALLISTA, ORACLE], tags={"mana-sink": ["Walking Ballista"]})
    facts.fetched["tag_table"] = "ramp,tutor,mana-sink"   # alternate-win-condition unknown when these facts were built
    p = detect(facts)
    assert p.tag_checked == ("mana_sink",)
    assert p.by_category["empty_library_win"] == ["Thassa's Oracle"]
    assert p.notes == ["payoff tag check skipped for empty_library_win: facts predate the alternate-win-condition tag"]


def test_commander_is_scanned_too():
    oracle_cmd = CardData.from_scryfall(make_card("Thassa's Oracle", oracle_text=ORACLE.oracle_text, mana_cost="{U}{U}", type_line="Legendary Creature — Merfolk Wizard"))
    res = Resolution({"Thassa's Oracle": oracle_cmd, "Sol Ring": SOL_RING}, [], 0, None)
    facts = build_facts(parse_decklist("1 Thassa's Oracle\n\n1 Sol Ring\n"), res, None, "offline", "t.txt", tag_cache=full_tag_cache(**{"alternate-win-condition": ["Thassa's Oracle"]}))
    assert detect(facts).by_category["empty_library_win"] == ["Thassa's Oracle"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_payoffs.py -q`
Expected: `ModuleNotFoundError: No module named 'edhpower.payoffs'`.

- [ ] **Step 3: Implement `src/edhpower/payoffs.py`**

```python
"""Payoff detection: which cards in the deck turn an infinite resource into a win.

Patterns are ported from scrollvault.net bracket.js v393 (genPayoffCats and friends), widened where a
card scrollvault curates by name fails the pattern. No card names appear here. Two categories also
require a Scryfall oracle tag when the facts were built with that tag known; a facts file that
predates the tag gets pattern-only detection for the category and a note saying so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from edhpower.config import PAYOFF_CATEGORIES
from edhpower.facts import DeckFacts
from edhpower.scryfall import CardData

TAG_CHECKS: dict[str, str] = {"mana_sink": "mana-sink", "empty_library_win": "alternate-win-condition"}

CATEGORY_LABELS: dict[str, str] = {
    "mana_sink": "mana sink",
    "drain": "death-trigger drain",
    "etb_damage": "ETB damage",
    "go_wide": "go-wide finisher",
    "token_drain": "token drain",
    "counter_win": "counter win",
    "cast_damage": "cast damage",
    "empty_library_win": "empty-library win",
    "life_drain": "lifegain drain",
    "landfall_payoff": "landfall drain",
    "landfall_tokens": "landfall tokens (fuel)",
}

_OPP_LOSS = r"(?:(?:each opponent|target opponent|target player|each player) loses? (?:\d+|x|one|two|that much) life|deals? (?:\d+|x|one|two|that much) damage to (?:each opponent|each player|any target|target (?:player|opponent)))"
_NOT_THEIRS = r"(?:(?!opponent|don't own|attacking|blocking)[^.])*?"

_X_SPELL_EFFECT = re.compile(r"deals x damage[^.]*divided|deals x damage to each (?:opponent|player|of (?:them|those|these))|each opponent loses x life|repeat the following process x times")
_SINK_PINGER = re.compile(r"remove a \+1/\+1 counter[^.]*deals? \d+ damage to any target")
_SINK_COUNTER_FEED = re.compile(r"put[^.]*\+1/\+1 counter")
_SINK_TRAMPLE = re.compile(r"\}: [^.]*creatures you control get \+\d+/\+\d+ and (?:gain|have) trample")
_SINK_X_ACTIVATION = re.compile(r"\{x\}[^:\n]*:[^.\n]*(?:each opponent loses|deals x damage)")
_DRAIN = re.compile(r"whenever (?:this creature or )?(?:a|an|another|one or more)\b" + _NOT_THEIRS + r"\bcreatures?\b" + _NOT_THEIRS + r"\bdie(?:s)?\b[^.]*?" + _OPP_LOSS)
_ETB_DAMAGE = re.compile(r"whenever (?:a|another)[^.]*creature[^.]*enters[^.]*(?:deals \d+ damage to each opponent|each opponent loses \d+ life)")
_GO_WIDE = re.compile(r"creatures you control (?:get \+[0-9x]+/\+[0-9x]+ and (?:gain|have) trample|gain trample and get \+[0-9x]+/\+[0-9x]+)")
_TOKEN_DRAIN = re.compile(r"whenever (?:one or more )?tokens? you control (?:enters?|are created)[^.]*each opponent loses|whenever you create[^.]*tokens?[^.]*each opponent loses")
_COUNTER_WIN = re.compile(r"\+1/\+1 counters?[^.]*you win the game|(?:twenty|\d+) or more [a-z+/1 ]*counters on (?:it|this [a-z]+)[^.]*you win the game")
_CAST_DAMAGE = re.compile(r"whenever you cast (?:an?|your) (?:instant|sorcery|noncreature)[^.]* spell[^.]*deals \d+ damage to each opponent")
_EMPTY_LIBRARY = re.compile(r"draw a card while your library has no cards|no cards in it, you win the game|library has no cards in it[^.]*win the game|number of cards in your library, you win the game")
_LIFE_DRAIN = re.compile(r"whenever you gain life[^.]*?" + _OPP_LOSS)
_LANDFALL = r"(?:landfall|whenever (?:a|this land or another) land(?: you control)? enters)"
_LANDFALL_PAYOFF = re.compile(_LANDFALL + r"[\s\S]{0,160}?(?:each opponent loses|target (?:player|opponent) loses?|deals? \d+ damage to (?:each opponent|any target))")
_LANDFALL_TOKENS = re.compile(_LANDFALL + r"[^.]*create[^.]*token")


@dataclass(frozen=True)
class DeckPayoffs:
    by_category: dict[str, list[str]]
    tag_checked: tuple[str, ...]
    notes: list[str]

    def cards_for(self, categories: Iterable[str]) -> list[str]:
        out: set[str] = set()
        for c in categories:
            out.update(self.by_category.get(c, ()))
        return sorted(out)

    def to_dict(self) -> dict[str, Any]:
        return {"by_category": {k: list(v) for k, v in self.by_category.items()}, "tag_checked": list(self.tag_checked), "notes": list(self.notes)}


def _text(card: CardData) -> str:
    if card.faces:
        return " ".join(f.oracle_text for f in card.faces).lower()
    return card.oracle_text.lower()


def _cost(card: CardData) -> str:
    if card.faces and not card.mana_cost:
        return "".join(f.mana_cost for f in card.faces).lower()
    return card.mana_cost.lower()


def _mana_sink(text: str, cost: str, tagged: bool, checked: bool) -> bool:
    if "{x}" in cost and _X_SPELL_EFFECT.search(text):
        return True   # X spell: no tag needed
    if checked and not tagged:
        return False
    if _SINK_PINGER.search(text) and ("{x}" in cost or _SINK_COUNTER_FEED.search(text)):
        return True
    if _SINK_TRAMPLE.search(text) or _SINK_X_ACTIVATION.search(text):
        return True
    return False


def categories_for(card: CardData, tags: tuple[str, ...], tag_checked: frozenset[str]) -> frozenset[str]:
    """Payoff categories this card provides. `tag_checked` names the categories whose tag is required."""
    text, cost = _text(card), _cost(card)
    found: set[str] = set()
    if _mana_sink(text, cost, "mana-sink" in tags, "mana_sink" in tag_checked):
        found.add("mana_sink")
    if _DRAIN.search(text):
        found.add("drain")
    if _ETB_DAMAGE.search(text):
        found.add("etb_damage")
    if _GO_WIDE.search(text):
        found.add("go_wide")
    if _TOKEN_DRAIN.search(text):
        found.add("token_drain")
    if _COUNTER_WIN.search(text):
        found.add("counter_win")
    if _CAST_DAMAGE.search(text):
        found.add("cast_damage")
    if _EMPTY_LIBRARY.search(text) and ("alternate-win-condition" in tags or "empty_library_win" not in tag_checked):
        found.add("empty_library_win")
    if _LIFE_DRAIN.search(text):
        found.add("life_drain")
    if _LANDFALL_PAYOFF.search(text):
        found.add("landfall_payoff")
    if _LANDFALL_TOKENS.search(text):
        found.add("landfall_tokens")
    return frozenset(found)


def detect(facts: DeckFacts) -> DeckPayoffs:
    notes: list[str] = []
    checked: set[str] = set()
    if facts.tags_status != "ok":
        notes.append(f"payoff tag check skipped for {', '.join(sorted(TAG_CHECKS))}: {facts.tags_status}")
    else:
        known = set(str(facts.fetched.get("tag_table") or "").split(","))
        for category, slug in sorted(TAG_CHECKS.items()):
            if slug in known:
                checked.add(category)
            else:
                notes.append(f"payoff tag check skipped for {category}: facts predate the {slug} tag")
    by_category: dict[str, set[str]] = {c: set() for c in PAYOFF_CATEGORIES}
    for e in facts.entries:
        tags = facts.profiles[e.name].tags if e.name in facts.profiles else ()
        for c in categories_for(e.card, tags, frozenset(checked)):
            by_category[c].add(e.name)
    return DeckPayoffs({c: sorted(v) for c, v in by_category.items()}, tuple(sorted(checked)), notes)
```

- [ ] **Step 4: Run the payoff tests**

Run: `uv run pytest tests/test_payoffs.py -q`
Expected: all pass. If a pattern test fails, fix the pattern in `payoffs.py` (never the oracle text in the test) and re-run until green.

- [ ] **Step 5: Run the suite and commit**

Run: `uv run pytest -q` → all pass.

```bash
git add src/edhpower/payoffs.py tests/test_payoffs.py
git commit -m "payoffs: detect payoff categories from oracle text with tag checks

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Line classification in `sim/combos.py`

**Files:**
- Modify: `src/edhpower/sim/combos.py` (whole file)
- Test: `tests/test_sim_combos.py`

**Interfaces:**
- Consumes: `SimConfig.payoff_*`, `SimConfig.lock_only`, `payoffs.DeckPayoffs`, `payoffs.detect`.
- Produces:

```python
STATUSES = ("direct", "payoff", "no_payoff", "unmapped")   # lock_only lines are skipped, not simulated

@dataclass(frozen=True)
class PayoffNeed:
    candidates: frozenset[str]   # card names anywhere in the deck (including pieces)
    hand_ok: bool                # True when some resource is in cfg.payoff_hand_ok

@dataclass(frozen=True)
class SimLine:
    id: str; label: str; pieces: tuple[LinePiece, ...]; extra_mana: int; lethal: bool
    status: str; resources: tuple[str, ...]; payoff: PayoffNeed | None

def resources_of(produces: Iterable[str], cfg: SimConfig) -> tuple[str, ...]
def is_lock_only(produces: Iterable[str], cfg: SimConfig) -> bool
def classify(line: ComboLine, cfg: SimConfig, payoffs: DeckPayoffs) -> tuple[str, tuple[str, ...], PayoffNeed | None]
def select_lines(facts: DeckFacts, cfg: SimConfig, payoffs: DeckPayoffs | None = None) -> tuple[list[SimLine], list[SkippedLine]]
def payoff_ready(line: SimLine, board: set[str], hand: set[str]) -> bool
```

`select_lines` with `payoffs=None` calls `detect(facts)` itself, so every existing caller keeps working.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sim_combos.py` (the file's `_line` and `_facts` helpers stay; add the payoff cards to `_facts` by extending its `cards` list and deck text as shown):

```python
from edhpower.payoffs import detect
from edhpower.sim.combos import PayoffNeed, classify, is_lock_only, payoff_ready, resources_of

TREMORS = make_card("Impact Tremors", cmc=2.0, mana_cost="{1}{R}", type_line="Enchantment", colors=["R"],
                    oracle_text="Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.")
BALLISTA = make_card("Walking Ballista", cmc=0.0, mana_cost="{X}{X}", type_line="Artifact Creature — Construct", power="0", toughness="0",
                     oracle_text="This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nRemove a +1/+1 counter from this creature: It deals 1 damage to any target.")
FIELD = make_card("Field of the Dead", cmc=0.0, mana_cost="", type_line="Land", produced_mana=["C"],
                  oracle_text="This land enters tapped.\n{T}: Add {C}.\nWhenever this land or another land you control enters, if you control seven or more lands with different names, create a 2/2 black Zombie creature token.")
HOOF = make_card("Craterhoof Behemoth", cmc=8.0, mana_cost="{5}{G}{G}{G}", type_line="Creature — Beast", power="5", toughness="5", colors=["G"],
                 oracle_text="Haste\nWhen this creature enters, creatures you control gain trample and get +X/+X until end of turn, where X is the number of creatures you control.")


def _facts_with(lines, extra_cards=(), tags=None):
    """Like _facts, plus extra make_card() objects in the 99."""
    base = _facts(lines)
    if not extra_cards:
        return base
    cards = [make_card("Ulalek, Fused Atrocity", cmc=5.0, mana_cost="{C/W}{C/U}{C/B}{C/R}{C/G}", type_line="Legendary Creature — Eldrazi", power="2", toughness="5"),
             make_card("Basalt Monolith", cmc=3.0, mana_cost="{3}"), make_card("Forsaken Monument", cmc=5.0, mana_cost="{5}"),
             make_card("Kinnan, Bonder Prodigy", cmc=2.0, mana_cost="{G}{U}", type_line="Legendary Creature — Human Druid", colors=["G", "U"]),
             make_card("Strionic Resonator", cmc=2.0, mana_cost="{2}"), make_card("Spawn-Gang Commander", cmc=5.0, mana_cost="{4}{R}", type_line="Creature — Eldrazi Goblin", colors=["R"]),
             make_card("Wastes", cmc=0.0, mana_cost="", type_line="Basic Land", produced_mana=["C"]), *extra_cards]
    deck = ("1 Ulalek, Fused Atrocity\n\n1 Basalt Monolith\n1 Forsaken Monument\n1 Kinnan, Bonder Prodigy\n1 Strionic Resonator\n1 Spawn-Gang Commander\n30 Wastes\n"
            + "".join(f"1 {c['name']}\n" for c in extra_cards))
    return sim_facts(deck, cards, tags if tags is not None else {}, base.combos)


def test_resources_of_folds_near_infinite_and_ignores_unknown_features():
    assert resources_of(["Infinite colorless mana", "Near-infinite creature ETB", "Infinite landfall triggers", "Infinite storm count"], CFG) == ("mana", "etb", "landfall", "storm")
    assert resources_of(["Infinite tapped land tokens", "Lock"], CFG) == ()
    assert resources_of([], CFG) == ()


def test_is_lock_only():
    assert is_lock_only(["Prevent all damage that would be dealt to you", "Lock"], CFG)
    assert not is_lock_only(["Lock", "Infinite colorless mana"], CFG)
    assert not is_lock_only([], CFG)


def test_classify_direct_payoff_no_payoff_unmapped():
    mana = _line("m", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")])
    direct = _line("d", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], produces=("Infinite colorless mana", "Infinite damage"))
    empty = _line("e", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], produces=())
    no_sink = detect(_facts_with([mana]))
    with_sink = detect(_facts_with([mana], [BALLISTA], tags={"mana-sink": ["Walking Ballista"]}))
    assert classify(direct, CFG, no_sink) == ("direct", ("mana",), None)
    assert classify(mana, CFG, no_sink) == ("no_payoff", ("mana",), None)
    assert classify(mana, CFG, with_sink) == ("payoff", ("mana",), PayoffNeed(frozenset({"Walking Ballista"}), True))
    assert classify(empty, CFG, no_sink) == ("unmapped", (), None)


def test_classify_battlefield_only_resource_and_self_paying_piece():
    etb = _line("etb", [("Kinnan, Bonder Prodigy", "B"), ("Basalt Monolith", "B")], produces=("Infinite creature ETB",))
    p = detect(_facts_with([etb], [TREMORS]))
    assert classify(etb, CFG, p) == ("payoff", ("etb",), PayoffNeed(frozenset({"Impact Tremors"}), False))
    # the engine's own piece is a payoff: Purphoros-style text on a piece
    piece_payoff = make_card("Kinnan, Bonder Prodigy", cmc=2.0, mana_cost="{G}{U}", type_line="Legendary Creature — Human Druid", colors=["G", "U"],
                             oracle_text="Whenever another creature you control enters, this creature deals 2 damage to each opponent.")
    import dataclasses
    from edhpower.scryfall import CardData
    facts = _facts_with([etb])
    facts.entries = [dataclasses.replace(e, card=CardData.from_scryfall(piece_payoff)) if e.name == "Kinnan, Bonder Prodigy" else e for e in facts.entries]
    status, _, need = classify(etb, CFG, detect(facts))
    assert status == "payoff" and need.candidates == frozenset({"Kinnan, Bonder Prodigy"})


def test_classify_landfall_tokens_is_fuel_only_with_a_go_wide_payoff():
    land = _line("lf", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], produces=("Infinite landfall triggers",))
    assert classify(land, CFG, detect(_facts_with([land], [FIELD]))) == ("no_payoff", ("landfall",), None)
    status, _, need = classify(land, CFG, detect(_facts_with([land], [FIELD, HOOF])))
    assert status == "payoff" and need == PayoffNeed(frozenset({"Field of the Dead"}), False)


def test_select_lines_skips_lock_only_and_carries_status():
    lock = _line("lock", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], produces=("Prevent all damage that would be dealt to you", "Lock"))
    mana = _line("mana", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")], popularity=3)
    direct = _line("direct", [("Kinnan, Bonder Prodigy", "B"), ("Basalt Monolith", "B")], produces=("Infinite damage",), popularity=2)
    simulated, skipped = select_lines(_facts_with([lock, mana, direct]), CFG)
    assert [(l.id, l.status, l.resources, l.lethal, l.payoff) for l in simulated] == [("mana", "no_payoff", ("mana",), False, None), ("direct", "direct", (), True, None)]
    assert [(s.label, s.reason) for s in skipped] == [("Basalt Monolith + Forsaken Monument", "lock only")]


def test_select_lines_accepts_precomputed_payoffs():
    mana = _line("mana", [("Basalt Monolith", "B"), ("Forsaken Monument", "B")])
    facts = _facts_with([mana], [BALLISTA], tags={"mana-sink": ["Walking Ballista"]})
    (line,), _ = select_lines(facts, CFG, detect(facts))
    assert line.status == "payoff" and line.payoff.hand_ok


def test_payoff_ready_zone_rules():
    board_only = SimLine("x", "x", (), 0, False, "payoff", ("etb",), PayoffNeed(frozenset({"Impact Tremors"}), False))
    hand_ok = SimLine("y", "y", (), 0, False, "payoff", ("mana",), PayoffNeed(frozenset({"Walking Ballista"}), True))
    none = SimLine("z", "z", (), 0, False, "no_payoff", ("mana",), None)
    assert payoff_ready(board_only, {"Impact Tremors"}, set()) and not payoff_ready(board_only, set(), {"Impact Tremors"})
    assert payoff_ready(hand_ok, set(), {"Walking Ballista"}) and payoff_ready(hand_ok, {"Walking Ballista"}, set())
    assert not payoff_ready(none, {"Walking Ballista"}, {"Walking Ballista"})
```

Also update the existing `test_two_and_three_card_lines_are_selected_and_the_rest_explained`: its `two` line produces `Infinite colorless mana` and the deck has no sink, so add `assert two.status == "no_payoff" and three.status == "direct"` after the existing `lethal` assertions.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_sim_combos.py -q`
Expected: `ImportError: cannot import name 'PayoffNeed'`.

- [ ] **Step 3: Rewrite `src/edhpower/sim/combos.py`**

```python
"""Which Spellbook lines the simulator plays, when a line counts as assembled, and whether it can win.

Scoped to what the engine can do: 2- and 3-card `included` variants whose pieces live on the
battlefield, in hand or in the command zone, with no `requires` templates. Everything else is
reported as not simulated, never assumed free. A line's status says how it can become lethal:
`direct` (produces a win), `payoff` (produces a resource the deck can convert; the candidates are
named), `no_payoff` (resource with nothing to convert it), `unmapped` (no recognised product).
Lock-only lines are skipped. Ported from scrollvault's genSimLines payoff slot, in spirit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from edhpower.config import SimConfig
from edhpower.facts import DeckFacts
from edhpower.payoffs import DeckPayoffs, detect
from edhpower.sim.mana import parse_cost
from edhpower.spellbook import ComboLine

ALLOWED_ZONES = frozenset({"B", "H", "C"})
STATUSES: tuple[str, ...] = ("direct", "payoff", "no_payoff", "unmapped")


@dataclass(frozen=True)
class LinePiece:
    name: str
    zones: frozenset[str]


@dataclass(frozen=True)
class PayoffNeed:
    candidates: frozenset[str]
    hand_ok: bool


@dataclass(frozen=True)
class SimLine:
    id: str
    label: str
    pieces: tuple[LinePiece, ...]
    extra_mana: int
    lethal: bool
    status: str
    resources: tuple[str, ...]
    payoff: PayoffNeed | None


@dataclass(frozen=True)
class SkippedLine:
    label: str
    reason: str


def _label(line: ComboLine) -> str:
    return " + ".join(line.piece_names)


def resources_of(produces: Iterable[str], cfg: SimConfig) -> tuple[str, ...]:
    """Resources a line's products map to, in rule order, deduplicated. Unknown products map to nothing."""
    found: list[str] = []
    for feature in produces:
        text = feature.lower().replace("near-infinite", "infinite")
        for resource, pattern in cfg.payoff_resources:
            if pattern.search(text):
                if resource not in found:
                    found.append(resource)
                break
    return tuple(found)


def is_lock_only(produces: Iterable[str], cfg: SimConfig) -> bool:
    items = list(produces)
    return bool(items) and all(cfg.lock_only.match(p.strip()) for p in items)


def _is_direct(line: ComboLine, cfg: SimConfig) -> bool:
    return any(f in feat.lower() for feat in line.produces for f in cfg.lethal_features)


def classify(line: ComboLine, cfg: SimConfig, payoffs: DeckPayoffs) -> tuple[str, tuple[str, ...], PayoffNeed | None]:
    resources = resources_of(line.produces, cfg)
    if _is_direct(line, cfg):
        return "direct", resources, None
    if not resources:
        return "unmapped", resources, None
    candidates: set[str] = set()
    for res in resources:
        for category in cfg.payoff_converts.get(res, ()):
            chain = cfg.payoff_chained.get(category)
            if chain and not payoffs.cards_for(chain):
                continue   # fuel without a finisher
            candidates.update(payoffs.by_category.get(category, ()))
    if not candidates:
        return "no_payoff", resources, None
    hand_ok = any(res in cfg.payoff_hand_ok for res in resources)
    return "payoff", resources, PayoffNeed(frozenset(candidates), hand_ok)


def _skip_reason(line: ComboLine, cfg: SimConfig) -> str | None:
    n = len(line.pieces)
    if n not in (2, 3):
        return "4+ pieces"
    for p in line.pieces:
        bad = set(p.zones) - ALLOWED_ZONES
        if bad:
            return f"piece in zone {''.join(sorted(bad))}"
    if line.templates:
        return f"templated: {line.templates[0].name}"
    if n == 2 and line.notable_prerequisites.strip():
        return "notable prerequisites"
    if is_lock_only(line.produces, cfg):
        return "lock only"
    return None


def select_lines(facts: DeckFacts, cfg: SimConfig, payoffs: DeckPayoffs | None = None) -> tuple[list[SimLine], list[SkippedLine]]:
    if facts.combos is None:
        return [], []
    payoffs = payoffs if payoffs is not None else detect(facts)
    ordered = sorted(facts.combos.included, key=lambda l: (-(l.popularity if l.popularity is not None else -1), l.id))
    simulated: list[SimLine] = []
    skipped: list[SkippedLine] = []
    taken = {2: 0, 3: 0}
    caps = {2: cfg.max_two_card_lines, 3: cfg.max_three_card_lines}
    for line in ordered:
        reason = _skip_reason(line, cfg)
        if reason is None and taken[len(line.pieces)] >= caps[len(line.pieces)]:
            reason = "over cap"
        if reason is not None:
            skipped.append(SkippedLine(_label(line), reason))
            continue
        taken[len(line.pieces)] += 1
        extra = line.mana_value_needed if isinstance(line.mana_value_needed, int) else parse_cost(line.mana_needed).total
        status, resources, need = classify(line, cfg, payoffs)
        pieces = tuple(LinePiece(p.name, frozenset(p.zones) or frozenset({"B"})) for p in line.pieces)
        simulated.append(SimLine(line.id, _label(line), pieces, extra, status == "direct", status, resources, need))
    return simulated, skipped


def payoff_ready(line: SimLine, board: set[str], hand: set[str]) -> bool:
    """True when the line's payoff condition holds: a candidate on the battlefield, or in hand when hand_ok."""
    if line.payoff is None:
        return False
    if line.payoff.candidates & board:
        return True
    return line.payoff.hand_ok and bool(line.payoff.candidates & hand)


def pieces_to_cast(line: SimLine, board: set[str], hand: set[str], command_zone: set[str]) -> list[str] | None:
    to_cast: list[str] = []
    for p in line.pieces:
        if p.name in board:
            if p.zones == frozenset({"H"}):
                return None
            continue
        if p.name in command_zone:
            if "C" in p.zones:
                continue
            if "B" in p.zones:
                to_cast.append(p.name)
                continue
            return None
        if p.name in hand:
            if "H" in p.zones:
                continue
            if "B" in p.zones:
                to_cast.append(p.name)
                continue
        return None
    return to_cast


def missing_pieces(line: SimLine, board: set[str], hand: set[str], command_zone: set[str]) -> list[str]:
    return [p.name for p in line.pieces if p.name not in board and p.name not in hand and p.name not in command_zone]
```

- [ ] **Step 4: Run the combos tests, then the suite**

Run: `uv run pytest tests/test_sim_combos.py -q` → all pass.
Run: `uv run pytest -q` → all pass. `test_sim_engine.py` constructs `SimLine` only via `select_lines`, so the new fields do not break it; if any test builds `SimLine(...)` positionally, add `"no_payoff", (), None`.

- [ ] **Step 5: Commit**

```bash
git add src/edhpower/sim/combos.py tests/test_sim_combos.py
git commit -m "sim: classify Spellbook lines by payoff status; skip lock-only lines

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Engine — lethal only with the payoff, re-checked each turn

**Files:**
- Modify: `src/edhpower/sim/engine.py:34-52` (`Game.__init__`), `:280-305` (`_try_combo`), `:349-374` (`take_turn`)
- Test: `tests/test_sim_engine.py`

**Interfaces:**
- Consumes: `combos.payoff_ready`, `SimLine.status/payoff/lethal`.
- Produces: `Game.pending_payoff: set[str]`; `GameRecord` unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sim_engine.py`:

```python
from edhpower.payoffs import detect

BALLISTA_20 = make_card("Walking Ballista", cmc=20.0, mana_cost="{20}", type_line="Artifact Creature — Construct", power="0", toughness="0",
                        oracle_text="This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nRemove a +1/+1 counter from this creature: It deals 1 damage to any target.")
TREMORS_2 = make_card("Impact Tremors", cmc=2.0, mana_cost="{2}", type_line="Enchantment",
                      oracle_text="Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.")
TREMORS_20 = make_card("Impact Tremors", cmc=20.0, mana_cost="{20}", type_line="Enchantment",
                       oracle_text="Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.")


def _payoff_line(produces):
    line = ComboLine("pl", (ComboPiece("Basalt Monolith", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), tuple(produces), "", 0, "R", 1, "", "")
    return ComboData("C", [line], 0, {}, {"pl": ComboFlags("pl", True, False, 5, False, False, False, False, True)}, "R", "2026-09-10T00:00:00Z")


def _deck_lines(commander, entries, combos, tags=None):
    cards = [commander] + [c for c, _ in entries]
    text = f"1 {commander['name']}\n\n" + "".join(f"{n} {c['name']}\n" for c, n in entries)
    facts = sim_facts(text, cards, tags if tags is not None else {}, combos)
    return build_sim_deck(facts, CFG), select_lines(facts, CFG, detect(facts))[0]


def _staged_game(deck, lines, payoff_name):
    """Turn 5 board of 8 Wastes; both pieces in hand; payoff drawn on turn 8 (library pops from the end)."""
    g = _game(deck, lines)
    g.turn = 5
    g.board = [Perm(deck.cards["Wastes"], 0) for _ in range(8)]
    g.hand = ["Basalt Monolith", "Forsaken Monument"]
    g.library = [payoff_name, "Wastes", "Wastes"]
    return g


def _run_to(g, turn):
    while g.turn < turn:
        g.take_turn()
    return g.record.clocks


def test_payoff_line_in_hand_counts_for_infinite_mana():
    deck, lines = _deck_lines(CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1), (BALLISTA_20, 1)], _payoff_line(["Infinite colorless mana"]), tags={"mana-sink": ["Walking Ballista"]})
    assert lines[0].status == "payoff" and lines[0].payoff.hand_ok
    g = _staged_game(deck, lines, "Walking Ballista")
    clocks = _run_to(g, 8)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] == 8   # Ballista costs 20: never cast, but in hand is enough


def test_payoff_line_needs_the_battlefield_for_etb():
    deck, lines = _deck_lines(CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1), (TREMORS_2, 1)], _payoff_line(["Infinite creature ETB"]))
    assert lines[0].status == "payoff" and not lines[0].payoff.hand_ok
    clocks = _run_to(_staged_game(deck, lines, "Impact Tremors"), 8)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] == 8   # drawn and cast on turn 8, checked after the main phase
    deck, lines = _deck_lines(CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1), (TREMORS_20, 1)], _payoff_line(["Infinite creature ETB"]))
    clocks = _run_to(_staged_game(deck, lines, "Impact Tremors"), 12)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] is None   # in hand only: not enough for a battlefield payoff


def test_no_payoff_line_never_goes_lethal_and_direct_line_does_at_once():
    deck, lines = _deck_lines(CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1)], _payoff_line(["Infinite colorless mana"]))
    assert lines[0].status == "no_payoff"
    clocks = _run_to(_staged_game(deck, lines, "Wastes"), 12)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] is None
    deck, lines = _deck_lines(CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1)], _payoff_line(["Infinite colorless mana", "Infinite damage"]))
    clocks = _run_to(_staged_game(deck, lines, "Wastes"), 12)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] == 6


def test_payoff_already_on_board_stamps_lethal_at_assembly():
    deck, lines = _deck_lines(CMD, [(WASTES, 30), (BASALT, 1), (MONUMENT, 1), (TREMORS_2, 1)], _payoff_line(["Infinite creature ETB"]))
    g = _staged_game(deck, lines, "Wastes")
    g.board.append(Perm(deck.cards["Impact Tremors"], 0))
    clocks = _run_to(g, 7)
    assert clocks["combo"] == 6 and clocks["lethal_combo"] == 6
```

Note for the implementer: `_staged_game` relies on `MAIN_ORDER` casting Basalt Monolith as a `rock` and Forsaken Monument as a `reducer` on turn 6 (8 Wastes + the turn-6 land = 9 mana), after which `_try_combo` finds both pieces on the battlefield. If the first assertion gives `combo == 7`, print `g.board` after turn 6 to see which piece was held, and adjust the Wastes count on the staged board rather than the expectations.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_sim_engine.py -q -k "payoff or no_payoff"`
Expected: the first two tests fail with `lethal_combo` being `None` where `8` is expected (the engine ignores payoffs today); the no-payoff test may already pass for the `no_payoff` half but fail for `direct` only if the lethal flag broke — expect at least 3 failures.

- [ ] **Step 3: Implement**

In `src/edhpower/sim/engine.py`:

Change the import line to:

```python
from edhpower.sim.combos import SimLine, missing_pieces, payoff_ready, pieces_to_cast
```

In `Game.__init__`, after `self.fired: set[str] = set()` add:

```python
        self.pending_payoff: set[str] = set()
```

Replace the tail of `_try_combo` (from `self.fired.add(line.id)` to `return True`) with:

```python
            self.fired.add(line.id)
            self._stamp("combo")
            board_now, hand_now, _ = self._zones()
            if line.lethal or payoff_ready(line, board_now, hand_now):
                self._stamp("lethal_combo")
            elif line.payoff is not None:
                self.pending_payoff.add(line.id)
            return True
```

Add a method after `_try_combo`:

```python
    def _check_pending_payoffs(self) -> None:
        """A fired engine whose payoff arrived later: the lethal clock stamps the turn the condition first holds."""
        if not self.pending_payoff:
            return
        board, hand, _ = self._zones()
        for line in self.lines:
            if line.id in self.pending_payoff and payoff_ready(line, board, hand):
                self._stamp("lethal_combo")
                self.pending_payoff.clear()
                return
```

In `take_turn`, directly after `self._main_phase()` and before the second `_commander_castable` check, add:

```python
        self._check_pending_payoffs()
```

- [ ] **Step 4: Run the engine tests, then the suite**

Run: `uv run pytest tests/test_sim_engine.py -q` → all pass.
Run: `uv run pytest -q` → all pass (sim version still 1; goldens unaffected because the fixtures' lines either carry a direct win or have no payoff… if `test_golden_values` fails here, a fixture deck has a line that just became `payoff` with a candidate: that is the intended semantic change, and it is baselined in Task 10. Record which fixture moved in the commit message.)

- [ ] **Step 5: Commit**

```bash
git add src/edhpower/sim/engine.py tests/test_sim_engine.py
git commit -m "sim: lethal_combo requires the payoff; fired engines re-checked each turn

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `SimResult` carries line statuses and payoffs

**Files:**
- Modify: `src/edhpower/sim/__init__.py` (`SimResult`, `simulate`)
- Test: `tests/test_sim.py`

**Interfaces:**
- Produces: `SimResult.line_status: list[dict[str, Any]]` with keys `label`, `status`, `resources` (list), `categories` (payoff categories that would convert those resources, in config order, deduplicated), `candidates` (sorted list), `hand_ok` (bool); `SimResult.payoffs: dict[str, list[str]]` (= `DeckPayoffs.by_category`); `simulate(facts, cfg, iterations, tipping_target, payoffs: DeckPayoffs | None = None)`. `DeckPayoffs.notes` are appended to `SimResult.notes`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sim.py`:

```python
def test_result_carries_line_statuses_and_payoffs():
    from edhpower.payoffs import detect
    facts = fixture_facts("ulalek-bracket4-v2")
    r = simulate(facts, CFG, 20, tipping_target=3)
    assert r.payoffs == detect(facts).by_category
    assert len(r.line_status) == len(r.lines_simulated)
    for row, label in zip(r.line_status, r.lines_simulated):
        assert row["label"] == label and row["status"] in ("direct", "payoff", "no_payoff", "unmapped")
        assert set(row) == {"label", "status", "resources", "categories", "candidates", "hand_ok"}
        assert all(c in r.payoffs for c in row["categories"])
        assert (row["status"] == "payoff") == bool(row["candidates"])
    d = r.to_dict()
    assert d["line_status"] == r.line_status and d["payoffs"] == r.payoffs


def test_payoff_notes_reach_the_result():
    import dataclasses
    facts = dataclasses.replace(fixture_facts("precon-eldrazi-unbound"), tags_status="skipped (--no-tags)")
    r = simulate(facts, CFG, 10, tipping_target=5)
    assert any("payoff tag check skipped" in n for n in r.notes)


def test_precomputed_payoffs_give_identical_results():
    from edhpower.payoffs import detect
    facts = fixture_facts("ulalek-bracket3-v2")
    assert simulate(facts, CFG, 30, 4, payoffs=detect(facts)).to_dict() == simulate(facts, CFG, 30, 4).to_dict()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_sim.py -q` → `AttributeError: 'SimResult' object has no attribute 'payoffs'` / unexpected keyword `payoffs`.

- [ ] **Step 3: Implement**

In `src/edhpower/sim/__init__.py`:

Add to the imports: `from edhpower.payoffs import DeckPayoffs, detect`.

Add two fields to `SimResult` after `lines_skipped`:

```python
    line_status: list[dict[str, Any]]
    payoffs: dict[str, list[str]]
```

Change the signature and body of `simulate`:

```python
def simulate(facts: DeckFacts, cfg: SimConfig, iterations: int, tipping_target: int, payoffs: DeckPayoffs | None = None) -> SimResult:
    payoffs = payoffs if payoffs is not None else detect(facts)
    deck = build_sim_deck(facts, cfg)
    lines, skipped = select_lines(facts, cfg, payoffs)
```

(the rest of the loop is unchanged), and in the `notes` construction after `notes.extend(deck.notes)` add `notes.extend(payoffs.notes)`. In the `SimResult(...)` call add:

```python
        line_status=[{
            "label": l.label,
            "status": l.status,
            "resources": list(l.resources),
            "categories": list(dict.fromkeys(c for r in l.resources for c in cfg.payoff_converts.get(r, ()))),
            "candidates": sorted(l.payoff.candidates) if l.payoff else [],
            "hand_ok": bool(l.payoff.hand_ok) if l.payoff else False,
        } for l in lines],
        payoffs={k: list(v) for k, v in payoffs.by_category.items()},
```

- [ ] **Step 4: Run and commit**

Run: `uv run pytest tests/test_sim.py -q` → pass. Run: `uv run pytest -q` → all pass.

```bash
git add src/edhpower/sim/__init__.py tests/test_sim.py
git commit -m "sim: expose per-line payoff status and detected payoffs in SimResult

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Analysis wiring and sim version 2

**Files:**
- Modify: `src/edhpower/analysis.py`
- Modify: `src/edhpower/data/scoring.toml:69` (`version = 1` → `2`)
- Test: `tests/test_analysis.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `Analysis.payoffs: DeckPayoffs`; `Analysis.to_dict()["payoffs"]`; `analyse` computes `detect(facts)` once and passes it to `simulate` and (Task 8) `evaluate_bracket`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_analysis.py` (follow that file's existing way of getting a facts object; `fixture_facts` from `conftest` works):

```python
def test_analysis_carries_payoffs_once():
    from edhpower.analysis import analyse
    from edhpower.payoffs import DeckPayoffs, detect
    from .conftest import fixture_facts
    facts = fixture_facts("ulalek-bracket3-v2")
    a = analyse(facts, iterations=10)
    assert isinstance(a.payoffs, DeckPayoffs) and a.payoffs == detect(facts)
    assert a.to_dict()["payoffs"] == a.payoffs.to_dict()
    assert a.sim is not None and a.sim.payoffs == a.payoffs.by_category
    assert a.config["sim_version"] == 2
```

In `tests/test_config.py` change the two `cfg.stamp() == {... "sim_version": 1}` assertions and `s.version == 1` to `2`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_analysis.py tests/test_config.py -q` → `AttributeError: 'Analysis' object has no attribute 'payoffs'`; the config tests fail on `1 != 2`.

- [ ] **Step 3: Implement**

`scoring.toml`: change `version = 1` under `[sim]` to `version = 2                 # 2 (2026-10-18): lethal_combo needs the payoff; lock-only lines leave the combo clock`.

`analysis.py`: add `from edhpower.payoffs import DeckPayoffs, detect`; add field `payoffs: DeckPayoffs` to `Analysis` after `facts`; add `"payoffs": self.payoffs.to_dict(),` to `to_dict` after `"facts"`; in `analyse`:

```python
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
        ...
```

- [ ] **Step 4: Run and commit**

Run: `uv run pytest tests/test_analysis.py tests/test_config.py -q` → pass.
Run: `uv run pytest -q` → **exactly** the two golden tests fail (`test_golden_config_matches_current_config` because `sim_version` is now 2, and `test_golden_values` rows). That is expected until Task 10. Anything else failing is a defect.

```bash
git add src/edhpower/analysis.py src/edhpower/data/scoring.toml tests/test_analysis.py tests/test_config.py
git commit -m "analysis: detect payoffs once per run; bump sim version to 2

Goldens are intentionally red until the re-baseline task.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Bracket review criterion for self-harm two-card combos

**Files:**
- Modify: `src/edhpower/bracket.py` (`evaluate_bracket` signature and the two-card section)
- Modify: `src/edhpower/analysis.py` (pass `payoffs` and `cfg.sim`)
- Test: `tests/test_bracket.py`

**Interfaces:**
- Produces: `evaluate_bracket(facts, payoffs: DeckPayoffs | None = None, sim_cfg: SimConfig | None = None)`; new `Criterion("two_card_combos_no_payoff", "review", None, [...labels...], detail)` emitted only when both arguments are given and at least one definitely-two-card line qualifies.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bracket.py`:

```python
def _self_mill_line(cid, *names):
    return ComboLine(cid, tuple(ComboPiece(n, ("B",), False) for n in names), (), ("Infinite self-mill", "Near-infinite self-discard triggers"), "", 0, "S", 1, "", "")


def test_self_harm_two_card_combo_without_payoff_is_flagged_for_review_not_floored_lower():
    from edhpower.config import load_config
    from edhpower.payoffs import detect
    cards = [make_card("The Gitrog Monster", type_line="Legendary Creature — Frog Horror"), make_card("The Necrobloom", type_line="Legendary Creature — Plant Horror")]
    combos = _combos(lines=[_self_mill_line("g", "The Gitrog Monster", "The Necrobloom")], combo_flags=[_cf("g", two=True, speed=5)])
    facts = _facts(cards, combos)
    v = evaluate_bracket(facts, detect(facts), load_config().sim)
    names = {c.name: c for c in v.criteria}
    assert v.minimum_bracket == 3 and names["two_card_combos"].status == "triggered"
    r = names["two_card_combos_no_payoff"]
    assert r.status == "review" and r.floor is None and r.triggers == ["The Gitrog Monster + The Necrobloom (self_mill)"]
    assert "no empty-library win" in r.detail and "scrollvault would not floor" in r.detail


def test_self_harm_combo_with_a_payoff_in_the_deck_is_not_flagged():
    from edhpower.config import load_config
    from edhpower.payoffs import detect
    lab = make_card("Laboratory Maniac", type_line="Creature — Human Wizard", oracle_text="If you would draw a card while your library has no cards in it, you win the game instead.")
    cards = [make_card("The Gitrog Monster"), make_card("The Necrobloom"), lab]
    combos = _combos(lines=[_self_mill_line("g", "The Gitrog Monster", "The Necrobloom")], combo_flags=[_cf("g", two=True, speed=5)])
    facts = _facts(cards, combos)   # tags unavailable → pattern-only detection finds Lab Man
    v = evaluate_bracket(facts, detect(facts), load_config().sim)
    assert "two_card_combos_no_payoff" not in {c.name for c in v.criteria}


def test_mana_combo_without_sink_is_not_a_self_harm_review():
    from edhpower.config import load_config
    from edhpower.payoffs import detect
    cards = [make_card("Basalt Monolith"), make_card("Forsaken Monument")]
    combos = _combos(lines=[_line("m", "Basalt Monolith", "Forsaken Monument")], combo_flags=[_cf("m", two=True, speed=5)])
    facts = _facts(cards, combos)
    v = evaluate_bracket(facts, detect(facts), load_config().sim)
    assert "two_card_combos_no_payoff" not in {c.name for c in v.criteria}


def test_bracket_without_payoffs_argument_is_unchanged():
    cards = [make_card("The Gitrog Monster"), make_card("The Necrobloom")]
    combos = _combos(lines=[_self_mill_line("g", "The Gitrog Monster", "The Necrobloom")], combo_flags=[_cf("g", two=True, speed=5)])
    v = evaluate_bracket(_facts(cards, combos))
    assert "two_card_combos_no_payoff" not in {c.name for c in v.criteria} and v.minimum_bracket == 3
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_bracket.py -q` → `TypeError: evaluate_bracket() takes 1 positional argument but 3 were given`.

- [ ] **Step 3: Implement**

In `src/edhpower/bracket.py` add imports:

```python
from edhpower.config import SimConfig
from edhpower.payoffs import DeckPayoffs
```

Change the signature to `def evaluate_bracket(facts: DeckFacts, payoffs: DeckPayoffs | None = None, sim_cfg: SimConfig | None = None) -> BracketVerdict:`.

Inside the two-card section, right after the `criteria.append(Criterion("two_card_combos", ...))` line and before `if early:`, add:

```python
        if payoffs is not None and sim_cfg is not None:
            from edhpower.sim.combos import classify   # local import: bracket must not depend on the sim package at import time
            self_harm = {"self_mill", "draw"}
            flagged: list[str] = []
            for line in combos.included:
                f = combos.combo_flags.get(line.id)
                if f is None or not f.definitely_two_card:
                    continue
                status, resources, _ = classify(line, sim_cfg, payoffs)
                if status == "no_payoff" and resources and set(resources) <= self_harm:
                    flagged.append(f"{' + '.join(line.piece_names)} ({'/'.join(resources)})")
            if flagged:
                criteria.append(Criterion(
                    "two_card_combos_no_payoff", "review", None, flagged,
                    "floors Bracket 3 by the published rule, but its only product is self-harm and the deck has no empty-library win; scrollvault would not floor on it",
                ))
```

In `src/edhpower/analysis.py` change the bracket call to `bracket = evaluate_bracket(facts, payoffs, cfg.sim)`.

- [ ] **Step 4: Run and commit**

Run: `uv run pytest tests/test_bracket.py tests/test_analysis.py -q` → pass. Run: `uv run pytest -q` → only the two golden tests fail.

```bash
git add src/edhpower/bracket.py src/edhpower/analysis.py tests/test_bracket.py
git commit -m "bracket: review note for self-harm two-card combos with no payoff

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Report lines and narrative findings

**Files:**
- Modify: `src/edhpower/report.py:131-133` (sim block)
- Modify: `src/edhpower/narrative.py:98-111` (combos finding)
- Test: `tests/test_report.py`, `tests/test_narrative.py`

**Interfaces:**
- Consumes: `SimResult.line_status`, `SimResult.payoffs`, `payoffs.CATEGORY_LABELS`.
- Produces: report lines `lines simulated: <label> [<status text>]; …` and `payoffs: <label>: <names or none>; …`; findings of kind `combos`: `"N infinite engine(s) have no payoff in this deck: …"` and `"M lock line(s) excluded from the combo clock: …"`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_report.py` add a new facts builder and tests:

```python
def _payoff_facts():
    parsed = parse_decklist("1 Zhulodok, Void Gorger\n\n6 Wastes\n1 Basalt Monolith\n1 Forsaken Monument\n1 Glacial Chasm\n1 Walking Ballista\n")
    objs = [make_card("Zhulodok, Void Gorger", cmc=7.0, type_line="Legendary Creature — Eldrazi"),
            make_card("Wastes", type_line="Basic Land", cmc=0.0, produced_mana=["C"]),
            make_card("Basalt Monolith", cmc=3.0), make_card("Forsaken Monument", cmc=5.0), make_card("Glacial Chasm", type_line="Land", cmc=0.0),
            make_card("Walking Ballista", cmc=0.0, mana_cost="{X}{X}", type_line="Artifact Creature — Construct", power="0", toughness="0",
                      oracle_text="This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nRemove a +1/+1 counter from this creature: It deals 1 damage to any target.")]
    res = Resolution({o["name"]: CardData.from_scryfall(o) for o in objs}, [], 0, "2026-09-10T00:00:00Z")
    mana = ComboLine("m", (ComboPiece("Basalt Monolith", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), ("Infinite colorless mana",), "", 0, "R", 5, "", "")
    lock = ComboLine("l", (ComboPiece("Glacial Chasm", ("B",), False), ComboPiece("Forsaken Monument", ("B",), False)), (), ("Prevent all damage that would be dealt to you", "Lock"), "", 0, "S", 4, "", "")
    flags = {cid: ComboFlags(cid, True, False, 5, False, False, False, False, True) for cid in ("m", "l")}
    combos = ComboData("C", [mana, lock], 0, {}, flags, "R", "2026-09-10T01:00:00Z")
    from .conftest import full_tag_cache
    return build_facts(parsed, res, combos, None, "deck/p.txt", tag_cache=full_tag_cache(**{"mana-sink": ["Walking Ballista"]}))


def test_report_shows_line_status_and_payoffs():
    text = render_text(analyse(_payoff_facts(), iterations=20))
    assert "lines simulated: Basalt Monolith + Forsaken Monument [mana → Walking Ballista]" in text
    assert "not simulated: Glacial Chasm + Forsaken Monument (lock only)" in text
    assert "payoffs: mana sink: Walking Ballista" in text
    assert "1 lock line(s) excluded from the combo clock: Glacial Chasm + Forsaken Monument" in text


def test_report_names_engines_without_payoff():
    facts = _payoff_facts()
    facts.entries = [e for e in facts.entries if e.name != "Walking Ballista"]
    text = render_text(analyse(facts, iterations=20))
    assert "lines simulated: Basalt Monolith + Forsaken Monument [mana → no payoff in deck]" in text
    assert "payoffs: mana sink: none" in text
    assert "1 infinite engine(s) have no payoff in this deck: Basalt Monolith + Forsaken Monument" in text
```

Also extend the needle list in `test_report_contains_every_section` with `"payoffs:"`.

In `tests/test_narrative.py` append:

```python
def test_combos_findings_name_payoff_gaps_and_locks():
    from edhpower.sim import Clock, SimResult
    facts, bracket, curve, components, tipping, sim = _parts("ulalek-bracket3-v2", iterations=20)
    import dataclasses
    doctored = dataclasses.replace(
        sim,
        lines_simulated=["A + B", "C + D"],
        line_status=[{"label": "A + B", "status": "no_payoff", "resources": ["mana"], "categories": ["mana_sink"], "candidates": [], "hand_ok": False},
                     {"label": "C + D", "status": "payoff", "resources": ["etb"], "categories": ["etb_damage"], "candidates": ["E"], "hand_ok": False}],
        lines_skipped=[dataclasses.replace(sim.lines_skipped[0], reason="lock only")] if sim.lines_skipped else [],
    )
    text = "\n".join(f.text for f in build_narrative(facts, bracket, curve, components, tipping, doctored, CFG.narrative).findings if f.kind == "combos")
    assert "1 infinite engine(s) have no payoff in this deck: A + B" in text
    if sim.lines_skipped:
        assert "1 lock line(s) excluded from the combo clock" in text
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_report.py tests/test_narrative.py -q` → assertion failures on the missing strings.

- [ ] **Step 3: Implement**

`src/edhpower/report.py`: add `from edhpower.payoffs import CATEGORY_LABELS` and a helper near `_names`:

```python
def _status_text(row: dict) -> str:
    res = "/".join(row["resources"]) or "no recognised product"
    if row["status"] == "direct":
        return "direct win"
    if row["status"] == "payoff":
        return f"{res} → {_names(row['candidates'], 3)}"
    if row["status"] == "no_payoff":
        return f"{res} → no payoff in deck"
    return res
```

Replace the `lines simulated:` line with:

```python
        shown = [f"{row['label']} [{_status_text(row)}]" for row in sim.line_status]
        out.append(f"  lines simulated: {_truncated(shown, 6, '; ') if shown else 'none'}")
```

After the `not simulated:` block add:

```python
        relevant = {c for row in sim.line_status for c in row["categories"]}
        cats = [c for c in CATEGORY_LABELS if c in relevant or sim.payoffs.get(c)]
        if cats:
            out.append("  payoffs: " + "; ".join(f"{CATEGORY_LABELS[c]}: {_names(sim.payoffs.get(c, []), 4) if sim.payoffs.get(c) else 'none'}" for c in cats))
        else:
            out.append("  payoffs: none detected, and no simulated line needs one")
```

`relevant` comes from the `categories` key each `line_status` row carries (Task 6), so the report reads no config.

`src/edhpower/narrative.py`: in the `else:` branch of the combos block, after `findings.append(Finding("combos", text))`, add:

```python
        gaps = [row["label"] for row in sim.line_status if row["status"] == "no_payoff"]
        if gaps:
            findings.append(Finding("combos", f"{len(gaps)} infinite engine(s) have no payoff in this deck: {'; '.join(gaps[:3])}" + (f" … (+{len(gaps) - 3} more)" if len(gaps) > 3 else "")))
        locks = [x.label for x in sim.lines_skipped if x.reason == "lock only"]
        if locks:
            findings.append(Finding("combos", f"{len(locks)} lock line(s) excluded from the combo clock: {'; '.join(locks[:3])}" + (f" … (+{len(locks) - 3} more)" if len(locks) > 3 else "")))
```

- [ ] **Step 4: Run and commit**

Run: `uv run pytest tests/test_report.py tests/test_narrative.py -q` → pass. Run: `uv run pytest -q` → only the two golden tests fail.

```bash
git add src/edhpower/report.py src/edhpower/narrative.py tests/test_report.py tests/test_narrative.py
git commit -m "report: show per-line payoff status, detected payoffs, and payoff-gap findings

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Golden re-baseline, docs, calibration check

**Files:**
- Modify: `tests/fixtures/golden.json` (regenerated)
- Modify: `README.md:110-130` (sim limits) and the `[sim]` paragraph
- Modify: `docs/superpowers/specs/2026-10-18-payoff-gating-design.md` (status line only)

- [ ] **Step 1: Regenerate the goldens and read the diff**

```bash
uv run python tests/golden_update.py > /dev/null
git diff --stat tests/fixtures/golden.json
git diff tests/fixtures/golden.json
```

Expected: `config.sim_version` 1 → 2. For each fixture, only `sim_combo_reached` and `sim_lethal_combo_reached` may move (lock-only lines leaving the combo clock lowers `sim_combo_reached`; a line that became `payoff` can only lower or keep `sim_lethal_combo_reached`, never raise it, because v1 stamped lethal from the produces text alone). Any change to `sim_commander_median`, `sim_mana_threshold_median`, `sim_threat_median`, `sim_combat_median`, the tipping values or the scores is a defect: stop and find it before committing. Write the per-fixture before/after of the two combo fields into the commit message.

- [ ] **Step 2: Run the whole suite**

Run: `uv run pytest -q` → all pass, no warnings.

- [ ] **Step 3: Update the README**

In the "Known limits of sim v1" list: rename the heading to `Known limits of sim v2` and add one bullet at the end:

```markdown
- Combo payoffs are detected by oracle-text patterns (plus the `mana-sink` and
  `alternate-win-condition` tags for two categories). A payoff the patterns miss makes a real
  win read as "no payoff in deck"; the report lists what was detected so the gap is visible.
```

In the `[sim]` paragraph after "production defaults to 20 000", add: `sim v2 (2026-10-18) gates the lethal-combo clock on a detected payoff and drops lock-only lines from the combo clock; v1 and v2 combo numbers are not comparable.`

In the spec, change `**Status:** approved design, awaiting implementation plan.` to `**Status:** implemented (sim v2, 2026-10-18); plan at docs/superpowers/plans/2026-10-18-payoff-gating.md.`

- [ ] **Step 4: Calibration check on the Necrobloom list**

```bash
S=$TMPDIR; uv run edhpower necro-deck.txt --commander "The Necrobloom" --cache-dir "$S/edhpower-cache" --iterations 2000 2>&1 | sed -n '/Goldfish simulation/,/^$/p'
```

(First run fetches the two new tag slugs, about 11 requests.) Expected in the output:
- `lines simulated:` shows `The Gitrog Monster + The Necrobloom` **not** simulated (notable prerequisites, unchanged) and the four Glacial Chasm lines under `not simulated: … (lock only)`.
- The `two_card_combos_no_payoff` review criterion lists `The Gitrog Monster + The Necrobloom (self_mill)`.
- `payoffs:` names Craterhoof Behemoth under go-wide finisher and Field of the Dead under landfall tokens, or says `none` for both. Whichever it is, it must agree with `tests/test_payoffs.py`; do not adjust a pattern to fit this deck.
- `combo line assembled` shows `>T12` with 0% at every turn (every simulated line was a lock).

Paste the Goldfish block into the commit message body.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/golden.json README.md docs/superpowers/specs/2026-10-18-payoff-gating-design.md
git commit -m "sim v2: re-baseline goldens for payoff gating; document the change

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes

- Spec coverage: detection unit (T3), resource mapping and lock pattern (T1), tag table and `tag_table` provenance (T2), line statuses and `selfPays` (T4), engine zone rule and late payoff (T5), `SimResult` fields (T6), analysis wiring and sim version (T7), bracket review note (T8), report and narrative (T9), golden re-baseline, README and calibration (T10). Error handling: bad pattern (T1), empty produces (T4), no combos (unchanged, covered by existing tests).
- Type consistency: `DeckPayoffs.by_category: dict[str, list[str]]` everywhere; `PayoffNeed(candidates: frozenset[str], hand_ok: bool)`; `SimLine` positional order `(id, label, pieces, extra_mana, lethal, status, resources, payoff)` used identically in T4 tests and T4 implementation; `classify` returns `(status, resources, PayoffNeed | None)` in T4 and T8; `evaluate_bracket(facts, payoffs, sim_cfg)` in T8 and T7/T8 analysis call.
- Review Focus items are pinned in: T3 (`test_back_face_text_is_scanned`, `test_detect_without_tags_is_pattern_only_and_says_so`), T4 (`test_classify_direct_payoff_no_payoff_unmapped` empty produces; `test_classify_battlefield_only_resource_and_self_paying_piece`; `test_classify_landfall_tokens_is_fuel_only_with_a_go_wide_payoff`), T5 (`test_payoff_already_on_board_stamps_lethal_at_assembly`).
