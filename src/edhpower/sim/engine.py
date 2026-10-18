"""One goldfish game: on the play, no opponent, colours enforced, driven by SimCard fields."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from edhpower.config import SimConfig
from edhpower.sim.combos import SimLine, missing_pieces, payoff_ready, pieces_to_cast
from edhpower.sim.mana import COLORLESS, ManaCost, Unit, pay
from edhpower.sim.model import SimCard, SimDeck, reduction_applies

CLOCKS: tuple[str, ...] = ("commander", "mana_threshold", "tipping_target", "threat", "combat", "combo", "lethal_combo")
MAIN_ORDER: tuple[str, ...] = ("rock", "dork", "reducer", "ramp_spell", "draw_spell", "commander", "tutor", "combo",
                               "threat", "creature", "engine", "permanent")
CHEAPEST_FIRST = {"rock", "dork", "reducer", "engine", "permanent", "ramp_spell", "draw_spell", "tutor"}
UNTAP_RANK = {"permanents": 3, "artifacts": 2, "one_artifact": 1}


@dataclass
class Perm:
    card: SimCard
    entered: int
    tapped: bool = False


@dataclass
class GameRecord:
    clocks: dict[str, int | None]
    mana_by_turn: list[int]
    idle_by_turn: list[bool]


class Game:
    def __init__(self, deck: SimDeck, lines: list[SimLine], cfg: SimConfig, rng: random.Random, tipping_target: int) -> None:
        self.deck, self.cards, self.lines, self.cfg, self.rng = deck, deck.cards, lines, cfg, rng
        self.tipping_target = tipping_target
        self.library: list[str] = list(deck.library)
        self.rng.shuffle(self.library)
        self.hand: list[str] = []
        self.board: list[Perm] = []
        self.command_zone: set[str] = {c.name for c in deck.commanders}
        self.pool: list[Unit] = []
        self.turn = 0
        self.produced = 0
        self.damage = 0
        self.casts = 0
        self.fired: set[str] = set()
        self.pending_payoff: set[str] = set()
        self.record = GameRecord({k: None for k in CLOCKS}, [0] * (cfg.max_turn + 1), [False] * (cfg.max_turn + 1))
        self._opening_hand()

    # ---- setup -------------------------------------------------------------------------------
    def _draw(self, n: int) -> None:
        for _ in range(n):
            if self.library:
                self.hand.append(self.library.pop())

    def _opening_hand(self) -> None:
        self._draw(self.cfg.opening_hand)
        lands = sum(1 for n in self.hand if self.cards[n].is_land)
        if self.cfg.mulligan_min_lands <= lands <= self.cfg.mulligan_max_lands:
            return
        self.library = list(self.deck.library)
        self.rng.shuffle(self.library)
        self.hand = []
        self._draw(self.cfg.opening_hand)
        if not self.hand:
            return
        nonlands = [n for n in self.hand if not self.cards[n].is_land]
        bottom = max(nonlands, key=lambda n: self.cards[n].cmc) if nonlands else self.hand[0]
        self.hand.remove(bottom)
        self.library.insert(0, bottom)

    # ---- board queries -------------------------------------------------------------------------
    def _stamp(self, clock: str) -> None:
        if self.record.clocks[clock] is None:
            self.record.clocks[clock] = self.turn

    def _artifact_count(self) -> int:
        return sum(1 for p in self.board if p.card.is_artifact)

    def _creature_count(self) -> int:
        return sum(1 for p in self.board if p.card.is_creature)

    def _tron_names(self) -> set[str]:
        return {p.card.name for p in self.board if "tron" in p.card.params}

    def _urza_count(self) -> int:
        return sum(1 for p in self.board if "tron" in p.card.params or p.card.params.get("scales_with") == "urza_lands")

    def _untap_scope(self) -> int:
        return max((UNTAP_RANK.get(str(p.card.params.get("scope")), 0) for p in self.board if p.card.special == "untap"), default=0)

    def _zones(self) -> tuple[set[str], set[str], set[str]]:
        return {p.card.name for p in self.board}, set(self.hand), set(self.command_zone)

    def _reduction_for(self, c: SimCard) -> int:
        return sum(p.card.reduction for p in self.board
                   if p.card.reduction and reduction_applies(p.card.reduction_scope, c, self.deck.commander_subtypes))

    def _try_pay(self, c: SimCard, units: list[Unit] | None = None) -> list[Unit] | None:
        return pay(c.cost, self.pool if units is None else units, self._reduction_for(c))

    def _commander_castable(self) -> bool:
        return any(self._try_pay(self.cards[n]) is not None for n in self.command_zone)

    # ---- turn phases ---------------------------------------------------------------------------
    def _untap(self) -> None:
        scope = self._untap_scope()
        one_used = False
        for p in self.board:
            if "untap_cost" not in p.card.params:
                p.tapped = False
            elif scope == 3 or (scope == 2 and p.card.is_artifact):
                p.tapped = False
            elif scope == 1 and p.card.is_artifact and not one_used:
                p.tapped, one_used = False, True

    def _units_from(self, p: Perm) -> int:
        c = p.card
        if c.is_land:
            if "tron" in c.params:
                return int(c.params["tron"]) if len(self._tron_names()) == 3 else 1
            scales = c.params.get("scales_with")
            if scales == "creatures":
                return self._creature_count()
            if scales == "urza_lands":
                return self._urza_count() if self._artifact_count() >= self.cfg.metalcraft_count else 1
            return c.mana
        if c.role == "dork" and p.entered == self.turn:
            return 0
        if c.role in ("rock", "dork"):
            if c.params.get("requires") == "metalcraft" and self._artifact_count() < self.cfg.metalcraft_count:
                return 0
            return c.mana
        return 0

    def _add_units(self, kinds: frozenset[str], n: int, from_tap: bool = True) -> None:
        kinds = kinds or COLORLESS
        self.pool.extend([kinds] * n)
        self.produced += n
        if from_tap and kinds == COLORLESS and any(p.card.special == "doubler" for p in self.board):
            self.pool.append(COLORLESS)
            self.produced += 1

    def _produce(self) -> list[Unit]:
        self.pool = []
        for p in self.board:
            if p.tapped:
                continue
            n = self._units_from(p)
            if n:
                p.tapped = True
                self._add_units(p.card.produces, n, True)
        return self.pool

    def _needed_colors(self) -> frozenset[str]:
        needed: set[str] = set()
        for n in self.hand:
            c = self.cards[n]
            if not c.is_land:
                needed |= {next(iter(pip.options)) for pip in c.cost.pips if len(pip.options) == 1}
        have: set[str] = set()
        for p in self.board:
            have |= p.card.produces
        return frozenset(needed - have)

    def _land_priority(self, c: SimCard, needed: frozenset[str]) -> int:
        if c.params.get("sacrifice_on_land_drop"):
            return 8 if self.turn <= 2 else 1
        if "tron" in c.params:
            have = len(self._tron_names())
            return 9 if have == 2 else 7 if have == 1 else 5
        if c.mana >= 2 and not c.enters_tapped:
            return 10
        if c.params.get("scales_with") == "creatures":
            return 3 + self._creature_count()
        if c.mana == 0:
            return 4 if self.turn >= 4 else 1
        fixes = bool(c.produces & needed)
        if c.enters_tapped:
            return 3 if fixes else 2
        return 6 if fixes else 5

    def _play_land(self) -> None:
        lands = [n for n in self.hand if self.cards[n].is_land]
        if not lands:
            return
        needed = self._needed_colors()
        pick = max(lands, key=lambda n: (self._land_priority(self.cards[n], needed), -self.hand.index(n)))
        self.board = [p for p in self.board if not p.card.params.get("sacrifice_on_land_drop")]
        self.hand.remove(pick)
        card = self.cards[pick]
        self.board.append(Perm(card, self.turn, tapped=card.enters_tapped))

    def _fetch_land(self) -> bool:
        idx = next((i for i, n in enumerate(self.library) if self.cards[n].is_land and self.cards[n].mana == 1), None)
        if idx is None:
            return False
        name = self.library.pop(idx)
        self.board.append(Perm(self.cards[name], self.turn, tapped=True))
        return True

    def _resolve(self, name: str, from_hand: bool) -> None:
        """Put a paid-for card where it goes and apply its effect. Payment happened already."""
        c = self.cards[name]
        if from_hand:
            self.hand.remove(name)
        else:
            self.command_zone.discard(name)
            self._stamp("commander")
        self.casts += 1
        if c.role == "threat" and from_hand:
            self._stamp("threat")
        if c.role == "one_shot":
            self._add_units(c.produces, c.mana, False)
            return
        if c.role == "ramp_spell":
            self._fetch_land()
            return
        if c.role == "draw_spell":
            self._draw(c.draw)
            return
        if c.is_spell:
            return
        perm = Perm(c, self.turn)
        self.board.append(perm)
        if c.role == "rock":
            n = self._units_from(perm)
            if n:
                perm.tapped = True
                self._add_units(c.produces, n, True)

    def _cast(self, name: str, from_hand: bool = True) -> None:
        left = self._try_pay(self.cards[name])
        assert left is not None, name
        self.pool = left
        self._resolve(name, from_hand)

    def _castable(self, role: str) -> list[str]:
        names = [n for n in self.hand if self.cards[n].role == role and self._try_pay(self.cards[n]) is not None]
        key = (lambda n: self.cards[n].cmc) if role in CHEAPEST_FIRST else (lambda n: -self.cards[n].cmc)
        return sorted(names, key=key)

    def _tutor_target(self) -> str | None:
        board, hand, cz = self._zones()
        library = set(self.library)
        for line in self.lines:
            if line.id in self.fired:
                continue
            missing = missing_pieces(line, board, hand, cz)
            if len(missing) == 1 and missing[0] in library:
                return missing[0]
        return None

    def _try_tutor(self) -> bool:
        target = self._tutor_target()
        if target is None:
            return False
        tutors = self._castable("tutor")
        if tutors:
            self._cast(tutors[0])
            self.library.remove(target)
            self.hand.append(target)
            return True
        tc = self.cards[target]
        for p in self.board:
            cost = p.card.params.get("tutor_cost")
            if cost is None or not (tc.is_creature and tc.is_colorless):
                continue
            left = pay(ManaCost(int(cost), ()), self.pool)
            if left is not None:
                self.pool = left
                self.library.remove(target)
                self.hand.append(target)
                self.casts += 1
                return True
        return False

    def _try_combo(self) -> bool:
        board, hand, cz = self._zones()
        for line in self.lines:
            if line.id in self.fired:
                continue
            to_cast = pieces_to_cast(line, board, hand, cz)
            if to_cast is None:
                continue
            units: list[Unit] | None = list(self.pool)
            for n in to_cast:
                units = self._try_pay(self.cards[n], units)
                if units is None:
                    break
            if units is not None:
                units = pay(ManaCost(line.extra_mana, ()), units)
            if units is None:
                continue
            self.pool = units
            for n in to_cast:
                self._resolve(n, from_hand=n in hand)
            self.fired.add(line.id)
            self._stamp("combo")
            board_now, hand_now, _ = self._zones()
            if line.lethal or payoff_ready(line, board_now, hand_now):
                self._stamp("lethal_combo")
            elif line.payoff is not None:
                self.pending_payoff.add(line.id)
            return True
        return False

    def _check_pending_payoffs(self) -> None:
        """A fired engine whose payoff arrived later: the lethal clock stamps the turn the condition first holds."""
        if not self.pending_payoff:
            return
        board, hand, _ = self._zones()
        for line in self.lines:
            if line.id in self.pending_payoff and payoff_ready(line, board, hand):
                self._stamp("lethal_combo")
                self.pending_payoff.clear()
                return

    def _try_one_shot(self) -> bool:
        for n in self._castable("one_shot"):
            c = self.cards[n]
            after = self._try_pay(c)
            if after is None:
                continue
            after = after + [c.produces or COLORLESS] * c.mana
            if len(after) <= len(self.pool):
                continue
            enables = any(self._try_pay(self.cards[m]) is None and self._try_pay(self.cards[m], after) is not None
                          for m in self.hand if m != n and self.cards[m].role not in ("held", "land", "one_shot"))
            if enables or any(self._try_pay(self.cards[m], after) is not None and self._try_pay(self.cards[m]) is None for m in self.command_zone):
                self._cast(n)
                return True
        return False

    def _try_role(self, role: str) -> bool:
        if role == "commander":
            for n in sorted(self.command_zone):
                if self._try_pay(self.cards[n]) is not None:
                    self._cast(n, from_hand=False)
                    return True
            return False
        if role == "tutor":
            return self._try_tutor()
        if role == "combo":
            return self._try_combo()
        if role == "ramp_spell" and not any(self.cards[n].is_land and self.cards[n].mana == 1 for n in self.library):
            return False
        names = self._castable(role)
        if not names:
            return False
        self._cast(names[0])
        return True

    def _main_phase(self) -> None:
        progressed = True
        while progressed:
            progressed = any(self._try_role(role) for role in MAIN_ORDER)   # short-circuits at the first cast
            if not progressed:
                progressed = self._try_one_shot()

    def take_turn(self) -> None:
        self.turn += 1
        t = self.turn
        self.casts = 0
        self.produced = 0
        self._untap()
        if t > 1:
            self._draw(1)
        self._play_land()
        self._produce()
        if self._commander_castable():
            self._stamp("commander")
        self._main_phase()
        self._check_pending_payoffs()
        if self._commander_castable():
            self._stamp("commander")
        if t <= self.cfg.max_turn:
            self.record.mana_by_turn[t] = self.produced
            self.record.idle_by_turn[t] = self.casts == 0
        if self.produced >= self.cfg.mana_threshold:
            self._stamp("mana_threshold")
        if self.produced >= self.tipping_target:
            self._stamp("tipping_target")
        self.damage += sum(p.card.power for p in self.board if p.card.is_creature and p.entered < t)
        if self.damage >= self.cfg.lethal_damage:
            self._stamp("combat")


def play_game(deck: SimDeck, lines: list[SimLine], cfg: SimConfig, rng: random.Random, tipping_target: int) -> GameRecord:
    game = Game(deck, lines, cfg, rng, tipping_target)
    for _ in range(cfg.max_turn):
        game.take_turn()
    return game.record
