"""Thin numeric extractor over oracle text: mana produced (activated/static clauses only), cost reduction, draw count, enters-tapped.

Knows nothing about card names. Everything a tag or Scryfall field can answer is answered elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_MANA_SYMBOL = re.compile(r"\{([WUBRGC](?:/[WUBRGCP])?)\}")
_ADD_CLAUSE = re.compile(r"\b[Aa]dds? (?P<body>[^.\n]*)")
_TRIGGER_START = re.compile(r"^\s*(?:Whenever|When|At the beginning of)\b")
_WORD_MANA = re.compile(r"\b(?P<n>a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+) mana\b")
_BOARD_DEPENDENT = re.compile(r"\bfor each\b|\bequal to\b|\bthat much\b|\bX\b")
_OR_WORD = re.compile(r"\bor\b")
_ALT_SPLIT = re.compile(r",\s*|\bor\b")
_COST_LESS = re.compile(r"(?P<subject>[^.\n]*?)\bcosts? \{(?P<n>\d)\} less to cast")
_DRAW = re.compile(r"\bdraws? (?P<n>a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+) cards?\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.\n]")
_ENTERS_TAPPED = re.compile(r"\benters(?: the battlefield)? tapped\b(?! unless)")


@dataclass(frozen=True)
class OracleNumbers:
    mana_per_activation: int
    mana_colors: tuple[str, ...]
    repeatable: bool
    board_dependent: bool
    cost_reduction: int
    cost_reduction_scope: str
    draw_count: int
    enters_tapped: bool


def _mana_in(body: str) -> tuple[int, tuple[str, ...]]:
    symbols = _MANA_SYMBOL.findall(body)
    if symbols:
        letters = sorted({ch for s in symbols for ch in s if ch in "WUBRGC"})
        if _OR_WORD.search(body):
            # A choice between alternatives ("Add {W} or {U}.", "Add {R}, {G}, or {W}.",
            # "Add {B}{B} or {U}{U}."): the amount is the size of ONE alternative, not the
            # sum of all of them. Colours are still the union across every alternative.
            amount = max((len(_MANA_SYMBOL.findall(part)) for part in _ALT_SPLIT.split(body)), default=0)
        else:
            amount = len(symbols)
        return amount, tuple(letters)
    m = _WORD_MANA.search(body)
    if m:
        n = m.group("n")
        return (int(n) if n.isdigit() else _WORD_NUM[n]), ("any",)
    return 0, ()


def extract(oracle_text: str, type_line: str = "") -> OracleNumbers:
    text = oracle_text or ""
    best, colors, repeatable, dependent = 0, (), False, False
    for line in text.split("\n"):
        if _TRIGGER_START.match(line):
            # A triggered ability ("Whenever ... adds an additional {G}") is not a mana ability
            # the profile can count as a source; doublers and Kinnan-style triggers are modelled
            # by the simulator from special_behaviours, not from this number.
            continue
        for m in _ADD_CLAUSE.finditer(line):
            body = m.group("body")
            if _BOARD_DEPENDENT.search(body):
                dependent = True
                continue
            amount, cols = _mana_in(body)
            if amount == 0:
                continue
            cost_part = line[: m.start()]
            this_repeatable = "{T}" in cost_part and "Sacrifice" not in cost_part
            if amount > best:
                best, colors = amount, cols
            repeatable = repeatable or this_repeatable
    is_spell = "Instant" in type_line or "Sorcery" in type_line
    if is_spell:
        repeatable = False

    reduction, scope = 0, ""
    m = _COST_LESS.search(text)
    if m:
        reduction = int(m.group("n"))
        scope = " ".join(m.group("subject").split()).strip(" ,;:").lower()

    draw = 0
    for m in _DRAW.finditer(text):
        tail = text[m.end():]
        stop = _SENTENCE_END.search(tail)
        clause_tail = tail[: stop.start()] if stop else tail
        if _BOARD_DEPENDENT.search(clause_tail):
            # A variable count ("draw a card for each artifact you control") must not become
            # a confident fixed number. board_dependent stays mana-scoped; this clause simply
            # contributes 0 rather than flipping OracleNumbers.board_dependent.
            continue
        n = m.group("n").lower()
        draw += int(n) if n.isdigit() else _WORD_NUM.get(n, 0)

    return OracleNumbers(best, colors, repeatable, dependent, reduction, scope, draw, bool(_ENTERS_TAPPED.search(text)))
