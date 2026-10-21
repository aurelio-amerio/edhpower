"""One goldfish game: on the play, no opponent, colours enforced, driven by SimCard fields."""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from edhpower.config import SimConfig
from edhpower.sim.combos import SimLine, missing_pieces, payoff_ready, pieces_to_cast
from edhpower.sim.effects import Effect, condition_holds
from edhpower.sim.mana import ANY_COLOR, COLORLESS, ActivationCost, ManaCost, Unit, parse_activation_cost, pay
from edhpower.sim.model import SimCard, SimDeck, reduction_applies, token_card

CLOCKS: tuple[str, ...] = ("commander", "mana_threshold", "tipping_target", "threat", "combat", "combo", "lethal_combo",
                           "lethal_table", "first_opponent", "win", "reanimate")
MAIN_ORDER: tuple[str, ...] = ("rock", "dork", "reducer", "ramp_spell", "spell", "draw_spell", "commander", "tutor", "combo",
                               "threat", "creature", "engine", "permanent")
CHEAPEST_FIRST = {"rock", "dork", "reducer", "engine", "permanent", "ramp_spell", "spell", "draw_spell", "tutor"}
ALWAYS_WANTED = {"mill", "token", "counters", "drain"}   # cast effects worth casting whenever the spell is payable
UNTAP_RANK = {"permanents": 3, "artifacts": 2, "one_artifact": 1}

_cost = lru_cache(maxsize=None)(parse_activation_cost)   # effect costs are a handful of strings, parsed in hot loops


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
    graveyard_lands_by_turn: list[int] = field(default_factory=list)   # land cards in the graveyard at end of turn
    distinct_lands_by_turn: list[int] = field(default_factory=list)   # land names on the battlefield at end of turn


