from edhpower.config import load_config
from edhpower.sim.mana import ANY_COLOR, COLORLESS
from edhpower.sim.mana import parse_cost
from edhpower.sim.model import build_sim_deck, reduction_applies, sources_of

from .conftest import make_card, sim_facts

CFG = load_config().sim

CARDS = [
    make_card("Zhulodok, Void Gorger", cmc=7.0, mana_cost="{7}", type_line="Legendary Creature — Eldrazi", power="6", toughness="6"),
    make_card("Sol Ring", cmc=1.0, mana_cost="{1}", oracle_text="{T}: Add {C}{C}.", produced_mana=["C"]),
    make_card("Mana Vault", cmc=1.0, mana_cost="{1}", oracle_text="Mana Vault doesn't untap during your untap step.\n{T}: Add {C}{C}{C}.", produced_mana=["C"]),
    make_card("Mox Opal", cmc=0.0, mana_cost="{0}", oracle_text="Metalcraft — {T}: Add one mana of any color. Activate only if you control three or more artifacts.", produced_mana=["W", "U", "B", "R", "G"]),
    make_card("Lotus Petal", cmc=0.0, mana_cost="{0}", oracle_text="{T}, Sacrifice Lotus Petal: Add one mana of any color.", produced_mana=["W", "U", "B", "R", "G"]),
    make_card("Dark Ritual", cmc=1.0, mana_cost="{B}", type_line="Instant", oracle_text="Add {B}{B}{B}.", colors=["B"]),
    make_card("Llanowar Elves", cmc=1.0, mana_cost="{G}", type_line="Creature — Elf Druid", oracle_text="{T}: Add {G}.", power="1", toughness="1", colors=["G"], produced_mana=["G"]),
    make_card("Urza's Incubator", cmc=3.0, mana_cost="{3}", oracle_text="As Urza's Incubator enters, choose a creature type.\nCreature spells of the chosen type cost {2} less to cast."),
    make_card("Rampant Growth", cmc=2.0, mana_cost="{1}{G}", type_line="Sorcery", oracle_text="Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.", colors=["G"]),
    make_card("Demonic Tutor", cmc=2.0, mana_cost="{1}{B}", type_line="Sorcery", oracle_text="Search your library for a card, put that card into your hand, then shuffle.", colors=["B"]),
    make_card("Divination", cmc=3.0, mana_cost="{2}{U}", type_line="Sorcery", oracle_text="Draw two cards.", colors=["U"]),
    make_card("Counterspell", cmc=2.0, mana_cost="{U}{U}", type_line="Instant", oracle_text="Counter target spell.", colors=["U"]),
    make_card("Ulamog, the Ceaseless Hunger", cmc=10.0, mana_cost="{10}", type_line="Legendary Creature — Eldrazi", power="10", toughness="10"),
    make_card("Grizzly Bears", cmc=2.0, mana_cost="{1}{G}", type_line="Creature — Bear", power="2", toughness="2", colors=["G"]),
    make_card("Forsaken Monument", cmc=5.0, mana_cost="{5}", oracle_text="Colorless spells you cast cost {1} less to cast.\nWhenever you tap a permanent for {C}, add an additional {C}."),
    make_card("Unwinding Clock", cmc=4.0, mana_cost="{4}", oracle_text="Untap all artifacts you control during each other player's untap step."),
    make_card("Ancient Tomb", cmc=0.0, mana_cost="", type_line="Land", oracle_text="{T}: Add {C}{C}. Ancient Tomb deals 2 damage to you.", produced_mana=["C"]),
    make_card("City of Traitors", cmc=0.0, mana_cost="", type_line="Land", oracle_text="When you play another land, sacrifice City of Traitors.\n{T}: Add {C}{C}.", produced_mana=["C"]),
    make_card("Forest", cmc=0.0, mana_cost="", type_line="Basic Land — Forest", oracle_text="({T}: Add {G}.)", produced_mana=["G"]),
    make_card("Wastes", cmc=0.0, mana_cost="", type_line="Basic Land", oracle_text="({T}: Add {C}.)", produced_mana=["C"]),
    make_card("Rings of Brighthearth", cmc=3.0, mana_cost="{3}", oracle_text="Whenever you activate an ability, if it isn't a mana ability, you may pay {2}. If you do, copy that ability."),
]
DECK = "1 Zhulodok, Void Gorger\n\n" + "\n".join(f"1 {c['name']}" for c in CARDS[1:] if c["name"] not in ("Forest", "Wastes")) + "\n10 Forest\n10 Wastes\n"
TAGS = {"tutor": ["Demonic Tutor"], "land-ramp": ["Rampant Growth"], "ramp": ["Rampant Growth", "Sol Ring"], "mana-rock": ["Sol Ring"]}


