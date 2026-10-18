"""Scryfall card data model and resolving client with a local JSONL cache."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edhpower.decklist import DFC_SEPARATOR, front_face
from edhpower.http import HttpClient, HttpError


@dataclass(frozen=True)
class CardFace:
    name: str
    mana_cost: str
    type_line: str
    oracle_text: str


@dataclass(frozen=True)
class CardData:
    name: str
    cmc: float
    mana_cost: str
    type_line: str
    oracle_text: str
    power: str | None
    toughness: str | None
    colors: tuple[str, ...]
    color_identity: tuple[str, ...]
    produced_mana: tuple[str, ...]
    keywords: tuple[str, ...]
    edhrec_rank: int | None
    price_usd: float | None
    price_eur: float | None
    commander_legal: bool
    game_changer: bool
    reserved: bool
    set_code: str
    collector_number: str
    layout: str
    faces: tuple[CardFace, ...]
    fetched_at: str | None = None

    @classmethod
    def from_scryfall(cls, obj: dict[str, Any]) -> CardData:
        faces_raw = obj.get("card_faces") or []
        faces = tuple(
            CardFace(f.get("name", ""), f.get("mana_cost", ""), f.get("type_line", ""), f.get("oracle_text", ""))
            for f in faces_raw
        )
        front = faces_raw[0] if faces_raw else {}
        oracle = obj.get("oracle_text")
        if oracle is None:
            oracle = "\n//\n".join(f.oracle_text for f in faces)
        prices = obj.get("prices") or {}
        return cls(
            name=obj["name"],
            cmc=float(obj.get("cmc") or 0.0),
            mana_cost=obj.get("mana_cost") if obj.get("mana_cost") is not None else front.get("mana_cost", ""),
            type_line=obj.get("type_line", ""),
            oracle_text=oracle,
            power=obj.get("power", front.get("power")),
            toughness=obj.get("toughness", front.get("toughness")),
            colors=tuple(obj.get("colors") or front.get("colors") or []),
            color_identity=tuple(obj.get("color_identity") or []),
            produced_mana=tuple(obj.get("produced_mana") or []),
            keywords=tuple(obj.get("keywords") or []),
            edhrec_rank=obj.get("edhrec_rank") if isinstance(obj.get("edhrec_rank"), int) else None,
            price_usd=_price(prices.get("usd")),
            price_eur=_price(prices.get("eur")),
            commander_legal=(obj.get("legalities") or {}).get("commander") == "legal",
            game_changer=bool(obj.get("game_changer", False)),
            reserved=bool(obj.get("reserved", False)),
            set_code=obj.get("set", ""),
            collector_number=str(obj.get("collector_number", "")),
            layout=obj.get("layout", "normal"),
            faces=faces,
            fetched_at=obj.get(FETCHED_KEY),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CardData:
        d = dict(d)
        d["faces"] = tuple(CardFace(**f) for f in d.get("faces", []))
        for k in ("colors", "color_identity", "produced_mana", "keywords"):
            d[k] = tuple(d.get(k, ()))
        d.setdefault("fetched_at", None)
        return cls(**d)

    @property
    def front_type_line(self) -> str:
        return self.type_line.split(DFC_SEPARATOR, 1)[0]

    @property
    def is_land(self) -> bool:
        return "Land" in self.front_type_line

    @property
    def is_basic_land(self) -> bool:
        return self.front_type_line.startswith("Basic Land")

    def lookup_keys(self) -> list[str]:
        keys = [self.name.lower()]
        keys.extend(f.name.lower() for f in self.faces if f.name.lower() not in keys)
        return keys


def _price(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


SCRYFALL_BASE = "https://api.scryfall.com"
FETCHED_KEY = "_edhpower_fetched_at"  # stamped into every cached object; Scryfall never sends it
COLLECTION_BATCH = 75
NAMED_MIN_INTERVAL = 1.0


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


@dataclass
class Resolution:
    cards: dict[str, CardData]
    unresolved: list[str]
    network_requests: int
    cache_updated_at: str | None
    fetched_oldest: str | None = None
    fetched_newest: str | None = None
    fetched_unknown: int = 0


class ScryfallClient:
    def __init__(self, http: HttpClient, cache_path: Path, now: Callable[[], str] = _iso_now) -> None:
        self._http = http
        self._path = Path(cache_path)
        self._meta_path = self._path.with_suffix(".meta.json")
        self._now = now
        self._index: dict[str, CardData] = {}
        self._faces: dict[str, CardData] = {}
        self._load()

    # -- cache -------------------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    card = CardData.from_scryfall(obj)
                except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                    continue
                self._add_to_index(card)

    def _add_to_index(self, card: CardData) -> None:
        self._index[_norm(card.name)] = card
        for face in card.faces:
            self._faces[_norm(face.name)] = card

    def _lookup(self, key: str) -> CardData | None:
        return self._index.get(key) or self._faces.get(key)

    def _append(self, objs: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        stamp = self._now()
        with self._path.open("a", encoding="utf-8") as fh:
            for obj in objs:
                obj = {**obj, FETCHED_KEY: stamp}
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
                self._add_to_index(CardData.from_scryfall(obj))
        self._meta_path.write_text(json.dumps({"updated_at": stamp}), encoding="utf-8")

    def cache_updated_at(self) -> str | None:
        if not self._meta_path.exists():
            return None
        return json.loads(self._meta_path.read_text(encoding="utf-8")).get("updated_at")

    # -- resolve -----------------------------------------------------------
    @staticmethod
    def _key(name: str) -> str:
        return _norm(front_face(name))

    def resolve(self, names: Iterable[str]) -> Resolution:
        names = list(names)
        requests_made = 0

        # key -> first original spelling (front face), so requests carry the user's spelling
        original: dict[str, str] = {}
        for n in names:
            key = self._key(n)
            if self._lookup(key) is None:
                original.setdefault(key, front_face(n))
        unique_missing = list(original)

        for start in range(0, len(unique_missing), COLLECTION_BATCH):
            chunk = unique_missing[start : start + COLLECTION_BATCH]
            requests_made += 1
            status, body = self._http.post(
                f"{SCRYFALL_BASE}/cards/collection",
                {"identifiers": [{"name": original[k]} for k in chunk]},
            )
            if status != 200:
                raise HttpError(status, str(body))
            if body:
                self._append(body.get("data", []))

        still_missing = [k for k in unique_missing if self._lookup(k) is None]
        if still_missing:
            slow = self._http.with_min_interval(NAMED_MIN_INTERVAL)
            for key in still_missing:
                requests_made += 1
                status, body = slow.get(f"{SCRYFALL_BASE}/cards/named", params={"exact": original[key]})
                if status != 200 and status != 404:
                    raise HttpError(status, str(body))
                if status == 200 and body and body.get("object") == "card":
                    self._append([body])

        cards: dict[str, CardData] = {}
        unresolved: list[str] = []
        for n in names:
            card = self._lookup(self._key(n))
            if card is None:
                unresolved.append(n)
            else:
                cards[n] = card
        stamps = [c.fetched_at for c in cards.values()]
        known = sorted(s for s in stamps if s is not None)
        return Resolution(
            cards, unresolved, requests_made, self.cache_updated_at(),
            fetched_oldest=known[0] if known else None,
            fetched_newest=known[-1] if known else None,
            fetched_unknown=sum(1 for s in stamps if s is None),
        )
