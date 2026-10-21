"""Effect records: what a permanent or spell does to the board, read from the behaviours table or from a
Card-Forge script. The reader knows a small vocabulary (stage 1: landfall/ETB/token-created triggers that
make tokens, put counters, add mana or drain; anthems; mass pump; land-search ramp spells). Every ability
line or sub-ability it does not understand is returned in `unread`, so nothing is skipped silently.
No card names appear in this module."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from edhpower.scryfall import CardData

if TYPE_CHECKING:
    from edhpower.profile import SpecialBehaviour

TRIGGERS = ("landfall", "etb", "creature_etb", "token_created", "static", "cast")
ACTIONS = ("token", "counters", "anthem", "pump", "mana", "drain")
UNREAD_CHARS = 60


@dataclass(frozen=True)
class Effect:
    on: str
    do: str
    n: int | str = 1  # "lands" = lands you control at resolution
    power: int = 0
    toughness: int = 0
    type: str = ""  # token creature type; scope for anthem/pump/counters ("" all creatures, "tokens", or a creature type)
    each_opponent: bool = True
    when: str = ""  # "" | "distinct_lands >= N" | "lands >= N" | "tokens >= N"
    upgrade: Effect | None = None


@dataclass(frozen=True)
class CardEffects:
    effects: tuple[Effect, ...]
    source: str  # "table" | "forge" | "none"
    unread: tuple[str, ...]  # script lines or sub-abilities (first 60 chars) the reader did not understand
    partial: bool = False  # some effect read, some line/choice/branch not
    ramp_to_battlefield: int = 1
    ramp_to_hand: int = 0


@dataclass(frozen=True)
class ForgeScript:
    keywords: tuple[str, ...]
    triggers: list[dict[str, str]] = field(default_factory=list)
    abilities: list[dict[str, str]] = field(default_factory=list)
    statics: list[dict[str, str]] = field(default_factory=list)
    svars: dict[str, dict[str, str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------- parsing


def _fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in text.split(" | "):
        key, _, value = part.partition("$")
        out[key.strip()] = value.strip()
    return out


def parse_script(text: str) -> ForgeScript:
    """Split a Forge card script into its fields. Only the front face is read (stops at ALTERNATE)."""
    keywords: list[str] = []
    triggers: list[dict[str, str]] = []
    abilities: list[dict[str, str]] = []
    statics: list[dict[str, str]] = []
    svars: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line == "ALTERNATE":
            break
        prefix, sep, body = line.partition(":")
        if not sep:
            continue
        if prefix == "K":
            keywords.append(body)
        elif prefix == "T":
            triggers.append(_fields(body))
        elif prefix == "A":
            abilities.append(_fields(body))
        elif prefix == "S":
            statics.append(_fields(body))
        elif prefix == "SVar":
            name, _, value = body.partition(":")
            svars[name] = _fields(value)
    return ForgeScript(tuple(keywords), triggers, abilities, statics, svars)


def _text(d: dict[str, str]) -> str:
    return " | ".join(f"{k}$ {v}" if v else k for k, v in d.items())


def _clip(text: str) -> str:
    return text[:UNREAD_CHARS]


# ---------------------------------------------------------------------------------------------- reading


def _int(value: str | None, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value.lstrip("+"))
    except ValueError:
        return None


_TOKEN_SCRIPT = re.compile(r"^[a-z]+_(\d+)_(\d+)_(?:a_)?([a-z_]+)$")
# Ability words Forge appends to token script names (w_1_1_bird_flying, c_1_1_eldrazi_scion_sac): not types.
_TOKEN_SUFFIXES = frozenset({"sac", "flying", "haste", "trample", "vigilance", "deathtouch", "lifelink", "reach", "menace",
                             "defender", "hexproof", "indestructible", "decayed", "prowess"})
# Forge card properties that look like creature types in `Creature.<X>+YouCtrl` but are not.
_NOT_TYPES = frozenset({"Other", "StrictlyOther", "White", "Blue", "Black", "Red", "Green", "Colorless", "Multicolor"})
_TREASURE = "c_a_treasure_sac"
_YOUR_CREATURES = re.compile(r"^Creature(?:\.([A-Za-z]+))?(?:\+YouCtrl|\.YouCtrl)$")
_LANDS_COUNT = "Valid Land.YouCtrl"
_DISTINCT_LANDS_COUNT = "Valid Land.YouCtrl$DifferentCardNames"
_OPPONENTS_ALL = ("Player.Opponent", "Opponent")
_IGNORED_STEPS = ("GainLife", "Cleanup")
_BASIC_TYPES = ("Land", "Plains", "Island", "Swamp", "Mountain", "Forest")


def _creature_scope(valid: str) -> str | None:
    """`Creature.YouCtrl` -> "", `Creature.token+YouCtrl` -> "tokens", `Creature.<Type>+YouCtrl` -> type."""
    m = _YOUR_CREATURES.match(valid)
    if m is None:
        return None
    sub = m.group(1)
    if sub is None:
        return ""
    if sub == "token":
        return "tokens"
    return sub if sub[:1].isupper() and sub not in _NOT_TYPES else None


def _amount(value: str | None, svars: dict[str, dict[str, str]]) -> int | str | None:
    """Integer amount (default 1), or "lands" when it names an SVar counting lands you control."""
    n = _int(value, 1)
    if n is not None:
        return n
    if value is not None and svars.get(value) == {"Count": _LANDS_COUNT}:
        return "lands"
    return None


class _Reader:
    def __init__(self, script: ForgeScript) -> None:
        self.s = script
        self.effects: list[Effect] = []
        self.unread: list[str] = []

    def svar_text(self, name: str) -> str:
        return _clip(f"SVar:{name}:{_text(self.s.svars[name])}") if name in self.s.svars else _clip(f"SVar:{name}")

    def chain(self, name: str, on: str, seen: frozenset[str] = frozenset()) -> tuple[list[Effect], list[str]]:
        """Read SVar `name` and its SubAbility$ chain. Returns (effects, unread) without recording them."""
        step = self.s.svars.get(name)
        if step is None or name in seen:
            return [], [self.svar_text(name)]
        effects, unread = self.step(name, step, on, seen | {name})
        sub = step.get("SubAbility")
        if sub:
            more, more_unread = self.chain(sub, on, seen | {name})
            effects += more
            unread += more_unread
        return effects, unread

    def step(self, name: str, d: dict[str, str], on: str, seen: frozenset[str]) -> tuple[list[Effect], list[str]]:
        api = d.get("DB") or d.get("SP") or d.get("AB") or ""
        if api in _IGNORED_STEPS:
            return [], []
        if api == "Branch":
            return self.branch(name, d, on, seen)
        if api in ("Charm", "GenericChoice"):
            return self.charm(d, on, seen)
        effect = _action(api, d, on, self.s.svars)
        if effect is None:
            if api == "PumpAll" and "NumAtt" not in d and "NumDef" not in d and "KW" in d:
                return [], []  # keyword-only mass pump (vigilance until end of turn): not modelled, not a gap
            return [], [self.svar_text(name) if name else _clip(_text(d))]
        return [effect], []

    def branch(self, name: str, d: dict[str, str], on: str, seen: frozenset[str]) -> tuple[list[Effect], list[str]]:
        true_name, false_name = d.get("TrueSubAbility", ""), d.get("FalseSubAbility", "")
        true_fx, true_un = self.chain(true_name, on, seen) if true_name else ([], [])
        false_fx, false_un = self.chain(false_name, on, seen) if false_name else ([], [])
        when = _branch_condition(d, self.s.svars)
        if when is not None and len(true_fx) == 1 and len(false_fx) == 1 and not true_un and not false_un:
            return [replace(false_fx[0], upgrade=replace(true_fx[0], when=when))], []
        if false_fx and not true_fx:
            return false_fx, false_un + (true_un or [self.svar_text(name)])
        if true_fx and not false_fx:
            return true_fx, true_un + (false_un or [self.svar_text(name)])
        if not true_fx and not false_fx:
            return [], [self.svar_text(name)]
        # both branches read but not as a single upgradeable effect: keep the default branch
        return false_fx, false_un + [self.svar_text(true_name)]

    def charm(self, d: dict[str, str], on: str, seen: frozenset[str]) -> tuple[list[Effect], list[str]]:
        """Modal "choose one": the goldfish picks the first understood choice; the others are unread."""
        choices = [c.strip() for c in d.get("Choices", "").split(",") if c.strip()]
        picked: tuple[list[Effect], list[str]] | None = None
        unread: list[str] = []
        for c in choices:
            fx, un = self.chain(c, on, seen)
            if picked is None and fx:
                picked = (fx, un)
            else:
                unread.append(self.svar_text(c))
        if picked is None:
            return [], unread or [_clip(_text(d))]
        return picked[0], picked[1] + unread

    def trigger(self, t: dict[str, str]) -> None:
        on = _trigger_kind(t)
        execute = t.get("Execute", "")
        if on is None or not execute:
            self.unread.append(_clip("T:" + _text(t)))
            return
        fx, un = self.chain(execute, on, frozenset())
        if not fx:
            self.unread.append(_clip("T:" + _text(t)))
            return
        self.effects.extend(fx)
        self.unread.extend(un)


def _trigger_kind(t: dict[str, str]) -> str | None:
    mode = t.get("Mode")
    if mode == "ChangesZone" and t.get("Destination") == "Battlefield":
        valid = t.get("ValidCard", "")
        if valid == "Land.YouCtrl":
            return "landfall"
        if valid == "Card.Self":
            return "etb"
        if valid in ("Creature.Other+YouCtrl", "Creature.YouCtrl+Other"):
            return "creature_etb"
        return None
    if mode == "TokenCreated" and t.get("ValidPlayer") == "You":
        return "token_created"
    return None


def _branch_condition(d: dict[str, str], svars: dict[str, dict[str, str]]) -> str | None:
    compare = d.get("BranchConditionSVarCompare", "")
    n = _int(compare[2:]) if compare.startswith("GE") else None
    if n is None:
        return None
    count = svars.get(d.get("BranchConditionSVar", ""), {}).get("Count")
    if count == _DISTINCT_LANDS_COUNT:
        return f"distinct_lands >= {n}"
    if count == _LANDS_COUNT:
        return f"lands >= {n}"
    return None


def _action(api: str, d: dict[str, str], on: str, svars: dict[str, dict[str, str]]) -> Effect | None:
    if api == "Token":
        if d.get("TokenOwner", "You") != "You":
            return None
        n = _amount(d.get("TokenAmount"), svars)
        script = d.get("TokenScript", "")
        if n is None:
            return None
        if script == _TREASURE:
            return Effect(on, "mana", n)
        m = _TOKEN_SCRIPT.match(script)
        if m is None or (m.group(1), m.group(2)) == ("0", "0"):  # 0/0 tokens get their size from a CDA
            return None
        words = m.group(3).split("_")
        while words and words[-1] in _TOKEN_SUFFIXES:
            words.pop()
        if not words:
            return None
        return Effect(on, "token", n, int(m.group(1)), int(m.group(2)), " ".join(w.title() for w in words))
    if api == "PutCounterAll":
        scope = _creature_scope(d.get("ValidCards", ""))
        n = _int(d.get("CounterNum"), 1)
        if scope is None or d.get("CounterType") != "P1P1" or n is None:
            return None
        return Effect(on, "counters", n, type=scope)
    if api == "PumpAll":
        scope = _creature_scope(d.get("ValidCards", ""))
        p, t = _int(d.get("NumAtt"), 0), _int(d.get("NumDef"), 0)
        if scope is None or p is None or t is None or (p, t) == (0, 0):
            return None
        return Effect(on, "pump", 1, p, t, scope)
    if api == "Mana":
        produced, n = d.get("Produced", ""), _int(d.get("Amount"), 1)
        if n is None or not (produced == "Any" or produced in tuple("WUBRGC")):
            return None
        return Effect(on, "mana", n)
    if api in ("LoseLife", "DealDamage"):
        n = _int(d.get("LifeAmount" if api == "LoseLife" else "NumDmg"))
        if n is None:
            return None
        if d.get("Defined") in _OPPONENTS_ALL:
            return Effect(on, "drain", n)
        if d.get("Defined") == "TargetedPlayer" or d.get("ValidTgts") == "Opponent":
            return Effect(on, "drain", n, each_opponent=False)
        return None
    return None


_STATIC_FRAME = {"Mode", "Affected", "Description", "EffectZone"}


def _static(st: dict[str, str]) -> tuple[Effect | None, bool]:
    """(anthem effect, ignorable). Characteristic-defining and keyword-only statics are ignorable."""
    if st.get("CharacteristicDefining") == "True":
        return None, True
    if st.get("Mode") != "Continuous":
        return None, False
    if set(st) <= _STATIC_FRAME | {"AddKeyword"} and "AddKeyword" in st and st.get("Affected", "").startswith(("Creature", "Card.Self")):
        return None, True
    if set(st) - (_STATIC_FRAME | {"AddPower", "AddToughness", "AddKeyword"}):
        return None, False
    scope = _creature_scope(st.get("Affected", ""))
    p, t = _int(st.get("AddPower"), 0), _int(st.get("AddToughness"), 0)
    if scope is None or p is None or t is None or (p, t) == (0, 0):
        return None, False
    return Effect("static", "anthem", 1, p, t, scope), False


def _is_land_type(change_type: str) -> bool:
    return bool(change_type) and all(part.split(".")[0] in _BASIC_TYPES for part in change_type.split(","))


def _ramp(ability: dict[str, str], svars: dict[str, dict[str, str]]) -> tuple[int, int] | None:
    """(to battlefield, to hand) for a land-search spell's ChangeZone chain; None when it is not one."""
    to_bf = to_hand = 0
    found = False
    step: dict[str, str] | None = ability
    seen: set[str] = set()
    while step is not None:
        api = step.get("SP") or step.get("DB")
        if api == "ChangeZone":
            land = _is_land_type(step.get("ChangeType", ""))
            n = _int(step.get("ChangeNum"), 1) or 0
            dest = step.get("Destination")
            if dest == "Battlefield" and "Library" in step.get("Origin", "").split(",") and land:
                to_bf += n
                found = True
            elif dest == "Hand" and land:
                to_hand += n
                found = True
            elif dest != "Library":
                return None
        elif api != "Cleanup":
            return None
        sub = step.get("SubAbility")
        if not sub or sub in seen:
            break
        seen.add(sub)
        step = svars.get(sub)
    return (to_bf, to_hand) if found else None