def _deck(tags=TAGS):
    return build_sim_deck(sim_facts(DECK, CARDS, tags), CFG)


def test_roles_are_derived_from_profile_fields_not_names():
    d = _deck()
    roles = {n: c.role for n, c in d.cards.items()}
    assert roles["Sol Ring"] == "rock" and roles["Mana Vault"] == "rock" and roles["Mox Opal"] == "rock"
    assert roles["Lotus Petal"] == "one_shot" and roles["Dark Ritual"] == "one_shot"
    assert roles["Llanowar Elves"] == "dork" and roles["Urza's Incubator"] == "reducer"
    assert roles["Rampant Growth"] == "ramp_spell" and roles["Demonic Tutor"] == "tutor" and roles["Divination"] == "draw_spell"
    assert roles["Counterspell"] == "held" and roles["Ulamog, the Ceaseless Hunger"] == "threat"
    assert roles["Grizzly Bears"] == "creature" and roles["Rings of Brighthearth"] == "permanent"
    assert roles["Forsaken Monument"] == "engine" and roles["Unwinding Clock"] == "engine"
    assert roles["Forest"] == "land" and roles["Ancient Tomb"] == "land"


def test_mana_and_colours_come_from_profile_and_produced_mana():
    d = _deck()
    assert d.cards["Sol Ring"].mana == 2 and d.cards["Sol Ring"].produces == COLORLESS
    assert d.cards["Mana Vault"].mana == 3 and d.cards["Mana Vault"].params == {"untap_cost": 4}
    assert d.cards["Mox Opal"].params == {"requires": "metalcraft"} and d.cards["Mox Opal"].produces == ANY_COLOR
    assert d.cards["Llanowar Elves"].produces == frozenset({"G"})
    assert d.cards["Ancient Tomb"].mana == 2 and d.cards["Forest"].mana == 1 and d.cards["Forest"].produces == frozenset({"G"})
    assert d.cards["City of Traitors"].params == {"sacrifice_on_land_drop": True}
    assert d.cards["Dark Ritual"].mana == 3 and d.cards["Dark Ritual"].produces == frozenset({"B"})
    assert d.cards["Zhulodok, Void Gorger"].power == 6
    assert d.cards["Zhulodok, Void Gorger"].cost.generic == 7


def test_library_excludes_commander_and_counts_copies():
    d = _deck()
    assert len(d.library) == 38 and d.library.count("Forest") == 10 and "Zhulodok, Void Gorger" not in d.library
    assert d.commanders[0].name == "Zhulodok, Void Gorger" and d.commander_subtypes == frozenset({"Eldrazi"})
    assert d.coverage["rock"] == 3 and d.coverage["land"] == 22 and d.coverage["held"] == 1


def test_tag_roles_disappear_when_tags_are_down():
    d = _deck(tags=None)
    assert d.cards["Demonic Tutor"].role == "held" and d.cards["Rampant Growth"].role == "held"
    assert d.cards["Divination"].role == "draw_spell"   # draw_count is extracted, not tag-derived
    assert any("tags unavailable" in n for n in d.notes)


def test_reduction_scopes():
    d = _deck()
    eldrazi, bears, ring = d.cards["Ulamog, the Ceaseless Hunger"], d.cards["Grizzly Bears"], d.cards["Sol Ring"]
    assert reduction_applies("creature spells of the chosen type", eldrazi, frozenset({"Eldrazi"}))
    assert not reduction_applies("creature spells of the chosen type", bears, frozenset({"Eldrazi"}))
    assert reduction_applies("colorless spells you cast", ring, frozenset()) and not reduction_applies("colorless spells you cast", bears, frozenset())
    assert reduction_applies("colorless eldrazi spells you cast", eldrazi, frozenset()) and not reduction_applies("colorless eldrazi spells you cast", ring, frozenset())
    assert reduction_applies("spells you cast", bears, frozenset())
    assert not reduction_applies("spells you cast", d.cards["Forest"], frozenset())


