import io
import json
from pathlib import Path

import pytest

from edhpower.cli import main
from edhpower.tags import TAG_TABLE

from .conftest import make_card
from .test_scryfall import _collection_responder
from .test_spellbook import EB, FMC

DECK = "1 Ulalek, Fused Atrocity\n\n1 Ancient Tomb\n1 Basalt Monolith\n1 Forsaken Monument\n"

SEARCH = "https://api.scryfall.com/cards/search"


@pytest.fixture(autouse=True)
def _fast_sim(monkeypatch):
    import edhpower.analysis as analysis_mod
    real = analysis_mod.analyse
    monkeypatch.setattr("edhpower.cli.analyse", lambda facts, **kw: real(facts, **{**kw, "iterations": kw.get("iterations") or 10}))


def _wire_tags(fake_send, members: dict[str, list[str]] | None = None):
    members = members or {}

    def responder(params, body):
        slug = params["q"].split()[0].removeprefix("otag:")
        if slug not in TAG_TABLE:
            return 404, {}, json.dumps({"object": "error", "code": "not_found"})
        data = [{"object": "card", "name": n} for n in members.get(slug, [])]
        return 200, {}, json.dumps({"object": "list", "total_cards": len(data), "has_more": False, "data": data})

    fake_send.route("GET", SEARCH, responder)


def _card_overrides(name: str) -> dict:
    over: dict = {"game_changer": name == "Ancient Tomb"}
    if name == "Basalt Monolith":
        # Real Basalt Monolith costs {3}; the make_card() default cmc=2.0 would (with its "rock"
        # special-behaviour mana=3) misclassify it as fast mana instead of a mana rock.
        over["cmc"] = 3.0
        over["mana_cost"] = "{3}"
    return over


def _wire(fake_send, known_names):
    known = {n.lower(): make_card(n, **_card_overrides(n)) for n in known_names}
    fake_send.route("POST", "https://api.scryfall.com/cards/collection", _collection_responder(known))
    fake_send.route("GET", "https://api.scryfall.com/cards/named", lambda p, b: (404, {}, json.dumps({"code": "not_found"})))
    fake_send.route("POST", "https://backend.commanderspellbook.com/find-my-combos", FMC)
    fake_send.route("POST", "https://backend.commanderspellbook.com/estimate-bracket", EB)
    _wire_tags(fake_send)


def test_happy_path_writes_json_and_report(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ulalek, Fused Atrocity", "Ancient Tomb", "Basalt Monolith", "Forsaken Monument"])
    _wire_tags(fake_send)
    deck = tmp_path / "d.txt"
    deck.write_text(DECK)
    out = io.StringIO()
    code = main(
        [str(deck), "--json", str(tmp_path / "out" / "o.json"), "--cache-dir", str(tmp_path / "cache")],
        send=fake_send,
        stdout=out,
        stderr=io.StringIO(),
        sleep=lambda s: None,
    )
    assert code == 0
    text = out.getvalue()
    assert "minimum bracket: 3" in text and "Basalt Monolith + Forsaken Monument" in text
    data = json.loads((tmp_path / "out" / "o.json").read_text())
    assert data["bracket"]["minimum_bracket"] == 3
    assert len(data["facts"]["entries"]) == 4 and data["facts"]["commanders"] == ["Ulalek, Fused Atrocity"]
    assert data["tool"]["name"] == "edhpower"
    assert (tmp_path / "cache" / "cards.jsonl").exists()


def test_spellbook_names_are_canonical(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ulalek, Fused Atrocity", "Ancient Tomb", "Basalt Monolith", "Forsaken Monument"])
    deck = tmp_path / "d.txt"
    deck.write_text("1 ulalek, fused atrocity\n\n1 ancient tomb\n")
    assert main([str(deck), "--cache-dir", str(tmp_path)], send=fake_send, stdout=io.StringIO(), sleep=lambda s: None) == 0
    sb = next(c for c in fake_send.calls if "find-my-combos" in c["url"])
    assert sb["json"]["commanders"] == [{"card": "Ulalek, Fused Atrocity", "quantity": 1}]
    assert sb["json"]["main"] == [{"card": "Ancient Tomb", "quantity": 1}]


def test_unresolved_exits_2_unless_allowed(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ancient Tomb"])
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ancient Tomb\n\n1 Fake Card\n")
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path)], send=fake_send, stdout=out, sleep=lambda s: None) == 2
    assert "Fake Card" in out.getvalue()
    out2 = io.StringIO()
    code = main(
        [str(deck), "--cache-dir", str(tmp_path), "--allow-unresolved", "--json", str(tmp_path / "o.json")],
        send=fake_send,
        stdout=out2,
        sleep=lambda s: None,
    )
    assert code == 0
    assert json.loads((tmp_path / "o.json").read_text())["facts"]["unresolved"] == ["Fake Card"]


