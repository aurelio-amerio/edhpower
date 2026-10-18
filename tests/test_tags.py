import json
from pathlib import Path

import pytest

from edhpower.http import HttpClient, HttpError
from edhpower.tags import TAG_TABLE, TagCache, TagConfigError, TagFetcher, TagSet, load_tag_cache, save_tag_set

SEARCH = "https://api.scryfall.com/cards/search"


def _paged(pages: dict[str, list[list[str]]]):
    """pages: slug -> list of pages, each a list of card names."""
    def responder(params, body):
        slug = params["q"].split()[0].removeprefix("otag:")
        if slug not in pages:
            return 404, {}, json.dumps({"object": "error", "code": "not_found", "details": "Your query didn’t match any cards."})
        page = int(params.get("page", 1))
        chunks = pages[slug]
        data = [{"object": "card", "name": n} for n in chunks[page - 1]]
        total = sum(len(c) for c in chunks)
        return 200, {}, json.dumps({"object": "list", "total_cards": total, "has_more": page < len(chunks), "data": data})
    return responder


def _fetcher(tmp_path, fake_send, progress=None) -> TagFetcher:
    http = HttpClient("edhpower/test", send=fake_send, sleep=lambda s: None)
    return TagFetcher(http, tmp_path / "tags", now=lambda: "2026-09-10T12:00:00Z", progress=progress)


def test_tag_table_matches_spec():
    assert len(TAG_TABLE) == 21
    assert {"ramp", "mana-rock", "mana-dork", "land-ramp", "ritual", "cost-reducer", "tutor", "removal", "counterspell",
            "board-wipe", "card-advantage", "cantrip", "extra-turn", "mass-land-denial", "pitch-spell", "tax", "hatebear",
            "reanimate", "cheat-into-play", "extra-combat", "copy-spell"} == set(TAG_TABLE)
    assert TAG_TABLE["ramp"] == 2125 and TAG_TABLE["removal"] == 6146


def test_fetch_pages_until_has_more_is_false_and_writes_file(tmp_path, fake_send):
    fake_send.route("GET", SEARCH, _paged({"ramp": [["Sol Ring", "Arcane Signet"], ["Ancient Tomb"]]}))
    messages = []
    ts = _fetcher(tmp_path, fake_send, progress=messages.append).fetch("ramp")
    assert ts.names == frozenset({"Sol Ring", "Arcane Signet", "Ancient Tomb"})
    assert ts.total_cards == 3 and ts.fetched_at == "2026-09-10T12:00:00Z" and ts.query == "otag:ramp legal:commander"
    calls = [c for c in fake_send.calls if c["url"].startswith(SEARCH)]
    assert [c["params"]["page"] for c in calls] == [1, 2]
    assert all(c["params"]["unique"] == "cards" and c["params"]["q"] == "otag:ramp legal:commander" for c in calls)
    saved = json.loads((tmp_path / "tags" / "ramp.json").read_text())
    assert saved["names"] == ["Ancient Tomb", "Arcane Signet", "Sol Ring"] and saved["version"] == 1
    assert messages and "ramp" in messages[0]


def test_unknown_slug_is_a_configuration_error(tmp_path, fake_send):
    fake_send.route("GET", SEARCH, _paged({}))
    with pytest.raises(TagConfigError, match="otag:ramp"):
        _fetcher(tmp_path, fake_send).fetch("ramp")
    with pytest.raises(TagConfigError, match="not in the verified tag table"):
        _fetcher(tmp_path, fake_send).fetch("free-spell")


def test_server_error_is_http_error_not_empty_set(tmp_path, fake_send):
    fake_send.route("GET", SEARCH, lambda p, b: (500, {}, "boom"))
    with pytest.raises(HttpError):
        _fetcher(tmp_path, fake_send).fetch("ramp")
    assert not (tmp_path / "tags" / "ramp.json").exists()


def test_tag_requests_are_paced_at_one_per_second(tmp_path, fake_send):
    fake_send.route("GET", SEARCH, _paged({"ramp": [["A"], ["B"]]}))
    sleeps = []
    clock = iter([0.0, 0.0, 0.1, 0.1, 0.2, 0.2])
    http = HttpClient("edhpower/test", send=fake_send, sleep=sleeps.append, clock=lambda: next(clock))
    TagFetcher(http, tmp_path / "tags", now=lambda: "x").fetch("ramp")
    assert sleeps and all(s >= 0.8 for s in sleeps)


def test_ensure_fetches_only_missing_slugs_and_refresh_refetches(tmp_path, fake_send):
    pages = {slug: [[f"{slug} card"]] for slug in TAG_TABLE}
    fake_send.route("GET", SEARCH, _paged(pages))
    save_tag_set(tmp_path / "tags", TagSet("ramp", frozenset({"Old Card"}), "2026-01-01T00:00:00Z", 1, "otag:ramp legal:commander"))
    cache = _fetcher(tmp_path, fake_send).ensure()
    assert cache.complete and cache.sets["ramp"].names == frozenset({"Old Card"})
    assert len([c for c in fake_send.calls if c["url"].startswith(SEARCH)]) == len(TAG_TABLE) - 1
    cache = _fetcher(tmp_path, fake_send).ensure(refresh=True)
    assert cache.sets["ramp"].names == frozenset({"ramp card"})


def test_load_skips_corrupt_or_foreign_files_and_reports_missing(tmp_path):
    d = tmp_path / "tags"
    d.mkdir()
    (d / "ramp.json").write_text("{not json")
    (d / "tutor.json").write_text(json.dumps({"version": 99, "slug": "tutor", "names": [], "fetched_at": "x", "total_cards": 0}))
    save_tag_set(d, TagSet("cantrip", frozenset({"Brainstorm"}), "2026-09-01T00:00:00Z", 1, "q"))
    save_tag_set(d, TagSet("card-advantage", frozenset({"Brainstorm", "Rhystic Study"}), "2026-09-05T00:00:00Z", 2, "q"))
    cache = load_tag_cache(d)
    assert set(cache.sets) == {"cantrip", "card-advantage"} and not cache.complete
    assert "ramp" in cache.missing() and "tutor" in cache.missing()
    assert cache.tags_for("Brainstorm") == ("cantrip", "card-advantage") and cache.tags_for("Sol Ring") == ()
    assert cache.fetched_range() == ("2026-09-01T00:00:00Z", "2026-09-05T00:00:00Z")
    assert TagCache({}).fetched_range() == (None, None)
