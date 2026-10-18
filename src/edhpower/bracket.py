"""Official WotC Commander bracket criteria applied to DeckFacts. Returns a floor, not a placement."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from importlib import resources
from typing import Any, Literal

from edhpower.config import SimConfig
from edhpower.facts import DeckFacts
from edhpower.payoffs import DeckPayoffs

Status = Literal["ok", "triggered", "review", "unevaluated"]


@dataclass
class Criterion:
    name: str
    status: Status
    floor: int | None
    triggers: list[str]
    detail: str


@dataclass
class BracketVerdict:
    minimum_bracket: int
    criteria: list[Criterion]
    notes: list[str]
    source_url: str
    source_date: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_rules() -> dict[str, Any]:
    with resources.files("edhpower.data").joinpath("brackets.toml").open("rb") as fh:
        return tomllib.load(fh)


def evaluate_bracket(facts: DeckFacts, payoffs: DeckPayoffs | None = None, sim_cfg: SimConfig | None = None) -> BracketVerdict:
    rules = load_rules()
    criteria: list[Criterion] = []
    notes: list[str] = ["Brackets 1 (Exhibition) and 5 (cEDH) are self-declared; this is the minimum bracket the deckbuilding criteria allow."]
    combos = facts.combos
    cmc_by_name = {e.name: e.card.cmc for e in facts.entries}

    # Game Changers — Scryfall is authoritative, Spellbook cross-checks.
    gcs = list(facts.game_changers)
    n = len(gcs)
    if n == 0:
        criteria.append(Criterion("game_changers", "ok", None, [], "no Game Changers"))
    elif n <= rules["game_changers"]["bracket3_max"]:
        criteria.append(Criterion("game_changers", "triggered", 3, gcs, f"{n} Game Changer(s): allowed in Bracket 3 (max {rules['game_changers']['bracket3_max']})"))
    else:
        criteria.append(Criterion("game_changers", "triggered", 4, gcs, f"{n} Game Changers exceeds the Bracket 3 maximum"))
    if combos is not None:
        scry_gc = {e.name: e.card.game_changer for e in facts.entries}
        for name, flags in combos.card_flags.items():
            scry = scry_gc.get(name)
            if scry is None:
                continue
            if scry != flags.game_changer:
                notes.append(f"Scryfall and Spellbook disagree on whether '{name}' is a Game Changer (Scryfall={scry}, Spellbook={flags.game_changer}); one source is stale.")

    if combos is None:
        reason = facts.combos_unavailable_reason or "combo data unavailable"
        for name in ("mass_land_denial", "extra_turns", "two_card_combos"):
            criteria.append(Criterion(name, "unevaluated", None, [], reason))
        notes.append(f"Spellbook data unavailable ({reason}); mass land denial, extra turns and two-card combos were not evaluated.")
    else:
        # Mass land denial
        mld = sorted({n for n, f in combos.card_flags.items() if f.mass_land_denial})
        mld += [" + ".join(line.piece_names) for line in combos.included if combos.combo_flags.get(line.id) and combos.combo_flags[line.id].mass_land_denial]
        criteria.append(Criterion("mass_land_denial", "triggered" if mld else "ok", 4 if mld else None, mld, "mass land denial is Bracket 4+" if mld else "none"))

        # Extra turns
        plain = sorted(n for n, f in combos.card_flags.items() if f.extra_turn)
        looped = [" + ".join(line.piece_names) for line in combos.included if combos.combo_flags.get(line.id) and combos.combo_flags[line.id].extra_turn]
        detail = f"{len(plain)} extra-turn card(s): {', '.join(plain) if plain else 'none'}"
        if looped:
            criteria.append(Criterion("extra_turns", "triggered", 4, looped, detail + "; chained/looped extra turns are Bracket 4+"))
        else:
            criteria.append(Criterion("extra_turns", "ok", None, [], detail))

        # Two-card infinite combos
        two: list[str] = []
        early: list[str] = []
        arguably: list[str] = []
        for line in combos.included:
            f = combos.combo_flags.get(line.id)
            if f is None:
                continue
            label = " + ".join(line.piece_names)
            if f.definitely_two_card:
                two.append(f"{label} (speed {f.speed if f.speed is not None else '?'})")
                total = sum(cmc_by_name.get(p, 0.0) for p in line.piece_names)
                if total <= rules["two_card_combos"]["early_total_mv_max"]:
                    early.append(f"{label} (total MV {int(total)})")
            elif f.arguably_two_card:
                arguably.append(label)
        detail = "two-card infinite combos are Bracket 3+ unless early-game" + (f"; arguably two-card: {', '.join(arguably)}" if arguably else "")
        criteria.append(Criterion("two_card_combos", "triggered" if two else "ok", 3 if two else None, two, detail if two else "none"))
        if payoffs is not None and sim_cfg is not None:
            from edhpower.sim.combos import classify   # local import: bracket must not depend on the sim package at import time
            self_harm = {"self_mill", "draw"}
            flagged: list[str] = []
            for line in combos.included:
                f = combos.combo_flags.get(line.id)
                if f is None or not f.definitely_two_card:
                    continue
                status, resources, _ = classify(line, sim_cfg, payoffs)
                if status == "no_payoff" and resources and set(resources) <= self_harm:
                    flagged.append(f"{' + '.join(line.piece_names)} ({'/'.join(resources)})")
            if flagged:
                criteria.append(Criterion(
                    "two_card_combos_no_payoff", "review", None, flagged,
                    "floors Bracket 3 by the published rule, but its only product is self-harm and the deck has no empty-library win; scrollvault would not floor on it",
                ))
        if early:
            criteria.append(Criterion(
                "two_card_combos_early_review", "review", None, early,
                f"pieces total MV <= {rules['two_card_combos']['early_total_mv_max']}: may be an early-game combo, which Bracket 3 forbids; needs human judgement",
            ))

    if facts.tags_status != "ok":
        criteria.append(Criterion("tutors", "unevaluated", None, [], f"tag cache unavailable ({facts.tags_status})"))
    else:
        tutors = list(facts.partition.get("tutors", []))
        n = facts.partition_counts.get("tutors", 0)
        review_min = rules["tutors"]["review_min"]
        detail = f"{n} tutor(s); " + (f"at or above the review threshold of {review_min}: " + rules["tutors"]["note"] if n >= review_min else f"below the review threshold of {review_min}")
        criteria.append(Criterion("tutors", "review" if n >= review_min else "ok", None, tutors, detail))

    floors = [c.floor for c in criteria if c.floor is not None]
    return BracketVerdict(max([2, *floors]), criteria, notes, rules["source_url"], rules["source_date"])