def test_parse_error_exits_1(tmp_path: Path, fake_send):
    deck = tmp_path / "d.txt"
    deck.write_text("1 Sol Ring\ngarbage line\n")
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path)], send=fake_send, stdout=out, sleep=lambda s: None) == 1
    assert "garbage line" in out.getvalue()


def test_missing_file_exits_1(tmp_path: Path, fake_send):
    assert main([str(tmp_path / "nope.txt")], send=fake_send, stdout=io.StringIO(), sleep=lambda s: None) == 1


def test_spellbook_failure_degrades(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ancient Tomb"])
    fake_send.route("POST", "https://backend.commanderspellbook.com/find-my-combos", lambda p, b: (503, {}, "down"))
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ancient Tomb\n")
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path), "--commander", "Ancient Tomb"], send=fake_send, stdout=out, sleep=lambda s: None) == 0
    assert "Combos: unavailable" in out.getvalue() and "unevaluated" in out.getvalue()


def test_from_facts_makes_no_requests(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ancient Tomb"])
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ancient Tomb\n")
    facts_path = tmp_path / "f.json"
    assert (
        main(
            [str(deck), "--cache-dir", str(tmp_path), "--commander", "Ancient Tomb", "--facts-json", str(facts_path)],
            send=fake_send,
            stdout=io.StringIO(),
            sleep=lambda s: None,
        )
        == 0
    )
    n = len(fake_send.calls)
    assert main(["--from-facts", str(facts_path)], send=fake_send, stdout=io.StringIO(), sleep=lambda s: None) == 0
    assert len(fake_send.calls) == n


def test_commander_flag_and_no_combos(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ancient Tomb", "Ulalek, Fused Atrocity"])
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ancient Tomb\n1 Ulalek, Fused Atrocity\n")
    out = io.StringIO()
    code = main(
        [str(deck), "--cache-dir", str(tmp_path), "--commander", "Ulalek, Fused Atrocity", "--no-combos"],
        send=fake_send,
        stdout=out,
        sleep=lambda s: None,
    )
    assert code == 0 and "Commander(s): Ulalek, Fused Atrocity" in out.getvalue()
    assert not any("commanderspellbook" in c["url"] for c in fake_send.calls)


def test_no_commander_exits_1(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ancient Tomb", "Sol Ring"])
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ancient Tomb\n1 Sol Ring\n")
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path)], send=fake_send, stdout=out, sleep=lambda s: None) == 1
    assert "--commander" in out.getvalue()


def test_scryfall_failure_exits_3(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ancient Tomb", "Sol Ring"])
    fake_send.route("POST", "https://api.scryfall.com/cards/collection", lambda p, b: (503, {}, "down"))
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ancient Tomb\n\n1 Sol Ring\n")
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path)], send=fake_send, stdout=out, sleep=lambda s: None) == 3
    assert "Scryfall" in out.getvalue()


def test_malformed_json_decklist_exits_1(tmp_path: Path, fake_send):
    deck = tmp_path / "d.json"
    deck.write_text("{not json")
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path)], send=fake_send, stdout=out, sleep=lambda s: None) == 1
    assert "cannot parse" in out.getvalue()


