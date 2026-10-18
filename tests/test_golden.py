"""Golden values: changing a scoring constant or a rule must change these deliberately (rerun golden_update.py)."""

import json
from pathlib import Path

import pytest

from edhpower.config import load_config

from .golden_update import GOLDEN_ITERATIONS, golden_for

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "golden.json").read_text(encoding="utf-8"))


def test_golden_config_matches_current_config():
    assert GOLDEN["config"] == {**load_config().stamp(), "sim_iterations": GOLDEN_ITERATIONS}


@pytest.mark.parametrize("name", sorted(GOLDEN["decks"]))
def test_golden_values(name):
    got = golden_for(name)
    want = GOLDEN["decks"][name]
    assert got.keys() == want.keys()
    for key, value in want.items():
        if isinstance(value, float):
            assert got[key] == pytest.approx(value, abs=1e-6), key
        else:
            assert got[key] == value, key
