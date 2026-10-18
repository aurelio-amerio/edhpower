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

_X_SPELL_EFFECT = re.compile(r"deals x damage[^.]*divided|deals x damage to each (?:opponent|player|of (?:them|those|these))|each opponent loses (?:two times |twice )?x life|repeat the following process x times")
_SINK_PINGER = re.compile(r"remove a \+1/\+1 counter[^.]*deals? \d+ damage to any target")
_SINK_COUNTER_FEED = re.compile(r"put[^.]*\+1/\+1 counter")
_SINK_TRAMPLE = re.compile(r"\}: [^.]*creatures you control get \+\d+/\+\d+ and (?:gain|have) trample")
_SINK_X_ACTIVATION = re.compile(r"\{x\}[^:\n]*:[^.\n]*(?:each opponent loses|deals x damage)")
_DRAIN = re.compile(r"whenever (?:this creature or )?(?:a|an|another|one or more)\b" + _NOT_THEIRS + r"\bcreatures?\b" + _NOT_THEIRS + r"\bdie(?:s)?\b[^.]*?" + _OPP_LOSS)
_ETB_DAMAGE = re.compile(r"whenever (?:a|another)[^.]*creature[^.]*enters[^.]*(?:deals \d+ damage to each opponent|deals damage equal to (?:its|that creature's) power to any target|each opponent loses \d+ life)")
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
