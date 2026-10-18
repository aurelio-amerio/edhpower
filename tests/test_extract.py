import pytest

from edhpower.extract import OracleNumbers, extract


@pytest.mark.parametrize("text,type_line,mana,colors,repeatable,dependent", [
    ("{T}: Add {C}{C}.", "Artifact", 2, ("C",), True, False),
    ("({T}: Add {G}.)", "Basic Land — Forest", 1, ("G",), True, False),
    ("{T}: Add {C}{C}. Ancient Tomb deals 2 damage to you.", "Land", 2, ("C",), True, False),
    ("{T}: Add {C}.\n{T}: Add {C}{C}. Spend this mana only to cast colorless Eldrazi spells or activate abilities of colorless Eldrazi.", "Land", 2, ("C",), True, False),
    ("Add {B}{B}{B}.", "Instant", 3, ("B",), False, False),
    ("{T}: Add one mana of any color.", "Artifact", 1, ("any",), True, False),
    ("{T}, Sacrifice Jeweled Lotus: Add three mana of any one color. Spend this mana only to cast your commander or to activate abilities of your commander.", "Artifact", 3, ("any",), False, False),
    ("Imprint — When Chrome Mox enters, you may exile a nonartifact, nonland card from your hand.\n{T}: Add one mana of any of the exiled card's colors.", "Artifact", 1, ("any",), True, False),
    ("Multikicker {2}\nEverflowing Chalice enters with a charge counter on it for each time it was kicked.\n{T}: Add {C} for each charge counter on Everflowing Chalice.", "Artifact", 0, (), False, True),
    ("{T}: Add {G} for each creature you control.", "Legendary Land", 0, (), False, True),
    ("{T}: Add {C}{C}{C}.\nMana Vault doesn't untap during your untap step.", "Artifact", 3, ("C",), True, False),
    ("{T}: Add {G/U}.", "Land", 1, ("G", "U"), True, False),
    ("Flying", "Creature — Bird", 0, (), False, False),
    ("Whenever enchanted land is tapped for mana, its controller adds an additional {G}.", "Enchantment — Aura", 0, (), False, False),
    ("At the beginning of your upkeep, add a +1/+1 counter.", "Enchantment", 0, (), False, False),
    ("{T}: Add {W} or {U}.", "Land", 1, ("U", "W"), True, False),
    ("{T}: Add {R}, {G}, or {W}.", "Land", 1, ("G", "R", "W"), True, False),
    ("{T}: Add {B}{B} or {U}{U}.", "Land", 2, ("B", "U"), True, False),
])
def test_mana_extraction(text, type_line, mana, colors, repeatable, dependent):
    n = extract(text, type_line)
    assert (n.mana_per_activation, n.mana_colors, n.repeatable, n.board_dependent) == (mana, colors, repeatable, dependent)


@pytest.mark.parametrize("text,amount,scope", [
    ("Colorless Eldrazi spells you cast cost {2} less to cast.\n{7}, {T}: Search your library for a colorless creature card.", 2, "colorless eldrazi spells you cast"),
    ("Colorless spells you cast cost {1} less to cast.", 1, "colorless spells you cast"),
    ("As Urza's Incubator enters, choose a creature type.\nCreature spells of the chosen type cost {2} less to cast.", 2, "creature spells of the chosen type"),
    ("Flash", 0, ""),
])
def test_cost_reduction(text, amount, scope):
    n = extract(text, "Artifact")
    assert (n.cost_reduction, n.cost_reduction_scope) == (amount, scope)


@pytest.mark.parametrize("text,draw", [
    ("Draw a card.", 1),
    ("Draw two cards, then discard a card.", 2),
    ("Whenever you cast a colorless creature spell with mana value 7 or greater, draw three cards.", 3),
    ("Target player draws X cards.", 0),
    ("Flying", 0),
    ("Draw a card for each artifact you control.", 0),
])
def test_draw_count(text, draw):
    assert extract(text, "Sorcery").draw_count == draw


@pytest.mark.parametrize("text,tapped", [
    ("Ketria Triome enters tapped.\nCycling {3}", True),
    ("This land enters tapped unless you control two or more basic lands.", False),
    ("Shivan Reef enters the battlefield tapped.", True),
    ("{T}: Add {C}.", False),
])
def test_enters_tapped(text, tapped):
    assert extract(text, "Land").enters_tapped is tapped


def test_empty_text_is_all_zero():
    assert extract("", "") == OracleNumbers(0, (), False, False, 0, "", 0, False)


def test_triggered_add_clause_is_not_a_mana_ability():
    wild_growth = "Enchant land\nWhenever enchanted land is tapped for mana, its controller adds an additional {G}."
    n = extract(wild_growth, "Enchantment — Aura")
    assert n.mana_per_activation == 0 and n.mana_colors == () and n.repeatable is False

    monument = "Colorless spells you cast cost {1} less to cast.\nWhenever you tap a permanent for {C}, add an additional {C}."
    n = extract(monument, "Legendary Artifact")
    assert n.mana_per_activation == 0
    assert n.cost_reduction == 1

    kinnan = "Whenever you tap a nonland permanent for mana, add one mana of any type that permanent produced.\n{5}{G}{U}: Look at the top five cards."
    assert extract(kinnan, "Legendary Creature — Human Druid").mana_per_activation == 0


def test_activated_add_clause_still_counts_next_to_a_trigger():
    text = "{T}: Add one mana of any color.\nWhenever a creature dies, add {C}."
    n = extract(text, "Land")
    assert n.mana_per_activation == 1 and n.mana_colors == ("any",) and n.repeatable is True