def test_from_facts_missing_file_exits_1(tmp_path: Path, fake_send):
    out = io.StringIO()
    assert main(["--from-facts", str(tmp_path / "nope.json")], send=fake_send, stdout=out, sleep=lambda s: None) == 1
    assert "cannot load facts" in out.getvalue()


def test_json_decklist_not_an_object_exits_1(tmp_path: Path, fake_send):
    deck = tmp_path / "d.json"
    deck.write_text("[1, 2]")
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path)], send=fake_send, stdout=out, sleep=lambda s: None) == 1
    assert "cannot parse" in out.getvalue()


def test_unresolved_commander_exits_2_even_if_allowed(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ancient Tomb"])
    deck = tmp_path / "d.txt"
    deck.write_text("1 Fake Commander\n\n1 Ancient Tomb\n")
    out = io.StringIO()
    code = main([str(deck), "--cache-dir", str(tmp_path), "--allow-unresolved"], send=fake_send, stdout=out, sleep=lambda s: None)
    assert code == 2
    assert "commander" in out.getvalue()


def test_tags_are_built_once_and_reported(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ulalek, Fused Atrocity", "Ancient Tomb", "Basalt Monolith", "Forsaken Monument"])
    _wire_tags(fake_send, {"ramp": ["Ancient Tomb", "Basalt Monolith"], "mana-rock": ["Basalt Monolith"]})
    deck = tmp_path / "d.txt"
    deck.write_text(DECK)
    out, err = io.StringIO(), io.StringIO()
    code = main([str(deck), "--cache-dir", str(tmp_path / "cache"), "--json", str(tmp_path / "o.json")], send=fake_send, stdout=out, stderr=err, sleep=lambda s: None)
    assert code == 0
    assert len([c for c in fake_send.calls if c["url"].startswith(SEARCH)]) == len(TAG_TABLE)
    assert "tags:" in err.getvalue() and (tmp_path / "cache" / "tags" / "ramp.json").exists()
    text = out.getvalue()
    assert "Functional profile (tags: ok)" in text and "Component model (v1)" in text and "Tipping point" in text
    data = json.loads((tmp_path / "o.json").read_text())
    assert set(data) == {"tool", "config", "facts", "payoffs", "bracket", "scores", "tipping", "sim", "narrative", "freshness"}
    assert data["facts"]["tags_status"] == "ok" and data["facts"]["partition"]["mana_rocks"] == ["Basalt Monolith"]
    assert data["tool"]["version"] == "0.3.0" and data["config"]["config_version"] == 1
    # second run: cache hit, no search requests
    fake_send.calls.clear()
    assert main([str(deck), "--cache-dir", str(tmp_path / "cache")], send=fake_send, stdout=io.StringIO(), stderr=io.StringIO(), sleep=lambda s: None) == 0
    assert not [c for c in fake_send.calls if c["url"].startswith(SEARCH)]
    # --refresh-tags refetches every slug
    assert main([str(deck), "--cache-dir", str(tmp_path / "cache"), "--refresh-tags"], send=fake_send, stdout=io.StringIO(), stderr=io.StringIO(), sleep=lambda s: None) == 0
    assert len([c for c in fake_send.calls if c["url"].startswith(SEARCH)]) == len(TAG_TABLE)


def test_no_tags_skips_the_build_and_marks_dependents(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ulalek, Fused Atrocity", "Ancient Tomb"])
    _wire_tags(fake_send)
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ulalek, Fused Atrocity\n\n1 Ancient Tomb\n")
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path), "--no-tags"], send=fake_send, stdout=out, sleep=lambda s: None) == 0
    assert not [c for c in fake_send.calls if c["url"].startswith(SEARCH)]
    assert "tags: skipped (--no-tags)" in out.getvalue() and "Component model (v1): unevaluated" in out.getvalue()


