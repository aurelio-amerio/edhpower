from pathlib import Path

from edhpower.decklist import front_face, load_decklist, parse_decklist, parse_decklist_json

REPO_STYLE = """1 Ulalek, Fused Atrocity

// Lands (3)
1 Ancient Tomb
1 Eldrazi Temple
18 Wastes
// trailing note
"""


def test_plain_entries_and_counts():
    d = parse_decklist(REPO_STYLE)
    names = {e.name: e.count for e in d.entries}
    assert names == {"Ulalek, Fused Atrocity": 1, "Ancient Tomb": 1, "Eldrazi Temple": 1, "Wastes": 18}
    assert d.total_cards == 21
    assert d.errors == []


def test_line1_followed_by_blank_is_commander_with_warning():
    d = parse_decklist(REPO_STYLE)
    assert d.commanders == ["Ulalek, Fused Atrocity"]
    assert [e for e in d.entries if e.is_commander][0].name == "Ulalek, Fused Atrocity"
    assert any("line 1" in w for w in d.warnings)


def test_no_blank_after_line1_means_no_commander():
    d = parse_decklist("1 Sol Ring\n1 Ancient Tomb\n")
    assert d.commanders == []
    assert d.warnings == []


def test_comment_lines_are_ignored_and_lineno_kept():
    d = parse_decklist("// header\n1 Sol Ring\n")
    assert len(d.entries) == 1 and d.entries[0].lineno == 2 and d.entries[0].raw == "1 Sol Ring"


def test_unparseable_line_is_reported_not_dropped():
    d = parse_decklist("1 Sol Ring\nthis is not an entry\n")
    assert len(d.entries) == 1
    assert d.errors == ["line 2: this is not an entry"]


def test_duplicate_names_are_merged():
    d = parse_decklist("1 Wastes\n\n2 Wastes\n3 Wastes\n")
    assert [(e.name, e.count) for e in d.entries if e.name == "Wastes"] == [("Wastes", 6)]


ARCHIDEKT = """1x All Is Dust (m3c) 152 [Removal]
1x Ancient Tomb (plst) TMP-315 [Land]
1x Ulalek, Fused Atrocity (m3c) 2 [Commander]
2x Wastes (oge) 183 [Land]
1x Command Tower (m3c) 300
"""


def test_archidekt_lines_parse_and_commander_tag_wins():
    d = parse_decklist(ARCHIDEKT)
    assert {e.name: e.count for e in d.entries} == {
        "All Is Dust": 1, "Ancient Tomb": 1, "Ulalek, Fused Atrocity": 1, "Wastes": 2, "Command Tower": 1,
    }
    assert d.commanders == ["Ulalek, Fused Atrocity"]
    assert d.warnings == []


def test_commander_marker_comment_marks_next_entry():
    d = parse_decklist("1 Sol Ring\n// Commander\n1 Zhulodok, Void Gorger\n1 Wastes\n")
    assert d.commanders == ["Zhulodok, Void Gorger"]
    assert d.warnings == []


def test_override_beats_heuristic_and_supports_partners():
    d = parse_decklist("1 Sol Ring\n\n1 Thrasios, Triton Hero\n1 Tymna the Weaver\n",
                       commander_override=["Thrasios, Triton Hero", "Tymna the Weaver"])
    assert d.commanders == ["Thrasios, Triton Hero", "Tymna the Weaver"]
    assert all("line 1" not in w for w in d.warnings)


def test_override_name_missing_from_list_is_an_error():
    d = parse_decklist("1 Sol Ring\n", commander_override=["Not Here"])
    assert d.commanders == []
    assert any("Not Here" in e for e in d.errors)


def test_dfc_name_is_split_to_front_face():
    d = parse_decklist("1 Wandering Archaic // Explore the Vastlands\n")
    e = d.entries[0]
    assert e.name == "Wandering Archaic"
    assert e.raw == "1 Wandering Archaic // Explore the Vastlands"


def test_json_form():
    d = parse_decklist_json('{"commanders": ["Zhulodok, Void Gorger"], "main": [{"name": "Wastes", "count": 18}]}')
    assert d.commanders == ["Zhulodok, Void Gorger"]
    assert {e.name: e.count for e in d.entries} == {"Zhulodok, Void Gorger": 1, "Wastes": 18}


def test_load_decklist_dispatches_on_suffix(tmp_path: Path):
    p = tmp_path / "d.txt"
    p.write_text("1 Sol Ring\n")
    assert load_decklist(p).entries[0].name == "Sol Ring"
    j = tmp_path / "d.json"
    j.write_text('{"commanders": [], "main": [{"name": "Sol Ring", "count": 1}]}')
    assert load_decklist(j).entries[0].name == "Sol Ring"


def test_json_commander_repeated_in_main_is_not_double_counted():
    d = parse_decklist_json('{"commanders": ["Zhulodok, Void Gorger"], "main": [{"name": "Zhulodok, Void Gorger", "count": 1}, {"name": "Wastes", "count": 18}]}')
    assert {e.name: e.count for e in d.entries} == {"Zhulodok, Void Gorger": 1, "Wastes": 18}
    assert d.total_cards == 19
    assert d.commanders == ["Zhulodok, Void Gorger"]


def test_dfc_name_with_single_slash_is_split_to_front_face():
    d = parse_decklist("1 Walk-In Closet/Forgotten Cellar\n")
    assert d.entries[0].name == "Walk-In Closet"


def test_dfc_name_with_spaced_single_slash_is_split_to_front_face():
    d = parse_decklist("1 Walk-In Closet / Forgotten Cellar\n")
    assert d.entries[0].name == "Walk-In Closet"


def test_front_face_accepts_single_slash():
    assert front_face("Walk-In Closet/Forgotten Cellar") == "Walk-In Closet"
