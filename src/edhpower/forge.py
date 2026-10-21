"""Card-Forge card scripts: fetched from raw.githubusercontent.com at a pinned commit and cached as text."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path

from edhpower.http import HttpClient, HttpError

FORGE_RAW = "https://raw.githubusercontent.com/Card-Forge/forge/{commit}/forge-gui/res/cardsfolder/{initial}/{slug}.txt"


class ForgeError(Exception):
    """Forge unreachable, or a non-404 failure."""


def _face_slug(face: str) -> str:
    text = unicodedata.normalize("NFKD", face)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("-", "_").replace(" ", "_")
    text = re.sub(r"[^a-z0-9_]", "", text)
    return re.sub(r"_+", "_", text)


def forge_slug(name: str) -> str:
    return "_".join(_face_slug(face) for face in name.split(" // "))


class ForgeClient:
    def __init__(self, http: HttpClient, cache_dir: Path, commit: str, progress: Callable[[str], None] | None = None) -> None:
        self._http = http
        self._dir = Path(cache_dir)
        self._commit = commit
        self._progress = progress

    def fetch(self, name: str) -> str | None:
        slug = forge_slug(name)
        path = self._dir / f"{slug}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8") or None
        url = FORGE_RAW.format(commit=self._commit, initial=slug[:1], slug=slug)
        try:
            status, text = self._http.get_text(url)
        except HttpError as exc:
            raise ForgeError(str(exc)) from exc
        if status == 404:
            text = ""
        elif status != 200:
            raise ForgeError(f"HTTP {status} for {url}")
        self._dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return text or None

    def fetch_many(self, names: Iterable[str]) -> dict[str, str | None]:
        names = list(names)
        out: dict[str, str | None] = {}
        for i, name in enumerate(names, 1):
            if self._progress:
                self._progress(f"forge: {i}/{len(names)} {name}")
            out[name] = self.fetch(name)
        return out
