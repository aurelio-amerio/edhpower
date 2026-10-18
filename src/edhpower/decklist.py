"""Decklist parsing: plain `N Name` lines, `//` comments, Archidekt exports, JSON."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_PLAIN = re.compile(r"^(\d+)\s+(.+?)\s*$")
# 1x Name (set) collector [Category]   — set/collector required, category optional
_ARCHIDEKT = re.compile(r"^(\d+)x\s+(.+?)\s+\(([^)]+)\)\s+(\S+)(?:\s+\[([^\]]+)\])?\s*$")
_COMMANDER_MARKER = re.compile(r"^//\s*commander\s*$", re.IGNORECASE)
DFC_SEPARATOR = " // "


@dataclass(frozen=True)
class DeckEntry:
    name: str
    count: int
    is_commander: bool
    raw: str
    lineno: int


@dataclass
class ParsedDeck:
    entries: list[DeckEntry] = field(default_factory=list)
    commanders: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_cards(self) -> int:
        return sum(e.count for e in self.entries)


@dataclass
class _Raw:
    lineno: int
    name: str
    count: int
    raw: str
    marked: bool  # explicitly marked as commander in the file


def front_face(name: str) -> str:
    """'A // B' -> 'A'. Scryfall's collection endpoint only matches the front face."""
    return name.split(DFC_SEPARATOR, 1)[0].strip()


def _parse_line(line: str) -> tuple[int, str, bool] | None:
    m = _ARCHIDEKT.match(line)
    if m:
        category = (m.group(5) or "").strip().lower()
        return int(m.group(1)), m.group(2), category == "commander"
    m = _PLAIN.match(line)
    if m:
        return int(m.group(1)), m.group(2), False
    return None


def parse_decklist(text: str, commander_override: list[str] | None = None) -> ParsedDeck:
    deck = ParsedDeck()
    lines = text.splitlines()
    raws: list[_Raw] = []
    pending_marker = False

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("//"):
            pending_marker = bool(_COMMANDER_MARKER.match(stripped))
            continue
        parsed = _parse_line(stripped)
        if parsed is None:
            deck.errors.append(f"line {idx}: {stripped}")
            pending_marker = False
            continue
        count, name, tagged = parsed
        raws.append(_Raw(idx, front_face(name), count, stripped, tagged or pending_marker))
        pending_marker = False

    return _finish(deck, lines, raws, commander_override)


def parse_decklist_json(text: str, commander_override: list[str] | None = None) -> ParsedDeck:
    deck = ParsedDeck()
    data = json.loads(text)
    raws: list[_Raw] = []
    commanders = {front_face(n) for n in data.get("commanders", [])}
    for i, c in enumerate(data.get("commanders", []), start=1):
        raws.append(_Raw(i, front_face(c), 1, json.dumps(c), True))
    for i, item in enumerate(data.get("main", []), start=len(raws) + 1):
        name = front_face(str(item["name"]))
        if name in commanders:
            continue
        raws.append(_Raw(i, name, int(item.get("count", 1)), json.dumps(item), False))
    return _finish(deck, [], raws, commander_override)


def load_decklist(path: Path, commander_override: list[str] | None = None) -> ParsedDeck:
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix.lower() == ".json":
        return parse_decklist_json(text, commander_override)
    return parse_decklist(text, commander_override)


def _finish(deck: ParsedDeck, lines: list[str], raws: list[_Raw], override: list[str] | None) -> ParsedDeck:
    names_in_list = {r.name for r in raws}
    if override:
        wanted = list(dict.fromkeys(front_face(n) for n in override))
        missing = [n for n in wanted if n not in names_in_list]
        for n in missing:
            deck.errors.append(f"--commander '{n}' is not in the decklist")
        commander_names = {n for n in wanted if n in names_in_list}
    else:
        commander_names = {r.name for r in raws if r.marked}
        if not commander_names:
            commander_names = _line1_heuristic(lines, raws, deck)

    merged: dict[str, tuple[int, str, int]] = {}
    order: list[str] = []
    for r in raws:
        if r.name in merged:
            c, raw, ln = merged[r.name]
            merged[r.name] = (c + r.count, raw, ln)
        else:
            merged[r.name] = (r.count, r.raw, r.lineno)
            order.append(r.name)
    for name in order:
        count, raw, lineno = merged[name]
        deck.entries.append(DeckEntry(name, count, name in commander_names, raw, lineno))
    deck.commanders = [n for n in order if n in commander_names]
    if override:
        deck.commanders = [n for n in (front_face(x) for x in override) if n in commander_names]
    return deck


def _line1_heuristic(lines: list[str], raws: list[_Raw], deck: ParsedDeck) -> set[str]:
    """First non-blank line is an entry and the next line is blank → it is the commander."""
    if not raws or not lines:
        return set()
    first = raws[0]
    first_nonblank = next((i for i, l in enumerate(lines, start=1) if l.strip()), None)
    if first_nonblank == first.lineno and first.lineno < len(lines) and not lines[first.lineno].strip():
        deck.warnings.append(
            f"commander taken from line 1 ('{first.name}') because it is followed by a blank line; pass --commander to override"
        )
        return {first.name}
    return set()
