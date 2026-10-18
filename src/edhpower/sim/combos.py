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
