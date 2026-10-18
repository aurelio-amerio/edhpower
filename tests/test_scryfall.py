import json
from pathlib import Path

import pytest

from edhpower.http import HttpClient, HttpError
from edhpower.scryfall import COLLECTION_BATCH, CardData, ScryfallClient

from .conftest import make_card


def test_from_scryfall_normal_card():
    obj = make_card("Ancient Tomb", cmc=0.0, mana_cost="", type_line="Land",
                    oracle_text="{T}: Add {C}{C}. Ancient Tomb deals 2 damage to you.",
                    produced_mana=["C"], edhrec_rank=66, game_changer=True,
                    prices={"usd": "45.00", "eur": "74.53"}, set="uma", collector_number="236")
    c = CardData.from_scryfall(obj)
    assert c.name == "Ancient Tomb" and c.cmc == 0.0 and c.is_land and not c.is_basic_land
    assert c.produced_mana == ("C",) and c.game_changer is True
    assert c.price_usd == 45.0 and c.price_eur == 74.53 and c.edhrec_rank == 66
    assert c.lookup_keys() == ["ancient tomb"]


def test_from_scryfall_modal_dfc_joins_faces():
    obj = make_card("Wandering Archaic // Explore the Vastlands", layout="modal_dfc", cmc=5.0,
                    type_line="Creature — Avatar // Sorcery")
    del obj["oracle_text"]
    del obj["mana_cost"]
    obj["card_faces"] = [
        {"name": "Wandering Archaic", "mana_cost": "{5}", "type_line": "Creature — Avatar",
         "oracle_text": "Whenever an opponent casts an instant or sorcery spell...", "power": "4", "toughness": "4"},
        {"name": "Explore the Vastlands", "mana_cost": "{3}", "type_line": "Sorcery",
         "oracle_text": "Each player looks at the top five cards..."},
    ]
    c = CardData.from_scryfall(obj)
    assert c.name == "Wandering Archaic // Explore the Vastlands"
    assert c.mana_cost == "{5}" and c.power == "4"
    assert "Whenever an opponent" in c.oracle_text and "Each player looks" in c.oracle_text
    assert [f.name for f in c.faces] == ["Wandering Archaic", "Explore the Vastlands"]
    assert c.lookup_keys() == ["wandering archaic // explore the vastlands", "wandering archaic", "explore the vastlands"]
    assert not c.is_land


def test_missing_price_and_rank_become_none():
    c = CardData.from_scryfall(make_card("New Card", prices={"usd": None, "eur": None}, edhrec_rank=None))
    assert c.price_usd is None and c.price_eur is None and c.edhrec_rank is None


def test_basic_land_detection():
    assert CardData.from_scryfall(make_card("Wastes", type_line="Basic Land", cmc=0.0)).is_basic_land
    assert CardData.from_scryfall(make_card("Forest", type_line="Basic Land — Forest", cmc=0.0)).is_basic_land


def test_dict_round_trip():
    c = CardData.from_scryfall(make_card("Sol Ring", keywords=["Flash"], color_identity=["U"]))
    assert CardData.from_dict(c.to_dict()) == c


def _collection_responder(known: dict[str, dict]):
    def responder(params, body):
        found, missing = [], []
        for ident in body["identifiers"]:
            key = ident["name"].lower()
            hit = next((c for k, c in known.items() if k == key), None)
            (found if hit else missing).append(hit or ident)
        return 200, {}, json.dumps({"object": "list", "data": found, "not_found": missing})
    return responder


def _client(tmp_path: Path, fake_send) -> ScryfallClient:
    http = HttpClient("edhpower/test", send=fake_send, sleep=lambda s: None)
    return ScryfallClient(http, tmp_path / "cards.jsonl", now=lambda: "2026-09-10T12:00:00Z")


def test_resolves_via_collection_and_writes_cache(tmp_path, fake_send):
    known = {"sol ring": make_card("Sol Ring"), "ancient tomb": make_card("Ancient Tomb", type_line="Land")}
    fake_send.route("POST", "https://api.scryfall.com/cards/collection", _collection_responder(known))
    client = _client(tmp_path, fake_send)
    res = client.resolve(["Sol Ring", "ancient tomb"])
    assert set(res.cards) == {"Sol Ring", "ancient tomb"}
    assert res.cards["ancient tomb"].name == "Ancient Tomb"
    assert res.unresolved == [] and res.network_requests == 1
    assert res.cache_updated_at == "2026-09-10T12:00:00Z"
    lines = (tmp_path / "cards.jsonl").read_text().splitlines()
    assert len(lines) == 2


