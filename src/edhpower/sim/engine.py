"""One goldfish game: on the play, no opponent, colours enforced, driven by SimCard fields."""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field

from edhpower.config import SimConfig
from edhpower.sim.combos import SimLine, missing_pieces, payoff_ready, pieces_to_cast
from edhpower.sim.effects import Effect, condition_holds
from edhpower.sim.mana import ANY_COLOR, COLORLESS, ManaCost, Unit, pay
from edhpower.sim.model import SimCard, SimDeck, reduction_applies, token_card

CLOCKS: tuple[str, ...] = ("commander", "mana_threshold", "tipping_target", "threat", "combat", "combo", "lethal_combo",
                           "lethal_table", "first_opponent", "win")
MAIN_ORDER: tuple[str, ...] = ("rock", "dork", "reducer", "ramp_spell", "draw_spell", "commander", "tutor", "combo",
                               "threat", "creature", "engine", "permanent")
CHEAPEST_FIRST = {"rock", "dork", "reducer", "engine", "permanent", "ramp_spell", "draw_spell", "tutor"}
UNTAP_RANK = {"permanents": 3, "artifacts": 2, "one_artifact": 1}


@dataclass
class Perm:
    card: SimCard
    entered: int
    tapped: bool = False
    counters: int = 0   # +1/+1 counters


