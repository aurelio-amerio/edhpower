"""Commander Spellbook: find-my-combos (combo lines) and estimate-bracket (official-criteria flags)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from edhpower.http import HttpClient, HttpError

SPELLBOOK_BASE = "https://backend.commanderspellbook.com"
CLIENT_SCHEMA_VERSION = "6.4.0"  # backend.commanderspellbook.com/schema/ version this parser was written against


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class SpellbookError(Exception):
    pass


@dataclass(frozen=True)
class ComboPiece:
    name: str
    zones: tuple[str, ...]
    must_be_commander: bool


@dataclass(frozen=True)
class ComboTemplate:
    name: str
    zones: tuple[str, ...]


@dataclass(frozen=True)
class ComboLine:
    id: str
    pieces: tuple[ComboPiece, ...]
    templates: tuple[ComboTemplate, ...]
    produces: tuple[str, ...]
    mana_needed: str
    mana_value_needed: int | None
    bracket_tag: str
    popularity: int | None
    notable_prerequisites: str
    description: str

    @property
    def piece_names(self) -> list[str]:
        return [p.name for p in self.pieces]


@dataclass(frozen=True)
class ComboFlags:
    combo_id: str
    definitely_two_card: bool
    arguably_two_card: bool
    speed: int | None
    mass_land_denial: bool
    extra_turn: bool
    lock: bool
    skip_turns: bool
    relevant: bool


@dataclass(frozen=True)
class CardFlags:
    name: str
    game_changer: bool
    mass_land_denial: bool
    extra_turn: bool
    banned: bool


@dataclass
class ComboData:
    identity: str
    included: list[ComboLine]
    almost_included_count: int
    card_flags: dict[str, CardFlags]
    combo_flags: dict[str, ComboFlags]
    spellbook_bracket_tag: str
    fetched_at: str
    schema_version: int = 1
    api_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ComboData:
        return cls(
            identity=d["identity"],
            included=[_line_from_dict(x) for x in d["included"]],
            almost_included_count=d["almost_included_count"],
            card_flags={k: CardFlags(**v) for k, v in d["card_flags"].items()},
            combo_flags={k: ComboFlags(**v) for k, v in d["combo_flags"].items()},
            spellbook_bracket_tag=d["spellbook_bracket_tag"],
            fetched_at=d["fetched_at"],
            schema_version=d.get("schema_version", 1),
            api_version=d.get("api_version", ""),
        )


def _line_from_dict(d: dict[str, Any]) -> ComboLine:
    return ComboLine(
        id=d["id"],
        pieces=tuple(ComboPiece(p["name"], tuple(p["zones"]), p["must_be_commander"]) for p in d["pieces"]),
        templates=tuple(ComboTemplate(t["name"], tuple(t["zones"])) for t in d["templates"]),
        produces=tuple(d["produces"]),
        mana_needed=d["mana_needed"],
        mana_value_needed=d["mana_value_needed"],
        bracket_tag=d["bracket_tag"],
        popularity=d["popularity"],
        notable_prerequisites=d["notable_prerequisites"],
        description=d["description"],
    )


def _parse_line(v: dict[str, Any]) -> ComboLine:
    return ComboLine(
        id=str(v.get("id", "")),
        pieces=tuple(
            ComboPiece(u["card"]["name"], tuple(u.get("zoneLocations") or ()), bool(u.get("mustBeCommander", False)))
            for u in v.get("uses", [])
        ),
        templates=tuple(
            ComboTemplate(t["template"]["name"], tuple(t.get("zoneLocations") or ())) for t in v.get("requires", [])
        ),
        produces=tuple(p["feature"]["name"] for p in v.get("produces", [])),
        mana_needed=v.get("manaNeeded") or "",
        mana_value_needed=v.get("manaValueNeeded") if isinstance(v.get("manaValueNeeded"), int) else None,
        bracket_tag=v.get("bracketTag") or "",
        popularity=v.get("popularity") if isinstance(v.get("popularity"), int) else None,
        notable_prerequisites=v.get("notablePrerequisites") or "",
        description=v.get("description") or "",
    )


class SpellbookClient:
    def __init__(self, http: HttpClient, now: Callable[[], str] = _iso_now) -> None:
        self._http = http
        self._now = now

    @staticmethod
    def _body(commanders: list[str], main: list[tuple[str, int]]) -> dict[str, Any]:
        return {
            "commanders": [{"card": c, "quantity": 1} for c in commanders],
            "main": [{"card": n, "quantity": q} for n, q in main],
        }

    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            status, data = self._http.post(f"{SPELLBOOK_BASE}/{endpoint}", body)
        except HttpError as exc:
            raise SpellbookError(f"{endpoint} failed: {exc}") from exc
        if status != 200 or not isinstance(data, dict):
            raise SpellbookError(f"{endpoint} returned HTTP {status}: {str(data)[:200]}")
        return data

    def fetch(self, commanders: list[str], main: list[tuple[str, int]]) -> ComboData:
        # The Spellbook echo lists only a subset of the cards sent (not just flagged ones), and
        # neither endpoint reports unrecognised names, so a silently ignored name cannot be
        # detected; callers must send Scryfall-canonical names.
        body = self._body(commanders, main)
        fmc = self._post("find-my-combos", body)
        eb = self._post("estimate-bracket", body)

        try:
            results = fmc.get("results") or {}
            included = [_parse_line(v) for v in results.get("included", [])]

            card_flags: dict[str, CardFlags] = {}
            for c in eb.get("cards", []):
                name = c["card"]["name"]
                card_flags[name] = CardFlags(
                    name, bool(c.get("gameChanger")), bool(c.get("massLandDenial")), bool(c.get("extraTurn")), bool(c.get("banned"))
                )
            combo_flags: dict[str, ComboFlags] = {}
            for c in eb.get("combos", []):
                cid = str(c["combo"]["id"])
                combo_flags[cid] = ComboFlags(
                    cid, bool(c.get("definitelyTwoCard")), bool(c.get("arguablyTwoCard")),
                    c.get("speed") if isinstance(c.get("speed"), int) else None,
                    bool(c.get("massLandDenial")), bool(c.get("extraTurn")), bool(c.get("lock")), bool(c.get("skipTurns")),
                    bool(c.get("relevant")),
                )

            return ComboData(
                identity=results.get("identity") or "",
                included=included,
                almost_included_count=len(results.get("almostIncluded", [])),
                card_flags=card_flags,
                combo_flags=combo_flags,
                spellbook_bracket_tag=eb.get("bracketTag") or "",
                fetched_at=self._now(),
                api_version=CLIENT_SCHEMA_VERSION,
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise SpellbookError(f"malformed Spellbook response: {exc!r}") from exc
