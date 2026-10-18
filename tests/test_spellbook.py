import copy
import json

import pytest

from edhpower.http import HttpClient
from edhpower.spellbook import ComboData, SpellbookClient, SpellbookError

FMC = {
    "count": None, "next": None, "previous": None,
    "results": {
        "identity": "WUBRG",
        "included": [
            {"id": "4131-4547", "status": "OK", "bracketTag": "R", "manaNeeded": "", "manaValueNeeded": 0,
             "popularity": 1200, "description": "...", "notablePrerequisites": "",
             "uses": [{"card": {"name": "Basalt Monolith"}, "zoneLocations": ["B"], "mustBeCommander": False},
                      {"card": {"name": "Forsaken Monument"}, "zoneLocations": ["B"], "mustBeCommander": False}],
             "requires": [], "produces": [{"feature": {"name": "Infinite colorless mana"}}]},
            {"id": "5637-5642-5657--34", "status": "OK", "bracketTag": "E",
             "manaNeeded": "{C}{C} plus enough mana to pay for the Eldrazi spell", "manaValueNeeded": 2,
             "popularity": 3, "description": "...", "notablePrerequisites": "",
             "uses": [{"card": {"name": "Ulalek, Fused Atrocity"}, "zoneLocations": ["B"], "mustBeCommander": True},
                      {"card": {"name": "Echoes of Eternity"}, "zoneLocations": ["B"], "mustBeCommander": False},
                      {"card": {"name": "Kozilek's Unsealing"}, "zoneLocations": ["B"], "mustBeCommander": False}],
             "requires": [{"template": {"name": "Eldrazi Creature Card with MV=4, 5 or 6"}, "zoneLocations": ["H"]}],
             "produces": [{"feature": {"name": "Infinite colorless mana"}}, {"feature": {"name": "Infinite creature tokens"}}]},
        ],
        "almostIncluded": [{"id": "x"}, {"id": "y"}],
    },
}

EB = {
    "bracketTag": "R",
    "cards": [
        {"card": {"name": "Ancient Tomb"}, "quantity": 1, "banned": False, "gameChanger": True, "massLandDenial": False, "extraTurn": False},
        {"card": {"name": "Basalt Monolith"}, "quantity": 1, "banned": False, "gameChanger": False, "massLandDenial": False, "extraTurn": False},
        {"card": {"name": "Forsaken Monument"}, "quantity": 1, "banned": False, "gameChanger": False, "massLandDenial": False, "extraTurn": False},
        {"card": {"name": "Ulalek, Fused Atrocity"}, "quantity": 1, "banned": False, "gameChanger": False, "massLandDenial": False, "extraTurn": False},
    ],
    "templates": [],
    "combos": [
        {"combo": {"id": "4131-4547"}, "relevant": True, "borderlineRelevant": False, "arguablyTwoCard": False,
         "definitelyTwoCard": True, "speed": 5, "massLandDenial": False, "extraTurn": False, "lock": False,
         "skipTurns": False, "controlAllOpponents": False, "controlSomeOpponents": False},
    ],
}


def _client(fake_send) -> SpellbookClient:
    fake_send.route("POST", "https://backend.commanderspellbook.com/find-my-combos", FMC)
    fake_send.route("POST", "https://backend.commanderspellbook.com/estimate-bracket", EB)
    return SpellbookClient(HttpClient("edhpower/test", send=fake_send), now=lambda: "2026-09-10T12:00:00Z")


def test_request_body_shape(fake_send):
    _client(fake_send).fetch(["Ulalek, Fused Atrocity"], [("Ancient Tomb", 1), ("Basalt Monolith", 1)])
    body = fake_send.calls[0]["json"]
    assert body == {"commanders": [{"card": "Ulalek, Fused Atrocity", "quantity": 1}],
                    "main": [{"card": "Ancient Tomb", "quantity": 1}, {"card": "Basalt Monolith", "quantity": 1}]}
    assert fake_send.calls[1]["json"] == body


