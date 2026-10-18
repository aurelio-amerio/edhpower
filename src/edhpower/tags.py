"""Scryfall oracle-tag cache: one JSON file per verified slug, built by paging the search API."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from edhpower.http import HttpClient, HttpError

SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search"
TAG_MIN_INTERVAL = 1.0
TAG_CACHE_VERSION = 1

# Verified slugs (spec §tags.py, probed 2026-09-10; values are legal:commander counts at probe time,
# informational only — the cache records fresh counts). Anything not listed here is a configuration error.
TAG_TABLE: dict[str, int] = {
    "ramp": 2125,
    "mana-rock": 350,
    "mana-dork": 414,
    "land-ramp": 578,
    "ritual": 59,
    "cost-reducer": 297,
    "tutor": 1106,
    "removal": 6146,
    "counterspell": 517,
    "board-wipe": 901,
    "card-advantage": 5739,
    "cantrip": 618,
    "extra-turn": 53,
    "mass-land-denial": 106,
    "pitch-spell": 42,
    "tax": 432,
    "hatebear": 60,
    "reanimate": 987,
    "cheat-into-play": 242,
    "extra-combat": 45,
    "copy-spell": 177,
}


class TagConfigError(Exception):
    """A tag slug Scryfall does not know. Always a configuration error, never an empty set."""


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class TagSet:
    slug: str
    names: frozenset[str]
    fetched_at: str
    total_cards: int
    query: str


@dataclass
class TagCache:
    sets: dict[str, TagSet] = field(default_factory=dict)

    def missing(self) -> list[str]:
        return [slug for slug in TAG_TABLE if slug not in self.sets]

    @property
    def complete(self) -> bool:
        return not self.missing()

    def tags_for(self, name: str) -> tuple[str, ...]:
        return tuple(sorted(slug for slug, ts in self.sets.items() if name in ts.names))

    def fetched_range(self) -> tuple[str | None, str | None]:
        stamps = sorted(ts.fetched_at for ts in self.sets.values())
        return (stamps[0], stamps[-1]) if stamps else (None, None)


def _path(cache_dir: Path, slug: str) -> Path:
    return Path(cache_dir) / f"{slug}.json"


def load_tag_cache(cache_dir: Path) -> TagCache:
    sets: dict[str, TagSet] = {}
    for slug in TAG_TABLE:
        p = _path(cache_dir, slug)
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("version") != TAG_CACHE_VERSION or d.get("slug") != slug:
                continue
            sets[slug] = TagSet(slug, frozenset(d["names"]), str(d["fetched_at"]), int(d["total_cards"]), str(d.get("query", "")))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return TagCache(sets)


def save_tag_set(cache_dir: Path, ts: TagSet) -> None:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    payload = {
        "version": TAG_CACHE_VERSION,
        "slug": ts.slug,
        "query": ts.query,
        "fetched_at": ts.fetched_at,
        "total_cards": ts.total_cards,
        "names": sorted(ts.names),
    }
    _path(cache_dir, ts.slug).write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")


class TagFetcher:
    def __init__(
        self,
        http: HttpClient,
        cache_dir: Path,
        now: Callable[[], str] = _iso_now,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self._http = http.with_min_interval(TAG_MIN_INTERVAL)
        self._dir = Path(cache_dir)
        self._now = now
        self._progress = progress

    def fetch(self, slug: str) -> TagSet:
        if slug not in TAG_TABLE:
            raise TagConfigError(f"'{slug}' is not in the verified tag table (edhpower.tags.TAG_TABLE)")
        query = f"otag:{slug} legal:commander"
        names: set[str] = set()
        page = 1
        total = 0
        while True:
            status, body = self._http.get(SCRYFALL_SEARCH, params={"q": query, "unique": "cards", "page": page})
            if status == 404 and isinstance(body, dict) and body.get("code") == "not_found":
                raise TagConfigError(
                    f"Scryfall returned not_found for '{query}': the slug does not exist (or the tag is empty). Fix TAG_TABLE; this is never an empty set."
                )
            if status != 200 or not isinstance(body, dict):
                raise HttpError(status, str(body))
            total = int(body.get("total_cards") or 0)
            names.update(c["name"] for c in body.get("data", []) if isinstance(c, dict) and "name" in c)
            if self._progress:
                self._progress(f"tags: {slug} page {page} ({len(names)}/{total} cards)")
            if not body.get("has_more"):
                break
            page += 1
        ts = TagSet(slug, frozenset(names), self._now(), total, query)
        save_tag_set(self._dir, ts)
        return ts

    def ensure(self, refresh: bool = False) -> TagCache:
        cache = TagCache() if refresh else load_tag_cache(self._dir)
        for slug in cache.missing():
            cache.sets[slug] = self.fetch(slug)
        return cache
