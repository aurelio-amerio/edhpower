# Payoff gating for the goldfish simulator

**Date:** 2026-10-18. **Status:** implemented (sim v2, 2026-10-18); plan at docs/superpowers/plans/2026-10-18-payoff-gating.md.

## Problem

Spellbook lists an infinite combo whether or not the deck can turn its product into a win. The
simulator today stamps `lethal_combo` from a substring match on the line's `produces` list
(`sim.lethal_features`) and stamps `combo` for any assembled line, including pure locks. For the
Necrobloom list that means four "prevent all damage" lines drive the combo clock, and an
infinite self-mill line with no empty-library win in the deck would read as a win if it were
simulated. Scrollvault (bracket.js v393) gates on payoffs; this design ports that idea, scoped to
the simulator and the report.

Out of scope, recorded elsewhere: weighting the component model's `combos` part by payoff
(`docs/superpowers/ideas/2026-10-18-payoff-weighted-combos-component.md`); reanimation in the
engine (needs a graveyard zone first; separate design). The official bracket floor is not changed
by this work: WotC counts any two-card infinite, and `bracket.py` documents the published
criteria.

## Decisions taken with the user

1. Scope: sim clocks plus findings. Component score untouched.
2. Payoff zone: scrollvault's rule. For infinite mana a payoff in hand counts; for every other
   resource the payoff must be on the battlefield.
3. Detection: narrow oracle-text patterns ported from scrollvault, with a Scryfall oracle tag
   required as a check where one exists. Every matched card is listed in the report.
4. Landfall is added as a resource (scrollvault has none); without it the Nantuko lines in the
   Necrobloom list could never become lethal.

## Architecture

Everything new is a pure function of `DeckFacts`. No field is added to `DeckFacts` and the facts
schema version does not change: each `FactEntry` already carries `CardData` (oracle text, faces)
and `facts.profiles[name].tags`, which is all detection needs. The frozen fixtures therefore keep
loading, and the golden numbers move only where the simulator semantics changed.

```
DeckFacts ──> payoffs.detect(facts) ──> DeckPayoffs {category -> [card names], notes}
    │                                           │
    └──> sim.combos.select_lines(facts, cfg, payoffs) ──> SimLine(..., payoff=PayoffNeed | None)
                                                │
                                      engine: combo / lethal_combo clocks
                                                │
                                   report + narrative + bracket review note
```

## Components

### `payoffs.py` (new)

`detect(facts: DeckFacts) -> DeckPayoffs`, where

```python
@dataclass(frozen=True)
class DeckPayoffs:
    by_category: dict[str, list[str]]   # category -> sorted card names (commanders included)
    tag_checked: tuple[str, ...]        # categories whose tag check was applied
    notes: list[str]
```