def _read_script(text: str) -> CardEffects:
    s = parse_script(text)
    reader = _Reader(s)
    for t in s.triggers:
        reader.trigger(t)
    for st in s.statics:
        effect, ignorable = _static(st)
        if effect is not None:
            reader.effects.append(effect)
        elif not ignorable:
            reader.unread.append(_clip("S:" + _text(st)))
    ramp_bf, ramp_hand = 1, 0
    for a in s.abilities:
        if a.get("AB") == "Mana":
            continue  # mana abilities belong to the mana model, not to the effects reader
        if a.get("SP") == "ChangeZone":
            ramp = _ramp(a, s.svars)
            if ramp is not None:
                ramp_bf, ramp_hand = ramp
                continue
        if "SP" in a:
            fx, un = reader.step("", a, "cast", frozenset())
            sub = a.get("SubAbility")
            if fx and sub:
                more, more_un = reader.chain(sub, "cast", frozenset())
                fx, un = fx + more, un + more_un
            if fx:
                reader.effects.extend(fx)
                reader.unread.extend(un)
                continue
        reader.unread.append(_clip("A:" + _text(a)))
    effects, unread = tuple(reader.effects), tuple(reader.unread)
    return CardEffects(effects, "forge", unread, bool(effects) and bool(unread), ramp_bf, ramp_hand)