def test_cache_hit_makes_no_requests(tmp_path, fake_send):
    (tmp_path / "cards.jsonl").write_text(json.dumps(make_card("Sol Ring")) + "\n")
    (tmp_path / "cards.meta.json").write_text(json.dumps({"updated_at": "2026-09-01T00:00:00Z"}))
    client = _client(tmp_path, fake_send)
    res = client.resolve(["sol ring"])
    assert res.cards["sol ring"].name == "Sol Ring"
    assert res.network_requests == 0 and fake_send.calls == []
    assert res.cache_updated_at == "2026-09-01T00:00:00Z"


def test_batches_of_75(tmp_path, fake_send):
    names = [f"Card {i}" for i in range(160)]
    known = {n.lower(): make_card(n) for n in names}
    fake_send.route("POST", "https://api.scryfall.com/cards/collection", _collection_responder(known))
    res = _client(tmp_path, fake_send).resolve(names)
    sizes = [len(c["json"]["identifiers"]) for c in fake_send.calls]
    assert sizes == [COLLECTION_BATCH, COLLECTION_BATCH, 10]
    assert len(res.cards) == 160


def test_dfc_input_sends_front_face_and_indexes_full_name(tmp_path, fake_send):
    dfc = make_card("Wandering Archaic // Explore the Vastlands", layout="modal_dfc")
    dfc["card_faces"] = [{"name": "Wandering Archaic", "mana_cost": "{5}", "type_line": "Creature", "oracle_text": ""},
                         {"name": "Explore the Vastlands", "mana_cost": "{3}", "type_line": "Sorcery", "oracle_text": ""}]
    del dfc["oracle_text"]
    fake_send.route("POST", "https://api.scryfall.com/cards/collection", _collection_responder({"wandering archaic": dfc}))
    client = _client(tmp_path, fake_send)
    res = client.resolve(["Wandering Archaic // Explore the Vastlands"])
    assert fake_send.calls[0]["json"]["identifiers"] == [{"name": "Wandering Archaic"}]
    assert res.cards["Wandering Archaic // Explore the Vastlands"].name == "Wandering Archaic // Explore the Vastlands"
    # second resolve by either face name is a cache hit
    res2 = client.resolve(["explore the vastlands"])
    assert res2.network_requests == 0 and res2.cards["explore the vastlands"].name.startswith("Wandering")


def test_not_found_falls_back_to_named_then_unresolved(tmp_path, fake_send):
    fake_send.route("POST", "https://api.scryfall.com/cards/collection", _collection_responder({}))
    fake_send.route("GET", "https://api.scryfall.com/cards/named", lambda p, b: (
        (200, {}, json.dumps(make_card("Sol Ring"))) if p["exact"] == "Sol Ring"
        else (404, {}, json.dumps({"object": "error", "code": "not_found"}))))
    res = _client(tmp_path, fake_send).resolve(["Sol Ring", "Definitely Fake"])
    assert res.cards["Sol Ring"].name == "Sol Ring"
    assert res.unresolved == ["Definitely Fake"]
    gets = [c for c in fake_send.calls if c["method"] == "GET"]
    assert [c["params"]["exact"] for c in gets] == ["Sol Ring", "Definitely Fake"]


def test_corrupt_cache_line_is_skipped(tmp_path, fake_send):
    lines = [
        json.dumps(make_card("Sol Ring")),
        '{"object": "card", "name": "Bro',
    ]
    (tmp_path / "cards.jsonl").write_text("\n".join(lines) + "\n")
    client = _client(tmp_path, fake_send)
    res = client.resolve(["sol ring"])
    assert res.network_requests == 0
    assert res.cards["sol ring"].name == "Sol Ring"


