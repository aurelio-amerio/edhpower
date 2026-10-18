"""Which Spellbook lines the simulator plays, and when a line counts as assembled.

Scoped to what the engine can do: 2- and 3-card `included` variants whose pieces live on the
battlefield, in hand or in the command zone, with no `requires` templates. Everything else is
reported as not simulated, never assumed free.
"""

from __future__ import annotations

from dataclasses import dataclass

from edhpower.config import SimConfig
from edhpower.facts import DeckFacts
from edhpower.sim.mana import parse_cost
from edhpower.spellbook import ComboLine

ALLOWED_ZONES = frozenset({"B", "H", "C"})


@dataclass(frozen=True)
class LinePiece:
    name: str
    zones: frozenset[str]


@dataclass(frozen=True)
class SimLine:
    id: str
    label: str
    pieces: tuple[LinePiece, ...]
    extra_mana: int
    lethal: bool


@dataclass(frozen=True)
class SkippedLine:
    label: str
    reason: str


def _label(line: ComboLine) -> str:
    return " + ".join(line.piece_names)


def _skip_reason(line: ComboLine) -> str | None:
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
    return None


def select_lines(facts: DeckFacts, cfg: SimConfig) -> tuple[list[SimLine], list[SkippedLine]]:
    if facts.combos is None:
        return [], []
    ordered = sorted(facts.combos.included, key=lambda l: (-(l.popularity if l.popularity is not None else -1), l.id))
    simulated: list[SimLine] = []
    skipped: list[SkippedLine] = []
    taken = {2: 0, 3: 0}
    caps = {2: cfg.max_two_card_lines, 3: cfg.max_three_card_lines}
    for line in ordered:
        reason = _skip_reason(line)
        if reason is None and taken[len(line.pieces)] >= caps[len(line.pieces)]:
            reason = "over cap"
        if reason is not None:
            skipped.append(SkippedLine(_label(line), reason))
            continue
        taken[len(line.pieces)] += 1
        extra = line.mana_value_needed if isinstance(line.mana_value_needed, int) else parse_cost(line.mana_needed).total
        lethal = any(f in feat.lower() for feat in line.produces for f in cfg.lethal_features)
        pieces = tuple(LinePiece(p.name, frozenset(p.zones) or frozenset({"B"})) for p in line.pieces)
        simulated.append(SimLine(line.id, _label(line), pieces, extra, lethal))
    return simulated, skipped


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
