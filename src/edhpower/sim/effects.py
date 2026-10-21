"""Effect records: what a permanent or spell does to the board, read from the behaviours table or from a
Card-Forge script. The reader knows a small vocabulary (stage 1: landfall/ETB/token-created triggers that
make tokens, put counters, add mana or drain; anthems; mass pump; land-search ramp spells; stage 2: graveyard
lands, extra land drops, dredge, fetches, upkeep sacrifice, land-sacrifice triggers). Every ability
line or sub-ability it does not understand is returned in `unread`, so nothing is skipped silently.
No card names appear in this module."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from edhpower.scryfall import CardData
from edhpower.sim.mana import parse_activation_cost

if TYPE_CHECKING:
    from edhpower.profile import SpecialBehaviour

TRIGGERS = ("landfall", "etb", "creature_etb", "token_created", "static", "cast", "activated", "upkeep", "land_sacrificed",
            "land_milled", "dies")
ACTIONS = ("token", "counters", "anthem", "pump", "mana", "drain", "mill", "dredge", "extra_land",
           "play_lands_from_graveyard", "return_lands", "return_lands_to_hand", "fetch", "sacrifice_land",
           "chain_lands_from_hand", "reanimate", "draw")
UNREAD_CHARS = 60


@dataclass(frozen=True)
class Effect:
    on: str
    do: str
    n: int | str = 1  # "lands" = lands you control at resolution; "all" = every land card in the graveyard (return_lands);
    #                   "milled" = the lands of the triggering mill (return_lands on land_milled)
    power: int = 0
    toughness: int = 0
    type: str = ""  # reanimate: "creature" | "permanent"; token creature type; scope for anthem/pump/counters ("" all creatures, "tokens", or a creature type);
    #                 dredge: "" = this card has dredge n, "lands" = land cards in your graveyard have dredge n
    each_opponent: bool = True
    when: str = ""  # "" | "distinct_lands >= N" | "lands >= N" | "tokens >= N"
    upgrade: Effect | None = None
    cost: str = ""  # activation or additional cost in Forge spelling ("3 G Sac<1/CARDNAME>"); "" = none
    mv_max: int = 0  # reanimate target filter: mana value cap, 0 = no cap


@dataclass(frozen=True)
class CardEffects:
    effects: tuple[Effect, ...]
    source: str  # "table" | "forge" | "none"
    unread: tuple[str, ...]  # script lines or sub-abilities (first 60 chars) the reader did not understand
    partial: bool = False  # some effect read, some line/choice/branch not
    ramp_to_battlefield: int = 1
    ramp_to_hand: int = 0
    ramp_sacrifice_lands: int = 0  # lands sacrificed as the ramp spell's additional cost (Sac<N/Land>)
    land_search: bool = False  # the reader found a library -> battlefield/hand land search (the ramp fields are meaningful)


@dataclass(frozen=True)
class ForgeScript:
    keywords: tuple[str, ...]
    triggers: list[dict[str, str]] = field(default_factory=list)
    abilities: list[dict[str, str]] = field(default_factory=list)
    statics: list[dict[str, str]] = field(default_factory=list)
    svars: dict[str, dict[str, str]] = field(default_factory=dict)
    replacements: list[dict[str, str]] = field(default_factory=list)
    alternate_mode: str = ""  # AlternateMode$ of a card with a back face
    back_face_types: str | None = None  # Types line of the back face (after ALTERNATE); None when there is none


# ---------------------------------------------------------------------------------------------- parsing


def _fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in text.split(" | "):
        key, _, value = part.partition("$")
        out[key.strip()] = value.strip()
    return out


def parse_script(text: str) -> ForgeScript:
    """Split a Forge card script into its fields. Only the front face's abilities are read; of the back face
    (after ALTERNATE) only its Types line is kept."""
    keywords: list[str] = []
    triggers: list[dict[str, str]] = []
    abilities: list[dict[str, str]] = []
    statics: list[dict[str, str]] = []
    replacements: list[dict[str, str]] = []
    svars: dict[str, dict[str, str]] = {}
    alternate_mode = ""
    back_face_types: str | None = None
    lines = iter(text.splitlines())
    for raw in lines:
        line = raw.strip()
        if line == "ALTERNATE":
            back_face_types = ""
            for back in lines:
                if back.startswith("Types:"):
                    back_face_types = back.partition(":")[2].strip()
                    break
            break
        prefix, sep, body = line.partition(":")
        if not sep:
            continue
        if prefix == "AlternateMode":
            alternate_mode = body.strip()
        elif prefix == "K":
            keywords.append(body)
        elif prefix == "T":
            triggers.append(_fields(body))
        elif prefix == "A":
            abilities.append(_fields(body))
        elif prefix == "S":
            statics.append(_fields(body))
        elif prefix == "R":
            replacements.append(_fields(body))
        elif prefix == "SVar":
            name, _, value = body.partition(":")
            svars[name] = _fields(value)
    return ForgeScript(tuple(keywords), triggers, abilities, statics, svars, replacements, alternate_mode, back_face_types)


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
_LIFE_STEPS = ("LoseLife", "GainLife", "DealDamage")
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
        if api in _IGNORED_STEPS or (api in _LIFE_STEPS and d.get("Defined") == "You"):  # life is not a resource
            return [], []
        if api == "Sacrifice" and on == "upkeep":
            effect = _upkeep_sacrifice(d)
            if effect is not None:
                return [effect], []
        if any(k.startswith(("Condition", "Unless")) for k in d):  # conditional or punisher ("unless they pay") step: fail closed
            return [], [self.svar_text(name) if name else _clip(_text(d))]
        if api == "Branch":
            return self.branch(name, d, on, seen)
        if api in ("Charm", "GenericChoice"):
            return self.charm(d, on, seen)
        effect = _action(api, d, on, self.s.svars)
        if effect is None:
            if api == "PumpAll" and "NumAtt" not in d and "NumDef" not in d and "KW" in d:
                return [], []  # keyword-only mass pump (vigilance until end of turn): not modelled, not a gap
            return [], [self.svar_text(name) if name else _clip(_text(d))]
        if not effect.cost and "Sac<" in d.get("Cost", ""):  # a sacrifice cost the model does not pay
            return [effect], [_clip(f"Cost$ {d['Cost']}")]
        return [effect], []

    def branch(self, name: str, d: dict[str, str], on: str, seen: frozenset[str]) -> tuple[list[Effect], list[str]]:
        true_name, false_name = d.get("TrueSubAbility", ""), d.get("FalseSubAbility", "")
        true_fx, true_un = self.chain(true_name, on, seen) if true_name else ([], [])
        false_fx, false_un = self.chain(false_name, on, seen) if false_name else ([], [])
        when = _branch_condition(d, self.s.svars)
        if when is not None and len(true_fx) == 1 and len(false_fx) == 1 and not true_un and not false_un:
            return [replace(false_fx[0], upgrade=replace(true_fx[0], when=when))], []
        if false_fx and not true_fx:  # the upgrade branch is not understood: the default effect, unconditioned
            return false_fx, false_un + (true_un or [self.svar_text(name)])
        if true_fx and not false_fx:  # the effect happens only when the condition holds
            if when is None:
                return [], [self.svar_text(name)]
            return [replace(e, when=when) for e in true_fx], true_un + false_un
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
        kinds = _trigger_kinds(t)
        execute = t.get("Execute", "")
        if not kinds or not execute:
            self.unread.append(_clip("T:" + _text(t)))
            return
        for i, on in enumerate(kinds):  # a trigger that fires from several events yields one effect list per event
            fx, un = self.chain(execute, on, frozenset())
            if not fx:
                self.unread.append(_clip("T:" + _text(t)))
                return
            self.effects.extend(fx)
            if i == 0:
                self.unread.extend(un)


_TRIGGER_KEYS = frozenset({"Mode", "Origin", "Destination", "ValidCard", "ValidPlayer", "ValidToken", "TriggerZones", "Execute",
                           "TriggerDescription", "OptionalDecider", "Secondary", "Phase", "ValidCards"})
_YOUR_TOKENS = ("Card.token+YouCtrl", "Creature.token+YouCtrl")


_YOUR_LAND_CARDS = ("Land.YouOwn", "Land.YouOwn+!token")


def _trigger_kinds(t: dict[str, str]) -> tuple[str, ...]:
    """The trigger's kinds (empty when any key or value is outside the read vocabulary: fail closed). Lands put into
    your graveyard "from anywhere" are both milled and sacrificed, hence several."""
    if t.get("Mode") == "ChangesZoneAll" and t.get("Destination") == "Graveyard" and t.get("ValidCards") in _YOUR_LAND_CARDS \
            and not set(t) - _TRIGGER_KEYS and t.get("TriggerZones", "Battlefield") == "Battlefield":
        return {"Library": ("land_milled",), "Any": ("land_milled", "land_sacrificed")}.get(t.get("Origin", "Any"), ())
    kind = _trigger_kind(t)
    return (kind,) if kind else ()


def _trigger_kind(t: dict[str, str]) -> str | None:
    """The kind of a single-event trigger, or None when any key or value is outside the read vocabulary (fail closed)."""
    if set(t) - _TRIGGER_KEYS or t.get("TriggerZones", "Battlefield") != "Battlefield" or "ValidCards" in t:
        return None
    if "ValidToken" in t and t["ValidToken"] not in _YOUR_TOKENS:
        return None
    mode, origin = t.get("Mode"), t.get("Origin", "Any")
    if mode == "ChangesZone" and (origin, t.get("Destination")) == ("Battlefield", "Graveyard"):
        return {"Land.YouCtrl": "land_sacrificed", "Card.Self": "dies"}.get(t.get("ValidCard", ""))
    if origin != "Any":
        return None
    if mode == "Phase" and t.get("Phase") == "Upkeep" and t.get("ValidPlayer") == "You":
        return "upkeep"
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
    if api == "Mill":
        n = _int(d.get("NumCards"))
        return Effect(on, "mill", n) if n is not None and d.get("Defined") == "You" else None
    if api == "Effect":
        return _extra_land_effect(on, d, svars)
    if api in ("ChangeZone", "ChangeZoneAll"):
        return _zone_action(api, on, d)
    if api == "Draw":
        n = _int(d.get("NumCards"), 1)
        cost = _zone_cost(d, allow_mana=True)
        if n is None or n <= 0 or cost is None or d.get("Defined", "You") != "You" or "ValidTgts" in d:
            return None
        return Effect(on, "draw", n, cost=cost)
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


_YOUR_LANDS = ("Land.YouCtrl", "Land.YouOwn")
_DREDGE = re.compile(r"^Dredge:(\d+)$")
_UPKEEP_SAC_KEYS = frozenset({"DB", "UnlessPayer", "UnlessCost", "SpellDescription", "StackDescription"})
_UNLESS_SAC_LAND = re.compile(r"^Sac<(\d+)/Land>$")


def _upkeep_sacrifice(d: dict[str, str]) -> Effect | None:
    """`DB$ Sacrifice | UnlessPayer$ You | UnlessCost$ Sac<N/Land>`: sacrifice N lands, else this permanent."""
    m = _UNLESS_SAC_LAND.match(d.get("UnlessCost", ""))
    if m is None or d.get("UnlessPayer") != "You" or set(d) - _UPKEEP_SAC_KEYS:
        return None
    return Effect("upkeep", "sacrifice_land", int(m.group(1)))


def _extra_land_effect(on: str, d: dict[str, str], svars: dict[str, dict[str, str]]) -> Effect | None:
    """`SP$ Effect | StaticAbilities$ X` where X grants additional land plays this turn."""
    static = svars.get(d.get("StaticAbilities", ""))
    n = _int(static.get("AdjustLandPlays")) if static else None
    if static is None or n is None or static.get("Mode") != "Continuous" or static.get("Affected") != "You":
        return None
    return Effect(on, "extra_land", n) if set(static) <= _STATIC_FRAME | {"AdjustLandPlays"} else None


def _zone_cost(d: dict[str, str], allow_mana: bool) -> str | None:
    """The ability's `Cost$` when it parses (and, unless `allow_mana`, holds no mana); None when it does not."""
    cost = d.get("Cost", "")
    try:
        parsed = parse_activation_cost(cost)
    except ValueError:
        return None
    if parsed.mana.total and not allow_mana:
        return None
    return cost