Categories and their detection (patterns run on the lower-cased oracle text of all faces joined
by a space, as scrollvault's `_payoffText` does):

| category | pattern (ported from scrollvault v393) | tag check |
|---|---|---|
| `mana_sink` | **X-spell rule (no tag needed):** `{X}` in the mana cost **and** (`deals x damage ... divided` / `deals x damage to each (opponent\|player)` / `each opponent loses x life` / `repeat the following process x times`). **Activation rule (tag required):** `remove a +1/+1 counter ... deals N damage to any target` with `{X}` in cost or `put ... +1/+1 counter`; **or** `}: ... creatures you control get +N/+N and (gain\|have) trample`; **or** `{x}` inside an activation cost followed in the same sentence by `each opponent loses` / `deals x damage` | `mana-sink` (activation rule only) |
| `drain` | `whenever (a\|an\|another\|...) creature(s) [you control] (dies\|die) ... each opponent loses` or the broader death-trigger form (`GEN_PAY_DEATH`: dies → each/target opponent loses N / deals N damage to each opponent or any target, excluding opponent/attacking/blocking clauses) | none |
| `etb_damage` | `whenever (a\|another) ... creature ... enters ... (deals N damage to each opponent \| each opponent loses N life)` | none |
| `go_wide` | `creatures you control get +N/+N and (gain\|have) trample` or `creatures you control gain trample and get +N/+N` (Craterhoof's word order) | none |
| `token_drain` | `whenever (one or more) token(s) you control (enters\|are created) ... each opponent loses` or `whenever you create ... tokens ... each opponent loses` | none |
| `counter_win` | `+1/+1 counter(s) ... you win the game`, or `(twenty\|N) or more ... counters on (it\|this ...) ... you win the game` (Simic Ascendancy, Helix Pinnacle) | none |
| `cast_damage` | `whenever you cast (a\|an\|your) (instant\|sorcery\|noncreature) ... spell ... deals N damage to each opponent` | none |
| `empty_library_win` | `draw a card while your library has no cards` / `no cards in it, you win the game` / `library has no cards in it ... win the game` / `number of cards in your library, you win the game` (Thassa's Oracle) | `alternate-win-condition` |
| `life_drain` | `whenever you gain life ... (each/target opponent loses (N\|that much) life \| deals N damage to each opponent/any target)` | none (the `lifedrain` tag marks drain *sources* such as Blood Artist, not lifegain payoffs: Vito and Sanguine Bond are untagged) |
| `landfall_payoff` | `landfall` or `whenever a land (you control )?enters` followed in the same sentence by `each opponent loses` / `deals N damage to (each opponent\|any target)` | none |
| `landfall_tokens` | `landfall` or `whenever a land (you control )?enters` followed in the same sentence by `create ... token` (Field of the Dead, Scute Swarm). Fuel, not a win: counts as a landfall payoff **only when** the deck also has a `go_wide`, `token_drain` or `etb_damage` card, and the report names both halves | none |

Scrollvault's curated name lists (`MANA_SINK_CURATED` = Torment of Hailfire, Profane Source,
Debt to the Deathless, Exsanguinate; `ETB_DMG_CURATED`; `CAST_DMG_CURATED`; `GAME_END_PAYOFF`
= Thassa's Oracle, Laboratory Maniac, Jace, Wielder of Mysteries) are **not** copied as name lists.
The four `MANA_SINK_CURATED` cards are X spells matched by the X-spell rule (Torment of Hailfire
via `repeat the following process x times`); the three empty-library cards match the widened
pattern (Thassa's Oracle needed the `number of cards in your library` form). If a test shows a curated card the patterns miss, the pattern is widened,
not the list grown.

**Tag check rule.** `tags.TAG_TABLE` gains `mana-sink` and `alternate-win-condition` (probed
2026-10-18: 1814 and 62 legal cards; both tags verified on Walking Ballista, Exsanguinate, Thassa's
Oracle, Laboratory Maniac, Jace and Simic Ascendancy; Torment of Hailfire carries neither, which is
why the X-spell rule needs no tag). A pattern match in a tag-checked
category is kept only if the card's profile carries the tag, **when the facts were built with
that slug known**. `facts.fetched["tag_table"]` (new key, a comma-joined sorted string of slugs, written by
`build_facts`) says which slugs were known; a facts file without the key, or without the slug,
gets pattern-only detection for that category and a note
`"payoff tag check skipped for <category>: facts predate the <slug> tag"`. Fixtures frozen before
this change therefore degrade loudly, never silently.

`pinger` (714 cards) is not used: the Walking Ballista shape is already covered by the counter
rule inside `mana_sink`.

### Resource mapping (`scoring.toml`, `[sim.payoffs]`)

```toml
[sim.payoffs]
# Spellbook `produces` text -> resource. First matching rule wins per feature; "near-infinite" is
# folded into "infinite" before matching (scrollvault's near bucket is not kept separately).
resources = [
  { resource = "mana",        pattern = "infinite [a-z, ]*mana|infinite mana" },
  { resource = "death",       pattern = "infinite death triggers|infinite creature sacrifice triggers" },
  { resource = "etb",         pattern = "infinite creature etb" },
  { resource = "tokens",      pattern = "infinite [a-z ]*creature tokens?" },
  { resource = "counters",    pattern = "infinite \\+1/\\+1 counters" },
  { resource = "storm",       pattern = "infinite (?:storm count|magecraft triggers)" },
  { resource = "draw",        pattern = "infinite card draw" },
  { resource = "self_mill",   pattern = "infinite self-mill" },
  { resource = "landfall",    pattern = "infinite landfall triggers" },
  { resource = "lifegain",    pattern = "infinite lifegain" },
]
# resource -> payoff categories that convert it
converts = { mana = ["mana_sink"], death = ["drain"], etb = ["etb_damage"], tokens = ["go_wide", "etb_damage", "token_drain"], counters = ["counter_win"], storm = ["cast_damage"], draw = ["empty_library_win"], self_mill = ["empty_library_win"], landfall = ["landfall_payoff", "landfall_tokens"], lifegain = ["life_drain"] }
# landfall_tokens is fuel: it converts only when one of these is also in the deck
chained = { landfall_tokens = ["go_wide", "token_drain", "etb_damage"] }
# payoff may sit in hand for these resources (you can cast it with the infinite mana)
hand_ok = ["mana"]
# a line whose every produced feature matches this is a lock, not a combo (scrollvault __SELF_PROT)
lock_only = "^(?:lock|prevent all damage that would be dealt to (?:you|permanents you control|creatures you control|you and [^.]*)(?: during [^.]*| by sources you don't control)?|you have protection from everything(?: during [^.]*)?|you can't cast spells)$"
```

`SimConfig` gains `payoff_resources`, `payoff_converts`, `payoff_hand_ok`, `lock_only_pattern`.
`lethal_features` stays and keeps meaning "direct win".

### Line status (`sim/combos.py`)

`select_lines(facts, cfg, payoffs)` classifies every `included` line before the existing skip
rules:

| status | rule | simulated? | `combo` clock | `lethal_combo` clock |
|---|---|---|---|---|
| `direct` | any produced feature matches `lethal_features` | yes | on assembly | on assembly |
| `payoff` | not direct; ≥1 resource maps to a category with ≥1 card in the deck | yes | on assembly | when a candidate is on the battlefield, or in hand if the resource is in `hand_ok` |
| `no_payoff` | not direct; resources found but no category has a card in the deck | yes | on assembly | never |
| `unmapped` | not direct; no produced feature matches any resource rule | yes | on assembly | never |
| `lock_only` | every produced feature matches `lock_only` | **no** (skip reason `lock only`) | — | — |

`SimLine` gains `status: str` and `payoff: PayoffNeed | None` with
`candidates: frozenset[str]` (card names, across all converting categories) and `hand_ok: bool`.
The existing `lethal: bool` is kept and equals `status == "direct"`. Pieces that are themselves
payoff candidates count (scrollvault's `selfPays`): a line whose piece is in `candidates` is
`direct` in effect, so such a line is reported as `payoff` with the piece named and stamps
`lethal_combo` on assembly.

`SkippedLine` is unchanged; `lock only` is a new reason string.

### Engine (`sim/engine.py`)

- `_try_combo` stamps `combo` on assembly as today. It stamps `lethal_combo` immediately for
  `direct` lines and for `payoff` lines whose payoff condition already holds.
- New: `self.pending_payoff: set[str]` of fired `payoff` lines not yet lethal. At the end of each
  main phase (after the existing role loop) the engine checks each pending line; the first turn
  the condition holds stamps `lethal_combo` and clears the set. The check is a zone test only, no
  mana is paid for the payoff (scrollvault's rule: with infinite mana the sink is free; otherwise
  it must already be in play).
- `GameRecord` is unchanged. `sim.version` becomes 2.

### Report (`report.py`), narrative, bracket

- Sim block: the `lines simulated:` list carries the status after each label, e.g.
  `The Gitrog Monster + The Necrobloom [self-mill → empty-library win: none in deck]`,
  `Springheart Nantuko + Lotus Cobra [landfall → Field of the Dead]`. A new line
  `payoffs: mana sink: Walking Ballista; empty-library win: none; …` lists the detected cards per
  category (only categories relevant to some line, plus any that matched). Notes from
  `DeckPayoffs.notes` join the sim notes.
- `SimResult` gains `line_status: list[dict]` (label, status, resources, candidates) and
  `payoffs: dict[str, list[str]]` so the JSON carries the same information.
- Narrative: new `[combos]` finding
  `"N infinite engine(s) have no payoff in this deck: <labels>"` when any `no_payoff` line
  exists; and `"M lock line(s) excluded from the combo clock"` when any `lock_only` line exists.
- Bracket (`bracket.py`): new review criterion `two_card_combos_no_payoff` (status `review`,
  no floor) listing definitely-two-card lines whose status is `no_payoff` and whose resources are
  only `self_mill` or `draw`, with detail
  `"floors Bracket 3 by the published rule, but its only product is self-harm and the deck has no empty-library win; scrollvault would not floor on it"`.
  This needs `DeckPayoffs`, so `bracket.evaluate` takes it as an optional argument; `analysis.py`
  computes `detect(facts)` once and passes it to sim, bracket and narrative.

## Error handling

- `facts.combos is None`: unchanged behaviour, clocks `unevaluated`.
- A line with an empty `produces` list: `unmapped`.
- A card with empty oracle text (tokens, emblems never reach here) matches nothing.
- Malformed pattern in `scoring.toml`: `config.load` raises at startup, as for any other
  constant.

## Testing

TDD throughout; every test below is written before the code it covers.

- `tests/test_payoffs.py`: one test per category with a real positive (oracle text pasted from
  Scryfall) and a real negative, including Rogue's Passage (mana-sink tag, no pattern),
  Exsanguinate (X-cost rule, no curated list), Thassa's Oracle, Blood Artist, Impact Tremors,
  Craterhoof Behemoth (go_wide), Retreat to Hagra / Scute Swarm (landfall), Field of the Dead
  (landfall via `create ... token`). Tag-check tests: match dropped without the tag when
  `fetched["tag_table"]` lists the slug; kept with a note when it does not.
- `tests/test_sim_combos.py`: status classification for each row of the status table, using
  `ComboLine` objects built inline; lock-only skip; `selfPays` piece.
- `tests/test_sim_engine.py`: a fixed four-card library and a two-piece `payoff` line where the
  payoff is drawn two turns after assembly: `combo` at the assembly turn, `lethal_combo` two
  turns later; `hand_ok` variant stamps on the draw turn; `no_payoff` variant never stamps.
- `tests/test_bracket.py`: the review criterion fires for a self-mill two-card line with no
  empty-library win and not when Thassa's Oracle is present.
- `tests/test_report.py` / `test_narrative.py`: the new lines and findings render.
- `tests/test_config.py`: the `[sim.payoffs]` block loads and a bad pattern raises.
- Golden: `uv run python tests/golden_update.py` once, as the final task, after the sim version
  bump; the diff is reviewed line by line and the CALIBRATION note in the README is updated to say
  sim v2 numbers are not comparable with v1.

## Calibration check

After implementation, run the Necrobloom list and the five fixtures and compare the per-line
statuses against the expectation from reading the lists: Necrobloom should show the Gitrog line
as `no_payoff` (self-mill), the three Nantuko lines as `payoff` only if Craterhoof Behemoth
matches `go_wide` so that Field of the Dead chains through `landfall_tokens` (otherwise
`no_payoff`), and the four Glacial Chasm lines as `lock only`. The result is decided by the
tests, not adjusted to the deck.