def effects_for(card: CardData, script: str | None, special: SpecialBehaviour | None) -> CardEffects:
    """Table effects take precedence over the Forge script; no script means source "none".

    `card` is accepted so callers pass the whole card; stage 1 reads nothing from it."""
    del card
    if special is not None and special.effects:
        return CardEffects(tuple(special.effects), "table", ())
    if script is None:
        return CardEffects((), "none", ())
    return _read_script(script)


_CONDITION = re.compile(r"^(distinct_lands|lands|tokens) >= (\d+)$")


def condition_holds(when: str, distinct_lands: int, lands: int, tokens: int) -> bool:
    if not when:
        return True
    m = _CONDITION.match(when)
    if m is None:
        raise ValueError(f"unknown effect condition {when!r}")
    value = {"distinct_lands": distinct_lands, "lands": lands, "tokens": tokens}[m.group(1)]
    return value >= int(m.group(2))


_TABLE_KEYS = {"on", "do", "n", "power", "toughness", "type", "each_opponent", "when", "upgrade"}


def _table_effect(raw: dict[str, Any]) -> Effect:
    unknown = sorted(set(raw) - _TABLE_KEYS)
    if unknown:
        raise ValueError(f"unknown effect key {unknown[0]!r} in {raw!r}")
    on, do = raw.get("on"), raw.get("do")
    if on not in TRIGGERS:
        raise ValueError(f"effect key 'on' = {on!r} is not one of {TRIGGERS}")
    if do not in ACTIONS:
        raise ValueError(f"effect key 'do' = {do!r} is not one of {ACTIONS}")
    n = raw.get("n", 1)
    if not (isinstance(n, int) or n == "lands"):
        raise ValueError(f"effect key 'n' = {n!r} must be an integer or \"lands\"")
    when = str(raw.get("when", ""))
    if when and _CONDITION.match(when) is None:
        raise ValueError(f"effect key 'when' = {when!r} is not a known condition")
    upgrade = _table_effect(raw["upgrade"]) if "upgrade" in raw else None
    return Effect(on, do, n, int(raw.get("power", 0)), int(raw.get("toughness", 0)), str(raw.get("type", "")),
                  bool(raw.get("each_opponent", True)), when, upgrade)


def parse_effects_table(raw: list[dict]) -> tuple[Effect, ...]:
    return tuple(_table_effect(r) for r in raw)