def _fetch_count(d: dict[str, str]) -> int | None:
    """Lands a library search finds: `ChangeNum$` (default 1), or the number of `&` parts of `EACH A & B`."""
    change_type = d.get("ChangeType", "")
    if change_type.startswith("EACH "):
        parts = [p.strip() for p in change_type[5:].split("&")]
        return len(parts) if all(_is_land_type(p) for p in parts) else None
    return _int(d.get("ChangeNum"), 1) if _is_land_type(change_type) else None


_REANIMATE_CREATURE = ("Creature", "Creature.YouCtrl", "Creature.YouOwn")
_REANIMATE_PERMANENT = re.compile(r"^Permanent(?:\.YouCtrl(?:\+cmcLE(\d+))?|\.cmcLE(\d+)\+YouCtrl)$")


def _reanimate(on: str, d: dict[str, str]) -> Effect | None:
    """`ChangeZone` from your graveyard to the battlefield, one targeted creature or (mana-value capped) permanent card."""
    valid, n, cost = d.get("ValidTgts", ""), _int(d.get("TargetMax"), 1), _zone_cost(d, allow_mana=True)
    if not n or cost is None or _int(d.get("ChangeNum"), 1) != 1:
        return None
    if valid in _REANIMATE_CREATURE:
        return Effect(on, "reanimate", n, type="creature", cost=cost)
    m = _REANIMATE_PERMANENT.match(valid)
    if m is None:
        return None
    return Effect(on, "reanimate", n, type="permanent", cost=cost, mv_max=int(m.group(1) or m.group(2) or 0))


