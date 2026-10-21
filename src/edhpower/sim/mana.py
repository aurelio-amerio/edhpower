"""Mana costs and colour-aware payment for the simulator. Pure; no card names."""

from __future__ import annotations

import re
from dataclasses import dataclass

COLORS: tuple[str, ...] = ("W", "U", "B", "R", "G")
ANY_COLOR: frozenset[str] = frozenset(COLORS)
COLORLESS: frozenset[str] = frozenset({"C"})

Unit = frozenset[str]  # one mana, as the set of kinds the source can make it as

_SYMBOL = re.compile(r"\{([^}]+)\}")


@dataclass(frozen=True)
class Pip:
    options: frozenset[str]
    generic: int = 0      # {2/W}: payable with `generic` generic mana instead
    free: bool = False    # Phyrexian: payable with 2 life, which a goldfish always has


@dataclass(frozen=True)
class ManaCost:
    generic: int
    pips: tuple[Pip, ...]

    @property
    def total(self) -> int:
        return self.generic + len(self.pips)


def parse_cost(text: str) -> ManaCost:
    generic = 0
    pips: list[Pip] = []
    for sym in _SYMBOL.findall(text or ""):
        sym = sym.upper()
        if sym.isdigit():
            generic += int(sym)
        elif sym in ("X", "Y", "Z"):
            continue
        elif sym == "S":
            generic += 1
        elif "/" in sym:
            parts = sym.split("/")
            if "P" in parts:
                pips.append(Pip(frozenset(p for p in parts if p != "P"), free=True))
            elif parts[0].isdigit():
                pips.append(Pip(frozenset(parts[1:]), generic=int(parts[0])))
            else:
                pips.append(Pip(frozenset(parts)))
        elif sym in ANY_COLOR or sym == "C":
            pips.append(Pip(frozenset({sym})))
        # anything else ({T}, {Q}, {E}, {CHAOS}) is not mana
    return ManaCost(generic, tuple(pips))


def pay(cost: ManaCost, units: list[Unit], reduction: int = 0) -> list[Unit] | None:
    """Units left after paying `cost`, or None if it cannot be paid.

    Phyrexian pips cost life, never mana, so they are skipped outright. The rest is greedy, not
    an exact matching: strict pips are paid first with the least flexible unit that fits, then
    hybrid pips, then the generic part from the least flexible units left. Being greedy, it can
    refuse a payment an exact bipartite matching would find when two hybrid pips compete for one
    unit while a more flexible unit sits unused — rare enough to accept and document.
    """
    remaining = sorted(units, key=len)
    generic_due = max(cost.generic - reduction, 0)
    for pip in sorted(cost.pips, key=lambda p: len(p.options)):
        if pip.free:
            continue
        idx = next((i for i, u in enumerate(remaining) if pip.options & u), None)
        if idx is not None:
            remaining.pop(idx)
        elif pip.generic:
            generic_due += pip.generic
        else:
            return None
    if len(remaining) < generic_due:
        return None
    return remaining[generic_due:]


def can_pay(cost: ManaCost, units: list[Unit], reduction: int = 0) -> bool:
    return pay(cost, units, reduction) is not None


@dataclass(frozen=True)
class ActivationCost:
    mana: ManaCost
    tap: bool = False
    sacrifice_self: bool = False
    sacrifice_lands: int = 0
    sacrifice_creatures: int = 0


_COST_PART = re.compile(r"[^\s<>]+(?:<[^>]*>)?")
_MANA_PART = re.compile(r"^(?:\d+|[WUBRGC](?:/[WUBRGCP])?)$")
_SAC_PART = re.compile(r"^Sac<(\d+)/(CARDNAME|Land|Creature)(?:/[^>]*)?>$")
_LIFE_PART = re.compile(r"^PayLife<\d+>$")


def parse_activation_cost(text: str) -> ActivationCost:
    """Parse a Forge `Cost$` ("3 G Sac<1/CARDNAME>"). Life is not a resource, so PayLife<N> is accepted and
    dropped; any part outside mana, T, PayLife<N> and Sac<N/CARDNAME|Land|Creature> raises ValueError naming it."""
    mana: list[str] = []
    tap = sacrifice_self = False
    lands = creatures = 0
    for part in _COST_PART.findall(text or ""):
        if part == "T":
            tap = True
        elif _MANA_PART.match(part):
            mana.append("{" + part + "}")
        elif _LIFE_PART.match(part):
            continue
        elif (m := _SAC_PART.match(part)) is not None:
            n, what = int(m.group(1)), m.group(2)
            if what == "CARDNAME":
                sacrifice_self = True
            elif what == "Land":
                lands += n
            else:
                creatures += n
        else:
            raise ValueError(f"unsupported activation cost part {part!r} in {text!r}")
    return ActivationCost(parse_cost("".join(mana)),
                          tap, sacrifice_self, lands, creatures)
