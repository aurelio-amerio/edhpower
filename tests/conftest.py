"""Shared test helpers: Scryfall-shaped card factories and a fake HTTP send."""

from __future__ import annotations

import json
from typing import Any

import pytest

from edhpower.tags import TAG_TABLE, TagCache, TagSet


def full_tag_cache(**members) -> TagCache:
    """members: slug -> iterable of names; every other verified slug is present but empty."""
    sets = {slug: TagSet(slug, frozenset(members.get(slug, ())), "2026-09-05T00:00:00Z", 0, f"otag:{slug} legal:commander") for slug in TAG_TABLE}
    return TagCache(sets)


def make_card(name: str, **over: Any) -> dict[str, Any]:
    """Return a minimal Scryfall card object; override any field via kwargs."""
    card: dict[str, Any] = {
        "object": "card",
        "name": name,
        "layout": "normal",
        "cmc": 2.0,
        "mana_cost": "{2}",
        "type_line": "Artifact",
        "oracle_text": "",
        "colors": [],
        "color_identity": [],
        "produced_mana": [],
        "keywords": [],
        "edhrec_rank": 1000,
        "prices": {"usd": "1.00", "eur": "0.90"},
        "legalities": {"commander": "legal"},
        "game_changer": False,
        "reserved": False,
        "set": "tst",
        "collector_number": "1",
    }
    card.update(over)
    return card


class FakeSend:
    """Records requests and serves canned responses keyed by (method, url-prefix)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.routes: list[tuple[str, str, Any]] = []  # (method, url_prefix, responder)

    def route(self, method: str, url_prefix: str, responder: Any) -> None:
        """responder: dict/list (returned as 200 JSON) or callable(params, json_body) -> (status, headers, text).

        Inserted at the front of the route list, so later registrations win.
        """
        self.routes.insert(0, (method, url_prefix, responder))

    def __call__(self, method: str, url: str, params: dict | None, json_body: Any, headers: dict) -> tuple[int, dict, str]:
        self.calls.append({"method": method, "url": url, "params": params, "json": json_body, "headers": headers})
        for m, prefix, responder in self.routes:
            if m == method and url.startswith(prefix):
                if callable(responder):
                    return responder(params, json_body)
                return 200, {}, json.dumps(responder)
        return 404, {}, json.dumps({"object": "error", "code": "not_found", "details": "no route"})


@pytest.fixture
def fake_send() -> FakeSend:
    return FakeSend()


from functools import lru_cache
from pathlib import Path

from edhpower.decklist import parse_decklist
from edhpower.facts import DeckFacts, build_facts, load_facts
from edhpower.scryfall import CardData, Resolution

FIXTURES = Path(__file__).parent / "fixtures"


@lru_cache(maxsize=None)
def fixture_facts(name: str) -> DeckFacts:
    """Frozen live fixture, loaded once per session (the simulator makes analyse() non-trivial)."""
    return load_facts(FIXTURES / f"{name}.facts.json")


def sim_facts(decklist: str, cards: list[dict], tags: dict[str, list[str]] | None = None, combos=None,
              scripts: dict[str, str] | None = None) -> DeckFacts:
    """DeckFacts for a hand-written deck: `cards` are make_card() objects, `tags` is slug -> names
    (None means tags unavailable), `combos` a ComboData or None, `scripts` name -> Forge script text."""
    res = Resolution({c["name"]: CardData.from_scryfall(c) for c in cards}, [], 0, "2026-09-10T00:00:00Z")
    cache = full_tag_cache(**tags) if tags is not None else None
    return build_facts(parse_decklist(decklist), res, combos, None if combos else "offline", "sim.txt", tag_cache=cache,
                       forge_scripts=({c["name"]: scripts.get(c["name"]) for c in cards} if scripts is not None else None),
                       forge_commit="0" * 40 if scripts is not None else None)