def _zone_action(api: str, on: str, d: dict[str, str]) -> Effect | None:
    origin, dest = d.get("Origin"), d.get("Destination")
    if api == "ChangeZoneAll":
        if (origin, dest, d.get("ChangeType")) in (("Graveyard", "Battlefield", "Land.YouCtrl"), ("Graveyard", "Battlefield", "Land.YouOwn")):
            cost = _zone_cost(d, allow_mana=on == "activated")
            return None if cost is None else Effect(on, "return_lands", "all", cost=cost)
        if (origin, dest, d.get("ChangeType"), on) == ("Graveyard", "Battlefield", "Card.TriggeredCards", "land_milled"):
            return Effect(on, "return_lands", "milled")
        return None
    if origin == "Graveyard" and dest == "Battlefield" and api == "ChangeZone":
        reanimate = _reanimate(on, d)
        if reanimate is not None:
            return reanimate
    if origin == "Library" and dest == "Battlefield":
        n = _fetch_count(d)
        cost = _zone_cost(d, allow_mana=on == "activated")
        if n is None or cost is None or on == "cast" or ("AB" not in d and "DB" not in d):
            return None
        return Effect(on, "fetch", n, cost=cost)
    if origin == "Graveyard" and d.get("ValidTgts") in _YOUR_LANDS and "Cost" not in d:
        if dest == "Battlefield":
            n = _int(d.get("TargetMax"), 1)
            return Effect(on, "return_lands", n) if n else None
        if dest == "Hand":
            n = _int(d.get("TargetMax"))
            return Effect(on, "return_lands_to_hand", n) if n else None
    return None