def test_tag_network_failure_degrades_but_config_error_aborts(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ulalek, Fused Atrocity", "Ancient Tomb"])
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ulalek, Fused Atrocity\n\n1 Ancient Tomb\n")
    fake_send.route("GET", SEARCH, lambda p, b: (500, {}, "down"))
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path)], send=fake_send, stdout=out, stderr=io.StringIO(), sleep=lambda s: None) == 0
    assert "tags: unavailable" in out.getvalue() and "unevaluated" in out.getvalue()
    fake_send.route("GET", SEARCH, lambda p, b: (404, {}, json.dumps({"object": "error", "code": "not_found"})))
    out = io.StringIO()
    assert main([str(deck), "--cache-dir", str(tmp_path)], send=fake_send, stdout=out, stderr=io.StringIO(), sleep=lambda s: None) == 3
    assert "tag configuration error" in out.getvalue()


def test_from_facts_with_old_schema_exits_1(tmp_path: Path):
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"schema_version": 1}))
    out = io.StringIO()
    assert main(["--from-facts", str(p)], stdout=out, sleep=lambda s: None) == 1
    assert "schema 1" in out.getvalue()


def test_iterations_and_no_sim_flags(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ulalek, Fused Atrocity", "Ancient Tomb", "Basalt Monolith", "Forsaken Monument"])
    deck = tmp_path / "d.txt"
    deck.write_text(DECK)
    out = io.StringIO()
    code = main([str(deck), "--cache-dir", str(tmp_path / "c"), "--iterations", "15", "--json", str(tmp_path / "o.json")], send=fake_send, stdout=out, stderr=io.StringIO(), sleep=lambda s: None)
    assert code == 0 and "Goldfish simulation (sim v4, 15 games" in out.getvalue()
    assert json.loads((tmp_path / "o.json").read_text())["sim"]["iterations"] == 15
    out = io.StringIO()
    code = main([str(deck), "--cache-dir", str(tmp_path / "c"), "--no-sim"], send=fake_send, stdout=out, stderr=io.StringIO(), sleep=lambda s: None)
    assert code == 0 and "Goldfish simulation: skipped (--no-sim)" in out.getvalue()


def test_iterations_must_be_positive(tmp_path: Path, fake_send):
    out = io.StringIO()
    assert main(["--from-facts", "x.json", "--iterations", "0"], send=fake_send, stdout=out, sleep=lambda s: None) == 1
    assert "--iterations must be at least 1" in out.getvalue()


def test_no_forge_flag_sets_status(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ulalek, Fused Atrocity", "Ancient Tomb", "Basalt Monolith", "Forsaken Monument"])
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ulalek, Fused Atrocity\n\n1 Ancient Tomb\n")
    facts_path = tmp_path / "facts.json"
    code = main([str(deck), "--no-forge", "--facts-json", str(facts_path), "--cache-dir", str(tmp_path)], send=fake_send,
                stdout=io.StringIO(), stderr=io.StringIO(), sleep=lambda s: None)
    assert code == 0
    assert json.loads(facts_path.read_text())["fetched"]["forge_status"] == "skipped (--no-forge)"
    assert not any("raw.githubusercontent.com" in c["url"] for c in fake_send.calls)


def test_forge_unreachable_degrades_with_note(tmp_path: Path, fake_send):
    _wire(fake_send, ["Ulalek, Fused Atrocity", "Ancient Tomb", "Basalt Monolith", "Forsaken Monument"])
    fake_send.route("GET", "https://raw.githubusercontent.com/", lambda p, b: (500, {}, "down"))
    deck = tmp_path / "d.txt"
    deck.write_text("1 Ulalek, Fused Atrocity\n\n1 Ancient Tomb\n")
    facts_path = tmp_path / "facts.json"
    code = main([str(deck), "--facts-json", str(facts_path), "--cache-dir", str(tmp_path)], send=fake_send,
                stdout=io.StringIO(), stderr=io.StringIO(), sleep=lambda s: None)
    assert code == 0
    assert json.loads(facts_path.read_text())["fetched"]["forge_status"].startswith("Forge unreachable")