@dataclass
class GameRecord:
    clocks: dict[str, int | None]
    mana_by_turn: list[int]
    idle_by_turn: list[bool]
    tokens_by_turn: dict[str, list[int]] = field(default_factory=dict)   # token type -> tokens on board at end of turn
    board_power_by_turn: list[int] = field(default_factory=list)   # power of creatures able to attack that turn
    lands_by_turn: list[int] = field(default_factory=list)
    landfall_by_turn: list[int] = field(default_factory=list)   # lands that entered that turn
    damage_by_turn: list[int] = field(default_factory=list)   # life the opponents lost that turn, combat and drain
    max_swing: int = 0   # largest damage_by_turn


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
        self.damage = 0   # cumulative combat damage as if focused on one opponent: the `combat` clock
        self.casts = 0
        self.fired: set[str] = set()
        self.pending_payoff: set[str] = set()
        self.life: list[int] = [cfg.life_per_opponent] * cfg.opponents
        self.pumps: list[Effect] = []   # pumps resolved this turn; they end with it
        self.distinct_lands: set[str] = set()
        self.landfalls = 0   # lands that entered this turn
        self.token_cards: dict[tuple[str, int, int], SimCard] = {}
        n = cfg.max_turn + 1
        token_types = sorted({e.type for c in deck.cards.values() for top in c.effects for e in (top, top.upgrade)
                              if e is not None and e.do == "token"})
        self.record = GameRecord({k: None for k in CLOCKS}, [0] * n, [False] * n, {k: [0] * n for k in token_types},
                                 [0] * n, [0] * n, [0] * n, [0] * n)
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

    def _land_count(self) -> int:
        return sum(1 for p in self.board if p.card.is_land)

    def _token_count(self) -> int:
        return sum(1 for p in self.board if p.card.role == "token")

    @staticmethod
    def _in_scope(card: SimCard, scope: str) -> bool:
        """`scope` of an anthem/counters effect: "" every creature, "tokens" creature tokens, else a creature type."""
        if not card.is_creature:
            return False
        if scope == "tokens":
            return card.role == "token"
        return not scope or scope in card.subtypes

    def _anthems(self) -> list[Effect]:
        return [e for p in self.board for e in p.card.effects if e.do == "anthem"]

    def _anthem_bonus(self, card: SimCard, anthems: list[Effect] | None = None) -> int:
        return sum(e.power for e in (self._anthems() if anthems is None else anthems) if self._in_scope(card, e.type))

    def _board_power(self) -> int:
        """Power of the creatures (tokens included) able to attack this turn: printed power, counters and anthems."""
        anthems = self._anthems()
        return sum(p.card.power + p.counters + (self._anthem_bonus(p.card, anthems) if anthems else 0)
                   for p in self.board if p.card.is_creature and p.entered < self.turn)

    def _attack_powers(self, extra: Iterable[Effect] = ()) -> list[int]:
        """Positive damage of each creature able to attack this turn, largest first: printed power, counters,
        anthems, this turn's pumps and `extra` (pumps being considered)."""
        boosts = [*self._anthems(), *self.pumps, *extra]
        out = []
        for p in self.board:
            if p.card.is_creature and p.entered < self.turn:
                n = p.card.power + p.counters + sum(e.power for e in boosts if self._in_scope(p.card, e.type))
                if n > 0:
                    out.append(n)
        return sorted(out, reverse=True)

    @staticmethod
    def _assign(life: list[int], powers: list[int]) -> list[int]:
        """Life totals after `powers` (largest first) attack, each at the opponent with the most life left (ties: lowest index)."""
        life = list(life)
        for n in powers:
            i = max(range(len(life)), key=lambda k: (life[k], -k))
            life[i] -= n
        return life

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

    def _produce(self, fresh: bool = True) -> list[Unit]:
        """Tap every untapped source. `fresh` empties the pool first; otherwise mana already there (landfall) stays."""
        if fresh:
            self.pool = []
        for p in self.board:
            if p.tapped:
                continue
            n = self._units_from(p)
            if n:
                p.tapped = True
                self._add_units(p.card.produces, n, True)
        return self.pool

    def _pip_colors(self, names: Iterable[str]) -> set[str]:
        """Colours that the nonland cards `names` need as a single-colour pip."""
        out: set[str] = set()
        for n in names:
            c = self.cards[n]
            if not c.is_land:
                out |= {next(iter(pip.options)) for pip in c.cost.pips if len(pip.options) == 1}
        return out

    def _needed_colors(self) -> frozenset[str]:
        needed = self._pip_colors(self.hand)
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
        if any(p.card.params.get("sacrifice_on_land_drop") for p in self.board):
            self.board = [p for p in self.board if not p.card.params.get("sacrifice_on_land_drop")]
            self._lands_left()
        self.hand.remove(pick)
        card = self.cards[pick]
        perm = Perm(card, self.turn, tapped=card.enters_tapped)
        self.board.append(perm)
        self._land_entered(perm)

    def _basic_in_library(self) -> int | None:
        """Index of the first 1-mana land in the library (what a land-search spell finds), or None."""
        return next((i for i, n in enumerate(self.library) if self.cards[n].is_land and self.cards[n].mana == 1), None)

    def _fetch_land(self) -> bool:
        idx = self._basic_in_library()
        if idx is None:
            return False
        name = self.library.pop(idx)
        perm = Perm(self.cards[name], self.turn, tapped=True)
        self.board.append(perm)
        self._land_entered(perm)
        return True

    def _lands_left(self) -> None:
        self.distinct_lands = {p.card.name for p in self.board if p.card.is_land}

    def _sacrifice_lands(self, n: int) -> None:
        """Sacrifice `n` lands, lowest land priority first, keeping the last source of a colour that is still wanted."""
        for _ in range(n):
            lands = [p for p in self.board if p.card.is_land]
            if not lands:
                return
            wanted = self._pip_colors((*self.hand, *self.command_zone))
            needed = frozenset(wanted)

            def strands(p: Perm) -> bool:
                others: set[str] = set()
                for q in self.board:
                    if q is not p:
                        others |= q.card.produces
                return bool((p.card.produces & wanted) - others)

            victim = min(lands, key=lambda p: (strands(p), self._land_priority(p.card, needed)))
            self.board.remove(victim)
        self._lands_left()

    # ---- triggers ------------------------------------------------------------------------------
    def _triggered(self, on: str) -> list[tuple[Perm, Effect]]:
        """Board permanents' effects of kind `on`, in board order, snapshot before any of them resolves."""
        return [(p, e) for p in self.board if p.card.effects for e in p.card.effects if e.on == on]

    def _land_entered(self, perm: Perm) -> None:
        self.distinct_lands.add(perm.card.name)
        self.landfalls += 1
        for e in perm.card.effects:
            if e.on == "etb":
                self._fire(e, perm)
        for p, e in self._triggered("landfall"):
            self._fire(e, p)

    def _creature_entered(self, perm: Perm) -> None:
        """A creature entered: its own `etb` effects, then the `creature_etb` effects of every other permanent.
        A token entering does not fire token-making `creature_etb` effects: each such token would trigger it again."""
        for e in perm.card.effects:
            if e.on == "etb":
                self._fire(e, perm)
        is_token = perm.card.role == "token"
        for p, e in self._triggered("creature_etb"):
            if p is not perm and not (is_token and e.do == "token"):
                self._fire(e, p)

    def _tokens_created(self, n: int) -> None:
        """`token_created` effects fire once per token. Token-making ones are skipped: each token they make would
        trigger them again."""
        fx = [(p, e) for p, e in self._triggered("token_created") if e.do != "token"]
        for _ in range(n):
            for p, e in fx:
                self._fire(e, p)

    def _amount(self, e: Effect) -> int:
        return self._land_count() if e.n == "lands" else int(e.n)

    def _create_tokens(self, e: Effect) -> None:
        n = self._amount(e)
        if n <= 0:
            return
        key = (e.type, e.power, e.toughness)
        card = self.token_cards.get(key)
        if card is None:
            card = self.token_cards[key] = token_card(*key)
            self.record.tokens_by_turn.setdefault(e.type, [0] * (self.cfg.max_turn + 1))
        made = [Perm(card, self.turn) for _ in range(n)]
        self.board.extend(made)
        self._tokens_created(n)
        if any(e2.on == "creature_etb" for p in self.board for e2 in p.card.effects):
            for perm in made:
                self._creature_entered(perm)

    def _applicable(self, e: Effect) -> Effect | None:
        """The effect as it resolves now: its upgrade when that condition holds, None when its own condition fails."""
        if e.when or (e.upgrade is not None and e.upgrade.when):
            lands, tokens = self._land_count(), self._token_count()
            if e.upgrade is not None and condition_holds(e.upgrade.when, len(self.distinct_lands), lands, tokens):
                return e.upgrade
            if not condition_holds(e.when, len(self.distinct_lands), lands, tokens):
                return None
        return e

    def _fire(self, effect: Effect, source: Perm | None) -> None:
        """Resolve one effect. `source` is the permanent it belongs to (None for a spell)."""
        del source
        e = self._applicable(effect)
        if e is None:
            return
        if e.do == "token":
            self._create_tokens(e)
            return
        n = self._amount(e)
        if n <= 0:
            return
        if e.do == "counters":
            for p in self.board:
                if self._in_scope(p.card, e.type):
                    p.counters += n
        elif e.do == "mana":
            self._add_units(ANY_COLOR, n, from_tap=False)
        elif e.do == "drain":
            if e.each_opponent:
                self.life = [x - n for x in self.life]
            else:
                i = max(range(len(self.life)), key=lambda k: (self.life[k], -k))
                self.life[i] -= n
        elif e.do == "pump":
            self.pumps.append(e)
        # anthem is read by _board_power and _attack_powers

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
            self._sacrifice_lands(c.ramp_sacrifice_lands)
            for _ in range(c.ramp_to_battlefield):
                self._fetch_land()
            for _ in range(c.ramp_to_hand):
                idx = self._basic_in_library()
                if idx is None:
                    break
                self.hand.append(self.library.pop(idx))
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
        if c.is_creature:
            self._creature_entered(perm)
        else:
            for e in c.effects:
                if e.on == "etb":
                    self._fire(e, perm)

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

    def _try_pump(self) -> bool:
        """Cast the cheapest castable pump spell that makes this turn's attack kill an opponent who survives without it.
        Held otherwise: a pump is never cast for damage that kills nobody."""
        pumps = sorted({n for n in self.hand if any(e.on == "cast" and e.do == "pump" for e in self.cards[n].effects)},
                       key=lambda n: (self.cards[n].cmc, n))
        if not pumps:
            return False
        powers = self._attack_powers()
        if not powers:
            return False
        without = self._assign(self.life, powers)
        for n in pumps:
            c = self.cards[n]
            if self._try_pay(c) is None:
                continue
            fx = [a for e in c.effects if e.on == "cast" and e.do == "pump" and (a := self._applicable(e)) is not None]
            life = self._assign(self.life, self._attack_powers(fx))
            if any(w <= 0 < wo for w, wo in zip(life, without)):
                self._cast(n)
                for e in c.effects:
                    if e.on == "cast" and e.do == "pump":
                        self._fire(e, None)
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
        if role == "ramp_spell":
            lands = self._land_count()
            names = [n for n in names if self.cards[n].ramp_sacrifice_lands <= lands]
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
        self._try_pump()

    def take_turn(self) -> None:
        self.turn += 1
        t = self.turn
        self.casts = 0
        self.produced = 0
        self.landfalls = 0
        self.pool = []
        self.pumps = []
        life_before = sum(self.life)
        self._untap()
        if t > 1:
            self._draw(1)
        self._play_land()
        self._produce(fresh=False)
        if self._commander_castable():
            self._stamp("commander")
        self._main_phase()
        self._check_pending_payoffs()
        if self._commander_castable():
            self._stamp("commander")
        if t <= self.cfg.max_turn:
            self.record.mana_by_turn[t] = self.produced
            self.record.idle_by_turn[t] = self.casts == 0
            self._record_board(t)
        if self.produced >= self.cfg.mana_threshold:
            self._stamp("mana_threshold")
        if self.produced >= self.tipping_target:
            self._stamp("tipping_target")
        self._combat()
        dealt = life_before - sum(self.life)
        if t <= self.cfg.max_turn:
            self.record.damage_by_turn[t] = dealt
        self.record.max_swing = max(self.record.max_swing, dealt)
        if any(x <= 0 for x in self.life):
            self._stamp("first_opponent")
        if all(x <= 0 for x in self.life):
            self._stamp("lethal_table")
        if self.record.clocks["lethal_table"] is not None or self.record.clocks["lethal_combo"] is not None:
            self._stamp("win")

    def _combat(self) -> None:
        """Every creature that entered before this turn attacks. The life totals take it greedily, largest attacker
        first; the focused `combat` counter takes all of it."""
        powers = self._attack_powers()
        self.life = self._assign(self.life, powers)
        self.damage += sum(powers)
        if self.damage >= self.cfg.life_per_opponent:
            self._stamp("combat")

    def _record_board(self, t: int) -> None:
        rec = self.record
        counts = dict.fromkeys(rec.tokens_by_turn, 0)
        for (type_, _, _), card in self.token_cards.items():
            counts[type_] += sum(1 for p in self.board if p.card is card)
        for type_, n in counts.items():
            rec.tokens_by_turn[type_][t] = n
        rec.board_power_by_turn[t] = self._board_power()
        rec.lands_by_turn[t] = self._land_count()
        rec.landfall_by_turn[t] = self.landfalls


def play_game(deck: SimDeck, lines: list[SimLine], cfg: SimConfig, rng: random.Random, tipping_target: int) -> GameRecord:
    game = Game(deck, lines, cfg, rng, tipping_target)
    for _ in range(cfg.max_turn):
        game.take_turn()
    return game.record