_STATIC_FRAME = {"Mode", "Affected", "Description", "EffectZone"}


def _static(st: dict[str, str]) -> tuple[Effect | None, bool]:
    """(anthem effect, ignorable). Characteristic-defining and keyword-only statics are ignorable."""
    if st.get("CharacteristicDefining") == "True":
        return None, True
    if st.get("Mode") != "Continuous":
        return None, False
    keys = set(st)
    if keys <= _STATIC_FRAME | {"AdjustLandPlays"} and st.get("Affected") == "You" and _int(st.get("AdjustLandPlays")) is not None:
        return Effect("static", "extra_land", _int(st["AdjustLandPlays"]) or 0), False
    if keys <= _STATIC_FRAME | {"AffectedZone", "MayPlay"} and st.get("Affected") in _YOUR_LANDS \
            and (st.get("MayPlay"), st.get("AffectedZone")) == ("True", "Graveyard"):
        return Effect("static", "play_lands_from_graveyard"), False
    dredge = _DREDGE.match(st.get("AddKeyword", ""))
    if keys <= _STATIC_FRAME | {"AffectedZone", "AddKeyword"} and dredge and st.get("AffectedZone") == "Graveyard" \
            and st.get("Affected") == "Land.YouOwn":
        return Effect("static", "dredge", int(dredge.group(1)), type="lands"), False
    if "MayLookAt" in st and keys <= _STATIC_FRAME | {"AffectedZone", "MayLookAt"}:
        return None, True
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


