"""Command-line entry point: parse → resolve → tags → combos → facts → analyse → report + JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO

from edhpower import __version__
from edhpower.analysis import analyse
from edhpower.config import load_config
from edhpower.decklist import load_decklist
from edhpower.facts import build_facts, load_facts, save_facts
from edhpower.forge import ForgeClient, ForgeError
from edhpower.http import HttpClient, HttpError, SendFn
from edhpower.report import render_text
from edhpower.scryfall import ScryfallClient
from edhpower.spellbook import SpellbookClient, SpellbookError
from edhpower.tags import TagCache, TagConfigError, TagFetcher

EXIT_OK, EXIT_USAGE, EXIT_UNRESOLVED, EXIT_DATASOURCE = 0, 1, 2, 3


def default_cache_dir() -> Path:
    env = os.environ.get("EDHPOWER_CACHE_DIR")
    return Path(env) if env else Path.home() / ".cache" / "edhpower"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="edhpower", description="Commander deck analysis: curve, combos, official bracket, power scores, tipping point, goldfish simulation.")
    p.add_argument("decklist", nargs="?", help="decklist .txt (plain or Archidekt) or .json")
    p.add_argument("--commander", action="append", default=None, metavar="NAME", help="commander name (repeat for partners); overrides file markers")
    p.add_argument("--json", type=Path, metavar="PATH", help="write the full analysis (facts, bracket, scores, tipping, sim, narrative, freshness) as JSON")
    p.add_argument("--facts-json", type=Path, metavar="PATH", help="write DeckFacts only (replayable with --from-facts)")
    p.add_argument("--from-facts", type=Path, metavar="PATH", help="skip parsing and network; analyse a saved DeckFacts file")
    p.add_argument("--allow-unresolved", action="store_true", help="continue when some cards cannot be resolved")
    p.add_argument("--no-combos", action="store_true", help="skip Commander Spellbook")
    p.add_argument("--no-forge", action="store_true", help="skip Card-Forge scripts (the simulator then models no card effects from them)")
    p.add_argument("--no-tags", action="store_true", help="skip the oracle-tag cache (component score and tutor criterion become unevaluated)")
    p.add_argument("--refresh-tags", action="store_true", help="refetch every oracle-tag set (about 150 requests at 1/s)")
    p.add_argument("--iterations", type=int, default=None, metavar="N", help="goldfish simulation games (default: [sim].iterations in scoring.toml, 20000)")
    p.add_argument("--no-sim", action="store_true", help="skip the goldfish simulation (the narrative's sim-based findings become unavailable)")
    p.add_argument("--cache-dir", type=Path, default=None, help="cache directory (default: $EDHPOWER_CACHE_DIR or ~/.cache/edhpower)")
    p.add_argument("--version", action="version", version=f"edhpower {__version__}")
    return p


def _tags(args: argparse.Namespace, http: HttpClient, cache_dir: Path, err: IO[str]) -> tuple[TagCache | None, str | None]:
    """Returns (cache, unavailable_reason). Raises TagConfigError for an unknown slug."""
    if args.no_tags:
        return None, "skipped (--no-tags)"
    fetcher = TagFetcher(http, cache_dir / "tags", progress=lambda m: err.write(m + "\n"))
    try:
        cache = fetcher.ensure(refresh=args.refresh_tags)
    except (HttpError, OSError) as exc:
        return None, f"unavailable: {exc}"
    if not cache.complete:
        return cache, f"unavailable: tag cache incomplete ({len(cache.missing())} slug(s) missing)"
    return cache, None


def main(
    argv: list[str] | None = None,
    *,
    send: SendFn | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    args = build_parser().parse_args(argv)

    if args.iterations is not None and args.iterations < 1:
        out.write("error: --iterations must be at least 1\n")
        return EXIT_USAGE

    if args.from_facts:
        try:
            facts = load_facts(args.from_facts)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            out.write(f"error: cannot load facts {args.from_facts}: {exc}\n")
            return EXIT_USAGE
    else:
        if not args.decklist:
            out.write("error: a decklist path or --from-facts is required\n")
            return EXIT_USAGE
        path = Path(args.decklist)
        if not path.exists():
            out.write(f"error: decklist not found: {path}\n")
            return EXIT_USAGE
        try:
            parsed = load_decklist(path, args.commander)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            out.write(f"error: cannot parse decklist {path}: {exc}\n")
            return EXIT_USAGE
        if parsed.errors:
            for e in parsed.errors:
                out.write(f"error: {e}\n")
            return EXIT_USAGE
        if not parsed.commanders:
            out.write("error: no commander identified; pass --commander NAME (repeat for partners)\n")
            return EXIT_USAGE

        cache_dir = args.cache_dir or default_cache_dir()
        http = HttpClient(user_agent=f"edhpower/{__version__}", min_interval=0.1, send=send, sleep=sleep)
        scry = ScryfallClient(http, cache_dir / "cards.jsonl")
        try:
            resolution = scry.resolve([e.name for e in parsed.entries])
        except (HttpError, OSError) as exc:
            out.write(f"error: Scryfall unreachable: {exc}\n")
            return EXIT_DATASOURCE
        missing_cmd = [n for n in parsed.commanders if n in resolution.unresolved]
        if missing_cmd:
            out.write(f"error: commander(s) could not be resolved: {', '.join(missing_cmd)}\n")
            return EXIT_UNRESOLVED
        if resolution.unresolved and not args.allow_unresolved:
            out.write("error: unresolved card names (pass --allow-unresolved to continue):\n")
            for n in resolution.unresolved:
                out.write(f"  - {n}\n")
            return EXIT_UNRESOLVED

        forge_scripts: dict[str, str | None] | None = None
        forge_reason: str | None = None
        forge_cfg = load_config().forge
        if args.no_forge:
            forge_reason = "skipped (--no-forge)"
        else:
            forge_http = http.with_min_interval(forge_cfg.min_interval)
            forge = ForgeClient(forge_http, cache_dir / "forge" / forge_cfg.commit, forge_cfg.commit, progress=lambda m: err.write(m + "\n"))
            try:
                forge_scripts = forge.fetch_many([resolution.cards[e.name].name for e in parsed.entries if e.name in resolution.cards])
            except (ForgeError, OSError) as exc:
                forge_scripts, forge_reason = None, f"Forge unreachable: {exc}"

        try:
            tag_cache, tags_reason = _tags(args, http, cache_dir, err)
        except TagConfigError as exc:
            out.write(f"error: tag configuration error: {exc}\n")
            return EXIT_DATASOURCE

        combos = None
        reason: str | None = None
        if args.no_combos:
            reason = "skipped (--no-combos)"
        else:
            commanders = [resolution.cards[e.name].name for e in parsed.entries if e.is_commander and e.name in resolution.cards]
            main_list = [(resolution.cards[e.name].name, e.count) for e in parsed.entries if not e.is_commander and e.name in resolution.cards]
            try:
                combos = SpellbookClient(http).fetch(commanders, main_list)
            except (SpellbookError, OSError) as exc:
                reason = f"Spellbook unreachable: {exc}"

        facts = build_facts(parsed, resolution, combos, reason, str(path), tag_cache=tag_cache, tags_unavailable_reason=tags_reason,
                             forge_scripts=forge_scripts, forge_commit=forge_cfg.commit, forge_unavailable_reason=forge_reason)
        if args.facts_json:
            Path(args.facts_json).parent.mkdir(parents=True, exist_ok=True)
            save_facts(facts, args.facts_json)

    analysis = analyse(facts, iterations=args.iterations, run_sim=not args.no_sim)
    out.write(render_text(analysis))

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return EXIT_OK
