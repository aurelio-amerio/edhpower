import pytest

from edhpower.forge import FORGE_RAW, ForgeClient, ForgeError, forge_slug
from edhpower.http import HttpClient

COMMIT = "a" * 40
RAW = "https://raw.githubusercontent.com/Card-Forge/forge/"


@pytest.mark.parametrize("name,slug", [
    ("Azusa, Lost but Seeking", "azusa_lost_but_seeking"),
    ("Walk-In Closet // Forgotten Cellar", "walk_in_closet_forgotten_cellar"),
    ("Thespian's Stage", "thespians_stage"),
    ("Jötun Grunt", "jotun_grunt"),
    ("Lim-Dûl the Necromancer", "lim_dul_the_necromancer"),
    ("Six", "six"),
])
def test_forge_slug(name, slug):
    assert forge_slug(name) == slug


def _client(tmp_path, fake_send, progress=None) -> ForgeClient:
    http = HttpClient("edhpower/test", send=fake_send, sleep=lambda s: None)
    return ForgeClient(http, tmp_path / "forge", COMMIT, progress=progress)


def test_url_template():
    assert FORGE_RAW.format(commit=COMMIT, initial="s", slug="six") == f"{RAW}{COMMIT}/forge-gui/res/cardsfolder/s/six.txt"


def test_fetch_caches_text(tmp_path, fake_send):
    fake_send.route("GET", RAW, lambda p, b: (200, {}, "Name:Six\nManaCost:2 R\n"))
    c = _client(tmp_path, fake_send)
    assert c.fetch("Six") == "Name:Six\nManaCost:2 R\n"
    assert c.fetch("Six") == "Name:Six\nManaCost:2 R\n"
    assert len(fake_send.calls) == 1
    assert fake_send.calls[0]["url"] == FORGE_RAW.format(commit=COMMIT, initial="s", slug="six")
    # a fresh client over the same directory still reads the cache
    assert _client(tmp_path, fake_send).fetch("Six") is not None and len(fake_send.calls) == 1


def test_404_returns_none_and_is_cached(tmp_path, fake_send):
    fake_send.route("GET", RAW, lambda p, b: (404, {}, "404: Not Found"))
    c = _client(tmp_path, fake_send)
    assert c.fetch("Nope") is None
    assert c.fetch("Nope") is None
    assert len(fake_send.calls) == 1


def test_500_raises_forge_error(tmp_path, fake_send):
    fake_send.route("GET", RAW, lambda p, b: (500, {}, "down"))
    with pytest.raises(ForgeError):
        _client(tmp_path, fake_send).fetch("Six")


def test_fetch_many_preserves_order_and_nones(tmp_path, fake_send):
    fake_send.route("GET", RAW, lambda p, b: (404, {}, "x"))
    fake_send.route("GET", f"{RAW}{COMMIT}/forge-gui/res/cardsfolder/s/six.txt", lambda p, b: (200, {}, "Name:Six\n"))
    msgs: list[str] = []
    out = _client(tmp_path, fake_send, progress=msgs.append).fetch_many(["Zed", "Six", "Alpha"])
    assert list(out) == ["Zed", "Six", "Alpha"]
    assert out == {"Zed": None, "Six": "Name:Six\n", "Alpha": None}
    assert msgs[0] == "forge: 1/3 Zed" and msgs[-1] == "forge: 3/3 Alpha"