_SAC = re.compile(r"Sac<([^/>]+)/([^>]+)>")


def _land_sacrifice(cost: str) -> int | None:
    """Lands sacrificed by `cost` (Sac<N/Land>); None when it holds any other sacrifice."""
    total = 0
    for num, what in _SAC.findall(cost):
        n = _int(num)
        if n is None or what != "Land":
            return None
        total += n
    return total


_COMPARE = re.compile(r"^Compare \w+ GE\d+\.(\d+)\.(\d+)$")


def _change_num(step: dict[str, str], svars: dict[str, dict[str, str]]) -> tuple[int, str | None] | None:
    """(lands, unread note) for a search step's `ChangeNum$`; None when it is neither an integer nor a floor-able X."""
    raw = step.get("ChangeNum")
    n = _int(raw, 1)
    if n is not None:
        return n, None
    m = _COMPARE.match(svars.get(raw or "", {}).get("Count", ""))
    if m is None:
        return None
    floor = min(int(m.group(1)), int(m.group(2)))
    return floor, _clip(f"ChangeNum$ {raw} read as {floor}")


def _ramp(ability: dict[str, str], svars: dict[str, dict[str, str]]) -> tuple[int, int, int, list[str]] | None:
    """(to battlefield, to hand, lands sacrificed, unread notes) for a land-search spell's chain; None when it is not one."""
    sacrificed = _land_sacrifice(ability.get("Cost", ""))
    if sacrificed is None:
        return None
    to_bf = to_hand = 0
    notes: list[str] = []
    found = False
    step: dict[str, str] | None = ability
    seen: set[str] = set()
    while step is not None:
        api = step.get("SP") or step.get("DB")
        if any(k.startswith(("Condition", "Unless")) for k in step):
            return None
        if api == "ChangeZone":
            land = _is_land_type(step.get("ChangeType", ""))
            num = _change_num(step, svars)
            dest = step.get("Destination")
            library = "Library" in step.get("Origin", "").split(",")
            if num is None:
                return None
            n, note = num
            if dest == "Battlefield" and library and land:
                to_bf += n
                found = True
            elif dest == "Hand" and library and land:
                to_hand += n
                found = True
            elif dest != "Library":
                return None
            if note and found:
                notes.append(note)
        elif api == "Sacrifice" and step is ability and step.get("Defined") == "You" and step.get("SacValid") == "Land":
            sacrificed += 1
        elif api != "Cleanup":
            return None
        sub = step.get("SubAbility")
        if not sub or sub in seen:
            break
        seen.add(sub)
        step = svars.get(sub)
    return (to_bf, to_hand, sacrificed, notes) if found else None


# Keywords with no effect on a goldfish board, mana or win clock beyond what the model already reads (combat,
# evasion, protection, casting timing, type-changing). Every other K: line is unread.
_IGNORED_KEYWORDS = frozenset({
    "Flying", "Trample", "Reach", "Vigilance", "Haste", "Menace", "Deathtouch", "Lifelink", "First Strike", "Double Strike",
    "Defender", "Indestructible", "Hexproof", "Shroud", "Ward", "Protection", "Flash", "Devoid", "Changeling", "Cycling",
    "TypeCycling", "Landwalk", "Horsemanship", "Shadow", "Fear", "Intimidate", "Skulk",
})