def test_full_name_wins_over_face_alias(tmp_path, fake_send):
    split = make_card("Fire // Ice", layout="split")
    split["card_faces"] = [
        {"name": "Fire", "mana_cost": "{1}{R}", "type_line": "Instant", "oracle_text": ""},
        {"name": "Ice", "mana_cost": "{1}{U}", "type_line": "Instant", "oracle_text": ""},
    ]
    del split["oracle_text"]
    del split["mana_cost"]
    lines = [
        json.dumps(make_card("Fire")),
        json.dumps(split),
    ]
    (tmp_path / "cards.jsonl").write_text("\n".join(lines) + "\n")
    client = _client(tmp_path, fake_send)
    res_fire = client.resolve(["Fire"])
    res_ice = client.resolve(["Ice"])
    assert res_fire.cards["Fire"].name == "Fire"
    assert res_ice.cards["Ice"].name == "Fire // Ice"
    assert res_fire.network_requests == 0 and res_ice.network_requests == 0


def test_scryfall_4xx_raises_http_error(tmp_path, fake_send):
    fake_send.route(
        "POST",
        "https://api.scryfall.com/cards/collection",
        lambda p, b: (429, {"Retry-After": "1"}, json.dumps({"code": "rate_limited"})),
    )
    http = HttpClient("edhpower/test", send=fake_send, sleep=lambda s: None)
    client = ScryfallClient(http, tmp_path / "cards.jsonl")
    with pytest.raises(HttpError):
        client.resolve(["Sol Ring"])


def test_diacritic_insensitive_cache_hit(tmp_path, fake_send):
    (tmp_path / "cards.jsonl").write_text(json.dumps(make_card("Lim-Dûl's Vault")) + "\n")
    client = _client(tmp_path, fake_send)
    res = client.resolve(["Lim-Dul's Vault"])
    assert res.network_requests == 0
    assert res.cards["Lim-Dul's Vault"].name == "Lim-Dûl's Vault"


def test_cache_lines_carry_per_card_fetch_stamp(tmp_path, fake_send):
    fake_send.route("POST", "https://api.scryfall.com/cards/collection", _collection_responder({"sol ring": make_card("Sol Ring")}))
    client = _client(tmp_path, fake_send)
    res = client.resolve(["Sol Ring"])
    line = json.loads((tmp_path / "cards.jsonl").read_text().splitlines()[0])
    assert line["_edhpower_fetched_at"] == "2026-09-10T12:00:00Z"
    assert res.cards["Sol Ring"].fetched_at == "2026-09-10T12:00:00Z"
    assert res.fetched_oldest == "2026-09-10T12:00:00Z" and res.fetched_newest == "2026-09-10T12:00:00Z"
    assert res.fetched_unknown == 0


def test_legacy_cache_lines_without_stamp_are_counted_unknown(tmp_path, fake_send):
    (tmp_path / "cards.jsonl").write_text(json.dumps(make_card("Sol Ring")) + "\n", encoding="utf-8")
    res = _client(tmp_path, fake_send).resolve(["Sol Ring"])
    assert res.cards["Sol Ring"].fetched_at is None
    assert res.fetched_unknown == 1 and res.fetched_oldest is None and res.fetched_newest is None


def test_fetch_range_spans_cards_from_different_runs(tmp_path, fake_send):
    fake_send.route("POST", "https://api.scryfall.com/cards/collection", _collection_responder({"sol ring": make_card("Sol Ring")}))
    http = HttpClient("edhpower/test", send=fake_send, sleep=lambda s: None)
    ScryfallClient(http, tmp_path / "cards.jsonl", now=lambda: "2026-09-01T00:00:00Z").resolve(["Sol Ring"])
    fake_send.route("POST", "https://api.scryfall.com/cards/collection", _collection_responder({"mana vault": make_card("Mana Vault")}))
    res = ScryfallClient(http, tmp_path / "cards.jsonl", now=lambda: "2026-09-10T00:00:00Z").resolve(["Sol Ring", "Mana Vault"])
    assert res.fetched_oldest == "2026-09-01T00:00:00Z" and res.fetched_newest == "2026-09-10T00:00:00Z"


def test_card_dict_round_trip_keeps_fetched_at():
    c = CardData.from_scryfall({**make_card("Sol Ring"), "_edhpower_fetched_at": "2026-09-10T00:00:00Z"})
    assert c.fetched_at == "2026-09-10T00:00:00Z" and CardData.from_dict(c.to_dict()) == c
    legacy = c.to_dict()
    del legacy["fetched_at"]
    assert CardData.from_dict(legacy).fetched_at is None