def test_sources_of():
    assert sources_of(("any",), ()) == ANY_COLOR
    assert sources_of(("C",), ("C",)) == COLORLESS
    assert sources_of(("G", "U"), ()) == frozenset({"G", "U"})
    assert sources_of((), ("W", "B")) == frozenset({"W", "B"})
    assert sources_of((), ()) == COLORLESS


# ---------------------------------------------------------------------------------- effects on SimCard
from edhpower.sim.model import token_card  # noqa: E402

from .test_sim_effects import BALOTHS, GRIZZLY_BEARS, RETREAT_TO_HAGRA, SIX  # noqa: E402

_FX_CARDS = [
    make_card("Cmdr", cmc=4.0, mana_cost="{2}{G}{G}", type_line="Legendary Creature — Elf", power="3", toughness="3"),
    make_card("Rampaging Baloths", cmc=6.0, mana_cost="{4}{G}{G}", type_line="Creature — Beast", power="6", toughness="6"),
    make_card("Six", cmc=3.0, mana_cost="{2}{G}", type_line="Legendary Creature — Treefolk", power="2", toughness="4"),
    make_card("Grizzly Bears", cmc=2.0, mana_cost="{1}{G}", type_line="Creature — Bear", power="2", toughness="2"),
    make_card("Retreat to Hagra", cmc=3.0, mana_cost="{2}{B}", type_line="Enchantment"),
    make_card("Mystery", cmc=2.0, mana_cost="{1}{G}", type_line="Creature — Elf", power="1", toughness="1"),
    make_card("Forest", cmc=0.0, mana_cost="", type_line="Basic Land — Forest", produced_mana=["G"]),
]
_FX_DECK = "1 Cmdr\n\n1 Rampaging Baloths\n1 Six\n1 Grizzly Bears\n1 Retreat to Hagra\n1 Mystery\n1 Forest\n"
_FX_SCRIPTS = {"Rampaging Baloths": BALOTHS, "Six": SIX, "Grizzly Bears": GRIZZLY_BEARS, "Retreat to Hagra": RETREAT_TO_HAGRA}


def _fx_deck():
    return build_sim_deck(sim_facts(_FX_DECK, _FX_CARDS, TAGS, scripts=_FX_SCRIPTS), CFG)


def test_effects_ride_on_simcard():
    deck = _fx_deck()
    assert deck.cards["Rampaging Baloths"].effects[0].do == "token"
    assert deck.effects_sources["forge"] == ["Grizzly Bears", "Rampaging Baloths", "Retreat to Hagra", "Six"]
    assert deck.effects_sources["none"] == ["Mystery"]


def test_token_card_shape():
    t = token_card("Beast", 3, 3)
    assert (t.name, t.is_creature, t.role, t.power, t.produces) == ("Beast token", True, "token", 3, frozenset())
    assert t.cost == parse_cost("")


def test_unmodelled_is_exact():
    deck = _fx_deck()
    assert "Six" in deck.unmodelled and "Mystery" in deck.unmodelled
    for n in ("Rampaging Baloths", "Grizzly Bears", "Forest", "Cmdr"):
        assert n not in deck.unmodelled
    assert "Retreat to Hagra" in deck.partial and "Retreat to Hagra" not in deck.unmodelled
    assert deck.unmodelled == tuple(sorted(deck.unmodelled))
    assert any("does not read" in n for n in deck.notes) and any("in part" in n for n in deck.notes)


def test_table_card_is_never_unmodelled():
    from edhpower.profile import SpecialBehaviour
    from edhpower.sim.effects import Effect
    from edhpower.sim import model
    sb = SpecialBehaviour("Six", None, 0, effects=(Effect(on="landfall", do="drain"),))
    orig = model.load_special_behaviours
    model.load_special_behaviours = lambda: {"Six": sb}
    try:
        deck = _fx_deck()
    finally:
        model.load_special_behaviours = orig
    assert "Six" not in deck.unmodelled and "Six" in deck.effects_sources["table"]