def test_parses_included_lines(fake_send):
    data = _client(fake_send).fetch(["Ulalek, Fused Atrocity"], [("Ancient Tomb", 1), ("Basalt Monolith", 1), ("Forsaken Monument", 1)])
    assert data.identity == "WUBRG" and len(data.included) == 2 and data.almost_included_count == 2
    basalt = data.included[0]
    assert [p.name for p in basalt.pieces] == ["Basalt Monolith", "Forsaken Monument"]
    assert basalt.pieces[0].zones == ("B",) and basalt.templates == () and basalt.bracket_tag == "R"
    assert basalt.produces == ("Infinite colorless mana",)
    ula = data.included[1]
    assert ula.pieces[0].must_be_commander is True
    assert ula.templates[0].name.startswith("Eldrazi Creature Card") and ula.templates[0].zones == ("H",)
    assert ula.mana_value_needed == 2


def test_parses_flags(fake_send):
    data = _client(fake_send).fetch(["Ulalek, Fused Atrocity"], [("Ancient Tomb", 1), ("Basalt Monolith", 1), ("Forsaken Monument", 1)])
    assert data.card_flags["Ancient Tomb"].game_changer is True
    assert data.combo_flags["4131-4547"].definitely_two_card is True
    assert data.combo_flags["4131-4547"].speed == 5
    assert data.spellbook_bracket_tag == "R"
    assert data.fetched_at == "2026-09-10T12:00:00Z"


def test_endpoint_failure_raises(fake_send):
    fake_send.route("POST", "https://backend.commanderspellbook.com/find-my-combos", lambda p, b: (400, {}, json.dumps({"main": ["Expected a dictionary"]})))
    client = SpellbookClient(HttpClient("ua", send=fake_send))
    with pytest.raises(SpellbookError):
        client.fetch([], [("Sol Ring", 1)])


def test_persistent_5xx_raises_spellbook_error(fake_send):
    fake_send.route("POST", "https://backend.commanderspellbook.com/find-my-combos", lambda p, b: (503, {}, "down"))
    client = SpellbookClient(HttpClient("ua", send=fake_send, sleep=lambda s: None))
    with pytest.raises(SpellbookError):
        client.fetch([], [("Sol Ring", 1)])


def test_malformed_response_raises_spellbook_error(fake_send):
    malformed_fmc = copy.deepcopy(FMC)
    malformed_fmc["results"]["included"][0]["uses"][0] = {"zoneLocations": ["B"]}  # missing "card" key
    fake_send.route("POST", "https://backend.commanderspellbook.com/find-my-combos", malformed_fmc)
    fake_send.route("POST", "https://backend.commanderspellbook.com/estimate-bracket", EB)
    client = SpellbookClient(HttpClient("ua", send=fake_send))
    with pytest.raises(SpellbookError):
        client.fetch(["Ulalek, Fused Atrocity"], [("Ancient Tomb", 1)])


def test_round_trip(fake_send):
    data = _client(fake_send).fetch(["Ulalek, Fused Atrocity"], [("Ancient Tomb", 1)])
    assert ComboData.from_dict(data.to_dict()) == data


def test_combo_data_stamps_client_schema_version(fake_send):
    from edhpower.spellbook import CLIENT_SCHEMA_VERSION
    fake_send.route("POST", "https://backend.commanderspellbook.com/find-my-combos", FMC)
    fake_send.route("POST", "https://backend.commanderspellbook.com/estimate-bracket", EB)
    http = HttpClient("edhpower/test", send=fake_send, sleep=lambda s: None)
    data = SpellbookClient(http, now=lambda: "2026-09-10T00:00:00Z").fetch(["Ulalek, Fused Atrocity"], [("Basalt Monolith", 1)])
    assert data.api_version == CLIENT_SCHEMA_VERSION == "6.4.0"
    assert ComboData.from_dict(data.to_dict()) == data
    legacy = data.to_dict()
    del legacy["api_version"]
    assert ComboData.from_dict(legacy).api_version == ""