class Game:
    def __init__(self, deck: SimDeck, lines: list[SimLine], cfg: SimConfig, rng: random.Random, tipping_target: int) -> None:
        self.deck, self.cards, self.lines, self.cfg, self.rng = deck, deck.cards, lines, cfg, rng
        self.tipping_target = tipping_target
        self.library: list[str] = list(deck.library)
        self.rng.shuffle(self.library)
        self.hand: list[str] = []
        self.board: list[Perm] = []
        self.graveyard: list[str] = []
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
        self.land_drops = 1   # lands that may be played this turn
        self.lands_played = 0   # lands played this turn
        self.dredged = False   # this turn's draw step was replaced by a dredge
        self.token_cards: dict[tuple[str, int, int], SimCard] = {}
        n = cfg.max_turn + 1
        token_types = sorted({e.type for c in deck.cards.values() for top in c.effects for e in (top, top.upgrade)
                              if e is not None and e.do == "token"})
        self.record = GameRecord({k: None for k in CLOCKS}, [0] * n, [False] * n, {k: [0] * n for k in token_types},
                                 [0] * n, [0] * n, [0] * n, [0] * n,
                                 graveyard_lands_by_turn=[0] * n, distinct_lands_by_turn=[0] * n)
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

    def _land_priority(self, c: SimCard, needed: frozenset[str], tapped: bool = False) -> int:
        """How much a land is worth playing now; `tapped`: it enters tapped whatever the card says (a return)."""
        if self._free_fetch(c) is not None and self._basic_in_library() is not None:
            return 3   # a tapped land of a needed colour: it is two landfalls
        enters_tapped = c.enters_tapped or tapped
        if c.params.get("sacrifice_on_land_drop"):
            return 8 if self.turn <= 2 else 1
        if "tron" in c.params:
            have = len(self._tron_names())
            return 9 if have == 2 else 7 if have == 1 else 5
        if c.mana >= 2 and not enters_tapped:
            return 10
        if c.params.get("scales_with") == "creatures":
            return 3 + self._creature_count()
        if c.mana == 0:
            return 4 if self.turn >= 4 else 1
        fixes = bool(c.produces & needed)
        if enters_tapped:
            return 3 if fixes else 2
        return 6 if fixes else 5

    def _static_drops(self) -> int:
        return sum(int(e.n) for p in self.board for e in p.card.effects if e.on == "static" and e.do == "extra_land")

    def _plays_from_graveyard(self) -> bool:
        return any(e.on == "static" and e.do == "play_lands_from_graveyard" for p in self.board for e in p.card.effects)

    def _land_step(self) -> None:
        """Play lands while drops are left: from the hand, else from the graveyard when a permanent allows it, best
        land priority first. A free fetch is cracked after each land, so a replayed fetch uses one drop each time."""
        while self.lands_played < self.land_drops:
            zone, lands = "hand", [n for n in self.hand if self.cards[n].is_land]
            if not lands and self._plays_from_graveyard():
                zone, lands = "graveyard", self._gy_lands()
            if not lands:
                break
            needed = self._needed_colors()
            pick = max(lands, key=lambda n: (self._land_priority(self.cards[n], needed), -lands.index(n)))
            for p in [p for p in self.board if p.card.params.get("sacrifice_on_land_drop")]:
                self._sacrifice(p)
            self._put_land(pick, self.cards[pick].enters_tapped, zone)
            self.lands_played += 1
            self._crack_free_fetches()
        self._crack_free_fetches()

    @staticmethod
    def _free_fetch(c: SimCard) -> Effect | None:
        """The activated fetch of a land that costs no mana and no creature, and is paid by tapping or sacrificing it."""
        if not c.is_land:
            return None
        for e in c.effects:
            if e.on == "activated" and e.do == "fetch":
                cost = _cost(e.cost)
                if not cost.mana.total and not cost.sacrifice_creatures and (cost.tap or cost.sacrifice_self):
                    return e
        return None

    def _crack_free_fetches(self) -> None:
        """Crack every untapped land's free fetch while the library still holds a land it finds."""
        while True:
            found = next(((p, e) for p in self.board if not p.tapped and (e := self._free_fetch(p.card)) is not None), None)
            if found is None or self._basic_in_library() is None or not self._activate(*found):
                return

    def _put_land(self, name: str, tapped: bool, zone: str) -> Perm:
        """Move the land `name` from `zone` ("hand" | "graveyard" | "library") onto the battlefield; it enters (landfall)."""
        {"hand": self.hand, "graveyard": self.graveyard, "library": self.library}[zone].remove(name)
        perm = Perm(self.cards[name], self.turn, tapped=tapped)
        self.board.append(perm)
        self._land_entered(perm)
        return perm

    def _basic_in_library(self) -> int | None:
        """Index of the first 1-mana land in the library (what a land-search spell finds), or None."""
        return next((i for i, n in enumerate(self.library) if self.cards[n].is_land and self.cards[n].mana == 1), None)

    def _fetch_land(self) -> bool:
        idx = self._basic_in_library()
        if idx is None:
            return False
        self._put_land(self.library[idx], True, "library")   # the first copy of a name is the one at idx
        return True

    def _lands_left(self) -> None:
        self.distinct_lands = {p.card.name for p in self.board if p.card.is_land}

    # ---- graveyard -----------------------------------------------------------------------------
    def _gy_lands(self) -> list[str]:
        return [n for n in self.graveyard if self.cards[n].is_land]

    def _to_graveyard(self, name: str) -> None:
        self.graveyard.append(name)

    def _sacrifice(self, perm: Perm) -> None:
        """Board -> graveyard (a token just leaves). A land also updates the distinct names and fires the
        `land_sacrificed` effects of every other permanent on the board; a creature then fires its own `dies` effects."""
        idx = next(i for i, p in enumerate(self.board) if p is perm)
        del self.board[idx]
        if perm.card.role != "token":
            self._to_graveyard(perm.card.name)
        if perm.card.is_land:
            self._lands_left()
            for p, e in self._triggered("land_sacrificed"):
                if p is not perm:
                    self._fire(e, p)
        if perm.card.is_creature:
            for e in perm.card.effects:
                if e.on == "dies":
                    self._fire(e, None)

    def _crackable(self, p: Perm) -> bool:
        """A land whose activated fetch is still worth cracking: it is two landfalls, not one."""
        return self._basic_in_library() is not None and any(e.on == "activated" and e.do == "fetch" for e in p.card.effects)

    def _sacrifice_lands(self, n: int) -> int:
        """Sacrifice `n` lands, lowest land priority first, keeping the last source of a colour that is still wanted
        and an uncracked fetch while another land qualifies. Returns how many were sacrificed."""
        done = 0
        for _ in range(n):
            lands = [p for p in self.board if p.card.is_land]
            if not lands:
                break
            wanted = self._pip_colors((*self.hand, *self.command_zone))
            needed = frozenset(wanted)

            def strands(p: Perm) -> bool:
                others: set[str] = set()
                for q in self.board:
                    if q is not p:
                        others |= q.card.produces
                return bool((p.card.produces & wanted) - others)

            victim = min(lands, key=lambda p: (strands(p), self._crackable(p), self._land_priority(p.card, needed)))
            self._sacrifice(victim)
            done += 1
        return done

    def _mill(self, n: int) -> list[str]:
        """The top `n` cards of the library (its end, as `_draw`) into the graveyard, in that order. When they hold
        a land, every `land_milled` effect of the board fires once (board order) with those lands."""
        out: list[str] = []
        for _ in range(n):
            if not self.library:
                break
            out.append(self.library.pop())
            self._to_graveyard(out[-1])
        lands = tuple(name for name in out if self.cards[name].is_land)
        if lands:
            for p, e in self._triggered("land_milled"):
                self._fire(e, p, milled=lands)
        return out

    def _best_gy_land(self, tapped: bool) -> str:
        needed = self._needed_colors()
        gy = self._gy_lands()
        return max(gy, key=lambda n: (self._land_priority(self.cards[n], needed, tapped), -gy.index(n)))

    def _return_lands(self, n: int | str) -> int:
        """Graveyard lands onto the battlefield tapped, one at a time, best land priority first; "all" = every one."""
        count = 0
        while self._gy_lands() and (n == "all" or count < int(n)):
            self._put_land(self._best_gy_land(True), True, "graveyard")
            count += 1
        return count

    def _return_lands_to_hand(self, n: int) -> int:
        count = 0
        while self._gy_lands() and count < n:
            name = self._best_gy_land(False)
            self.graveyard.remove(name)
            self.hand.append(name)
            count += 1
        return count

    # ---- draws and dredge --------------------------------------------------------------------------
    def _hand_lands(self) -> int:
        return sum(1 for n in self.hand if self.cards[n].is_land)

    def _dredge_choice(self, want_land: bool) -> tuple[str, int] | None:
        """The graveyard card to return to hand instead of a draw, and how many cards that mills; None to draw.
        Only when a land is wanted: first a land through a permanent that gives graveyard lands dredge, then a card
        with its own dredge that would be cast now. A dredge is only possible with at least n cards in the library."""
        if not want_land:
            return None
        left = len(self.library)
        land_n = max((int(e.n) for p in self.board for e in p.card.effects
                      if e.on == "static" and e.do == "dredge" and e.type == "lands"), default=0)
        if land_n and left >= land_n and self._gy_lands():
            return self._best_gy_land(False), land_n
        for name in self.graveyard:
            c = self.cards[name]
            if c.role != "spell":
                continue
            n = max((int(e.n) for e in c.effects if e.on == "static" and e.do == "dredge" and not e.type), default=0)
            if n and left >= n and self._spell_wanted(c):
                return name, n
        return None

    def _dredge(self, choice: tuple[str, int]) -> None:
        name, n = choice
        self.graveyard.remove(name)
        self.hand.append(name)
        self._mill(n)

    def _draw_step(self) -> None:
        """The turn's draw, replaced by a dredge when the hand holds fewer lands than this turn's drops."""
        choice = self._dredge_choice(self._hand_lands() < self.land_drops)
        if choice is None:
            self._draw(1)
            return
        self._dredge(choice)
        self.dredged = True

    def _chain_lands(self) -> None:
        """Each land in hand onto the battlefield tapped, best first, without using a drop, with a draw (or a land
        dredge) after each; until the hand holds no land, at most `chain_cap` lands."""
        for _ in range(self.cfg.chain_cap):
            lands = [n for n in self.hand if self.cards[n].is_land]
            if not lands:
                return
            needed = self._needed_colors()
            pick = max(lands, key=lambda n: (self._land_priority(self.cards[n], needed, True), -lands.index(n)))
            self._put_land(pick, True, "hand")
            choice = self._dredge_choice(want_land=True)
            if choice is None:
                self._draw(1)
            else:
                self._dredge(choice)

    def _activate(self, perm: Perm, e: Effect) -> bool:
        """Pay the whole cost of `perm`'s activated `e` (mana from the pool, tap, sacrifices), then fire it.
        False, with nothing paid, when any part cannot be paid."""
        cost = _cost(e.cost)
        if cost.tap and (perm.tapped or (perm.card.is_creature and perm.entered >= self.turn)):
            return False
        left = pay(cost.mana, self.pool) if cost.mana.total else self.pool
        if left is None or not self._pay_additional(cost, perm):
            return False
        self.pool = left
        if cost.tap:
            perm.tapped = True
        self._fire(e, perm)
        return True

    def _mass_return_wanted(self) -> bool:
        """Return every graveyard land now: enough of them and a landfall payoff, or the game is nearly over."""
        gy = len(self._gy_lands())
        return gy >= 1 and ((gy >= self.cfg.mass_return_min_lands and bool(self._triggered("landfall")))
                            or self.turn >= self.cfg.max_turn - 1)

    def _try_activated(self) -> bool:
        """Activate the first board ability whose policy holds and whose cost is payable."""
        for p in list(self.board):
            for e in p.card.effects:
                if e.on != "activated":
                    continue
                if e.do == "fetch":
                    wanted = self._basic_in_library() is not None
                elif e.do == "return_lands":
                    wanted = self._mass_return_wanted()
                elif e.do == "draw":
                    wanted = not self.hand
                else:
                    continue
                if wanted and self._activate(p, e):
                    return True
        return False

    def _upkeep(self) -> None:
        """Upkeep effects of board permanents, board order. A land sacrifice that cannot be paid sacrifices the source."""
        for p, e in self._triggered("upkeep"):
            if not any(q is p for q in self.board):
                continue
            if e.do == "sacrifice_land":
                n = int(e.n)
                if self._land_count() >= n:
                    self._sacrifice_lands(n)
                else:
                    self._sacrifice(p)
            else:
                self._fire(e, p)

    def _can_pay_additional(self, cost: ActivationCost, source: Perm | None) -> bool:
        """Whether `_pay_additional` would pay: the source is on the board for a self-sacrifice, and enough other
        lands and creatures remain for the land and creature sacrifices."""
        on_board = source is not None and any(p is source for p in self.board)
        if cost.sacrifice_self and not on_board:
            return False
        others = [p for p in self.board if not (cost.sacrifice_self and p is source)]
        return (sum(1 for p in others if p.card.is_land) >= cost.sacrifice_lands
                and sum(1 for p in others if p.card.is_creature) >= cost.sacrifice_creatures)

    def _pay_additional(self, cost: ActivationCost, source: Perm | None) -> bool:
        """Pay the non-mana parts of an effect's cost: sacrifice the source itself, then creatures, then lands.
        False, with nothing sacrificed, when any part cannot be paid."""
        if not self._can_pay_additional(cost, source):
            return False
        if cost.sacrifice_self and source is not None:
            self._sacrifice(source)
        if cost.sacrifice_creatures and not self._pay_sacrifice_creatures(cost.sacrifice_creatures):
            return False   # unreachable: counted above, and a dies trigger only adds lands
        if cost.sacrifice_lands:
            self._sacrifice_lands(cost.sacrifice_lands)
        return True

    def _pay_sacrifice_creatures(self, n: int) -> bool:
        """Sacrifice `n` creatures, one at a time: a nontoken creature whose `dies` effect returns lands while the
        graveyard holds one, else the lowest-power token, else the lowest-power nontoken creature (board order on
        ties). False, with nothing sacrificed, when fewer than `n` creatures are on the board."""
        if self._creature_count() < n:
            return False
        for _ in range(n):
            creatures = [p for p in self.board if p.card.is_creature]
            if not creatures:
                return False
            gy_lands = bool(self._gy_lands())
            victim = next((p for p in creatures if gy_lands and p.card.role != "token"
                           and any(e.on == "dies" and e.do == "return_lands" for e in p.card.effects)), None)
            if victim is None:
                victim = min(creatures, key=lambda p: (p.card.role != "token", p.card.power + p.counters))
            self._sacrifice(victim)
        return True

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

    def _fire(self, effect: Effect, source: Perm | None, milled: tuple[str, ...] = ()) -> None:
        """Resolve one effect. `source` is the permanent it belongs to (None for a spell or a dies effect);
        `milled` the lands of the mill that fired a `land_milled` effect."""
        e = self._applicable(effect)
        if e is None:
            return
        if e.do == "token":
            self._create_tokens(e)
            return
        if e.do == "return_lands":
            if e.n == "milled":
                for name in milled:
                    if name in self.graveyard:
                        self._put_land(name, True, "graveyard")
            else:
                self._return_lands(e.n)
            return
        if e.do in ("fetch", "draw", "reanimate") and e.cost and e.on != "activated":   # an activation pays its whole cost before firing
            cost = _cost(e.cost)
            # a spell's Cost$ holds its own mana cost, paid when it was cast
            left = pay(cost.mana, self.pool) if cost.mana.total and e.on != "cast" else self.pool
            if left is None or not self._pay_additional(cost, source):
                return
            self.pool = left
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
        elif e.do == "mill":
            self._mill(n)
        elif e.do == "return_lands_to_hand":
            self._return_lands_to_hand(n)
        elif e.do == "fetch":
            for _ in range(n):
                if not self._fetch_land():
                    break
        elif e.do == "chain_lands_from_hand":
            self._chain_lands()
        elif e.do == "draw":
            self._draw(n)   # a plain draw, never a dredge
        elif e.do == "reanimate":
            for _ in range(n):
                target = self._reanimate_target(e.type, e.mv_max, threshold=False)
                if target is None:
                    break
                self._reanimate(target)
        elif e.do == "extra_land":
            self.land_drops += n
            self._land_step()
            self._produce(fresh=False)   # the new land taps for mana this turn
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
        if c.role == "one_shot" and not c.is_spell:
            self._add_units(c.produces, c.mana, False)
            return
        if c.is_spell:
            if c.role == "one_shot":
                self._add_units(c.produces, c.mana, False)
            elif c.role == "ramp_spell":
                self._sacrifice_lands(c.ramp_sacrifice_lands)
                for _ in range(c.ramp_to_battlefield):
                    self._fetch_land()
                for _ in range(c.ramp_to_hand):
                    idx = self._basic_in_library()
                    if idx is None:
                        break
                    self.hand.append(self.library.pop(idx))
            elif c.role == "draw_spell":
                self._draw(c.draw)
            for e in c.effects:
                if e.on == "cast" and e.do != "pump":   # pumps fire from _try_pump only
                    self._fire(e, None)
            self._to_graveyard(name)
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

    def _reanimate_target(self, type_: str, mv_max: int, threshold: bool) -> str | None:
        """The graveyard card a reanimation returns: a creature card ("creature") or any permanent card, lands
        included ("permanent"), of mana value at most `mv_max` (0: no cap); with `threshold`, only one worth a
        spell (MV >= threat_mv or power >= reanimate_min_power). Highest MV first, ties by name."""
        best: str | None = None
        for name in self.graveyard:
            c = self.cards[name]
            if not (c.is_creature if type_ == "creature" else not c.is_spell):
                continue
            if mv_max > 0 and c.cmc > mv_max:
                continue
            if threshold and not (c.cmc >= self.cfg.threat_mv or c.power >= self.cfg.reanimate_min_power):
                continue
            if best is None or (-c.cmc, name) < (-self.cards[best].cmc, best):
                best = name
        return best

    def _reanimate(self, name: str) -> None:
        """Graveyard -> battlefield. A land enters tapped (landfall); anything else enters this turn and fires its
        enters effects. A creature stamps the `reanimate` clock."""
        c = self.cards[name]
        if c.is_creature:
            self._stamp("reanimate")
        if c.is_land:
            self._put_land(name, True, "graveyard")
            return
        self.graveyard.remove(name)
        perm = Perm(c, self.turn)
        self.board.append(perm)
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

    def _spell_wanted(self, c: SimCard) -> bool:
        """Cast this `spell` now: some applied non-pump cast effect of it is worth it on this board."""
        for effect in c.effects:
            if effect.on != "cast" or effect.do == "pump":
                continue
            e = self._applicable(effect)
            if e is None:
                continue
            if e.do in ALWAYS_WANTED:
                return True
            if e.do == "return_lands":
                if self._mass_return_wanted():
                    return True
            elif e.do == "return_lands_to_hand":
                if self._gy_lands() and self._hand_lands() < 1 + self._static_drops():
                    return True
            elif e.do == "extra_land":
                if self.lands_played >= self.land_drops and any(self.cards[n].is_land for n in self.hand):
                    return True
            elif e.do == "reanimate":
                if (self._reanimate_target(e.type, e.mv_max, threshold=True) is not None
                        and self._can_pay_additional(_cost(e.cost), None)):
                    return True
        return False

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
                          for m in self.hand if m != n and self.cards[m].role not in ("held", "land", "one_shot")
                          and (self.cards[m].role != "spell" or self._spell_wanted(self.cards[m])))
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
        elif role == "spell":
            names = [n for n in names if self._spell_wanted(self.cards[n])]
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
            if not progressed:
                progressed = self._try_activated()
        self._try_pump()

    def take_turn(self) -> None:
        self.turn += 1
        t = self.turn
        self.casts = 0
        self.produced = 0
        self.landfalls = 0
        self.lands_played = 0
        self.dredged = False
        self.pool = []
        self.pumps = []
        life_before = sum(self.life)
        self._untap()
        self._upkeep()
        self.land_drops = 1 + self._static_drops()
        if t > 1:   # turn 1's hand is the opening hand
            self._draw_step()
        self._land_step()
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
        rec.graveyard_lands_by_turn[t] = len(self._gy_lands())
        rec.distinct_lands_by_turn[t] = len(self.distinct_lands)


def play_game(deck: SimDeck, lines: list[SimLine], cfg: SimConfig, rng: random.Random, tipping_target: int) -> GameRecord:
    game = Game(deck, lines, cfg, rng, tipping_target)
    for _ in range(cfg.max_turn):
        game.take_turn()
    return game.record
