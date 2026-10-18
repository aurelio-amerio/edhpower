import tomllib
from importlib.metadata import version as distribution_version
from pathlib import Path

import edhpower

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_is_string():
    assert isinstance(edhpower.__version__, str)
    assert edhpower.__version__.count(".") == 2


def test_module_version_agrees_with_packaging_metadata():
    """The module version is what the Scryfall User-Agent reports; the distribution version is what
    an installed edhpower reports. They drifted once (0.2.0 vs 0.1.0) — they must not drift again."""
    assert distribution_version("edhpower") == edhpower.__version__
    if PYPROJECT.exists():  # source checkout: the declared version must agree too
        declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
        assert declared == edhpower.__version__
