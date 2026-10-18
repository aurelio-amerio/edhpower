import pytest

from edhpower.sim.mana import ANY_COLOR, COLORLESS, ManaCost, Pip, can_pay, parse_cost, pay

G, U, W = frozenset({"G"}), frozenset({"U"}), frozenset({"W"})


def test_parse_generic_colour_and_x():
    c = parse_cost("{2}{G}{G}")
    assert c.generic == 2 and c.pips == (Pip(G), Pip(G)) and c.total == 4
    assert parse_cost("{X}{R}") == ManaCost(0, (Pip(frozenset({"R"})),))
    assert parse_cost("") == ManaCost(0, ()) and parse_cost("{S}{S}").generic == 2


def test_parse_colorless_hybrid_phyrexian_and_twobrid():
    assert parse_cost("{8}{C}{C}").pips == (Pip(COLORLESS), Pip(COLORLESS))
    ulalek = parse_cost("{C/W}{C/U}{C/B}{C/R}{C/G}")
    assert ulalek.generic == 0 and ulalek.pips[0] == Pip(frozenset({"C", "W"})) and len(ulalek.pips) == 5
    assert parse_cost("{G/P}").pips == (Pip(G, free=True),)
    assert parse_cost("{2/W}").pips == (Pip(W, generic=2),)


def test_pay_prefers_the_least_flexible_unit():
    left = pay(parse_cost("{G}"), [ANY_COLOR, G])
    assert left == [ANY_COLOR]


def test_colorless_pip_needs_a_colorless_source():
    assert not can_pay(parse_cost("{C}"), [ANY_COLOR, G])
    assert can_pay(parse_cost("{C}"), [COLORLESS])
    assert can_pay(parse_cost("{1}"), [ANY_COLOR]) and can_pay(parse_cost("{1}"), [COLORLESS])


def test_hybrid_takes_either_side_and_ulalek_is_castable_off_five_colorless():
    assert can_pay(parse_cost("{C/W}{C/U}{C/B}{C/R}{C/G}"), [COLORLESS] * 5)
    assert can_pay(parse_cost("{C/W}{C/U}{C/B}{C/R}{C/G}"), [ANY_COLOR] * 5)
    assert not can_pay(parse_cost("{C/W}{C/U}{C/B}{C/R}{C/G}"), [COLORLESS] * 4)


def test_phyrexian_is_free_and_twobrid_falls_back_to_generic():
    assert can_pay(parse_cost("{G/P}"), [])
    assert can_pay(parse_cost("{2/W}"), [COLORLESS, COLORLESS])
    assert not can_pay(parse_cost("{2/W}"), [COLORLESS])
    assert pay(parse_cost("{2/W}"), [W, COLORLESS]) == [COLORLESS]


def test_reduction_applies_to_generic_only():
    assert can_pay(parse_cost("{8}{C}{C}"), [COLORLESS] * 4, reduction=6)
    assert not can_pay(parse_cost("{8}{C}{C}"), [ANY_COLOR] * 10, reduction=8)
    assert can_pay(parse_cost("{1}"), [], reduction=5)


def test_phyrexian_pips_never_consume_a_mana_unit():
    # {W/P} is payable with 2 life, so the {W} unit must stay available for the generic part.
    assert pay(parse_cost("{1}{W/P}"), [W]) == []
    assert pay(parse_cost("{1}{G/P}"), [G]) == []
    assert pay(parse_cost("{3}{U/P}"), [U, COLORLESS, COLORLESS]) == []
    # A Phyrexian-only cost needs no mana at all, and leaves any pool untouched.
    assert pay(parse_cost("{W/P}{W/P}"), []) == []
    assert pay(parse_cost("{G/P}"), [G, ANY_COLOR]) == [G, ANY_COLOR]