def _self_enters_tapped(r: dict[str, str], svars: dict[str, dict[str, str]]) -> bool:
    """`R:` "this enters tapped": read by the mana model, not here."""
    if (r.get("Event"), r.get("ValidCard"), r.get("Destination")) != ("Moved", "Card.Self", "Battlefield"):
        return False
    tap = svars.get(r.get("ReplaceWith", ""), {})
    return tap.get("DB") == "Tap" and tap.get("ETB") == "True" and tap.get("Defined") in ("Self", "ReplacedCard")


def _read_script(text: str) -> CardEffects:
    s = parse_script(text)
    reader = _Reader(s)
    dredge: list[Effect] = []
    for k in s.keywords:
        m = _DREDGE.match(k)
        if m is not None:
            dredge.append(Effect("static", "dredge", int(m.group(1))))
        elif k.split(":")[0].split(" from ")[0] not in _IGNORED_KEYWORDS:
            reader.unread.append(_clip("K:" + k))
    for r in s.replacements:
        if not _self_enters_tapped(r, s.svars):
            reader.unread.append(_clip("R:" + _text(r)))
    if s.back_face_types is not None and "Land" not in s.back_face_types.split():
        reader.unread.append(_clip(f"ALTERNATE: {s.alternate_mode or s.back_face_types}"))
    for t in s.triggers:
        reader.trigger(t)
    for st in s.statics:
        effect, ignorable = _static(st)
        if effect is not None:
            reader.effects.append(effect)
        elif not ignorable:
            reader.unread.append(_clip("S:" + _text(st)))
    ramp_bf, ramp_hand, ramp_sac, land_search = 1, 0, 0, False
    for a in s.abilities:
        if a.get("AB") == "Mana":
            continue  # mana abilities belong to the mana model, not to the effects reader
        if a.get("SP") in ("ChangeZone", "Sacrifice"):
            ramp = _ramp(a, s.svars)
            if ramp is not None:
                ramp_bf, ramp_hand, ramp_sac, notes = ramp
                reader.unread.extend(notes)
                land_search = True
                continue
        if "AB" in a and "SubAbility" not in a:
            fx, un = reader.step("", a, "activated", frozenset())
            if fx and all(e.cost for e in fx):  # an activated ability is read only when its cost is
                reader.effects.extend(fx)
                reader.unread.extend(un)
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
    reader.effects.extend(dredge)
    effects, unread = tuple(reader.effects), tuple(reader.unread)
    return CardEffects(effects, "forge", unread, bool(effects) and bool(unread), ramp_bf, ramp_hand, ramp_sac, land_search)


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


_TABLE_KEYS = {"on", "do", "n", "power", "toughness", "type", "each_opponent", "when", "upgrade", "cost", "mv_max"}


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
    if not (isinstance(n, int) or n in ("lands", "all", "milled")):
        raise ValueError(f"effect key 'n' = {n!r} must be an integer, \"lands\", \"all\" or \"milled\"")
    if n == "all" and do != "return_lands":
        raise ValueError(f"effect key 'n' = \"all\" is only for do = \"return_lands\", not {do!r}")
    if n == "milled" and not (do == "return_lands" and on == "land_milled"):
        raise ValueError(f"effect key 'n' = \"milled\" is only for do = \"return_lands\" on = \"land_milled\", not {do!r} on {on!r}")
    if raw.get("type") == "lands" and do != "dredge":
        raise ValueError(f"effect key 'type' = \"lands\" is only for do = \"dredge\", not {do!r}")
    cost = str(raw.get("cost", ""))
    parse_activation_cost(cost)
    when = str(raw.get("when", ""))
    if when and _CONDITION.match(when) is None:
        raise ValueError(f"effect key 'when' = {when!r} is not a known condition")
    upgrade = _table_effect(raw["upgrade"]) if "upgrade" in raw else None
    return Effect(on, do, n, int(raw.get("power", 0)), int(raw.get("toughness", 0)), str(raw.get("type", "")),
                  bool(raw.get("each_opponent", True)), when, upgrade, cost, int(raw.get("mv_max", 0)))


def parse_effects_table(raw: list[dict]) -> tuple[Effect, ...]:
    return tuple(_table_effect(r) for r in raw)
