"""sim/effects.py: Effect records from Forge card scripts (pinned commit) and from the behaviours table.

Script constants are pasted verbatim from Card-Forge commit 33aecdd6adac36a42af9eab75d2e654626a0e7db,
forge-gui/res/cardsfolder/<initial>/<slug>.txt; OPP_LANDFALL is the one hand-edited script.
"""

from __future__ import annotations

import pytest

from edhpower.profile import SpecialBehaviour
from edhpower.scryfall import CardData
from edhpower.sim.effects import CardEffects, Effect, condition_holds, effects_for, parse_effects_table, parse_script

from .conftest import make_card

NECROBLOOM = r"""Name:The Necrobloom
ManaCost:1 W B G
Types:Legendary Creature Plant
PT:2/7
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Land.YouCtrl | Execute$ TrigBranch | TriggerZones$ Battlefield | TriggerDescription$ Landfall — Whenever a land you control enters, create a 0/1 green Plant creature token. If you control seven or more lands with different names, create a 2/2 black Zombie creature token instead.
SVar:TrigBranch:DB$ Branch | BranchConditionSVar$ X | BranchConditionSVarCompare$ GE7 | TrueSubAbility$ DBZombie | FalseSubAbility$ DBPlant
SVar:DBPlant:DB$ Token | TokenScript$ g_0_1_plant | TokenOwner$ You
SVar:DBZombie:DB$ Token | TokenScript$ b_2_2_zombie | TokenOwner$ You
SVar:X:Count$Valid Land.YouCtrl$DifferentCardNames
S:Mode$ Continuous | AffectedZone$ Graveyard | Affected$ Land.YouOwn | AddKeyword$ Dredge:2 | Description$ Land cards in your graveyard have dredge 2. (You may return a land card from your graveyard to your hand and mill two cards instead of drawing a card.)
DeckHas:Ability$Token & Type$Zombie
DeckHints:Ability$Mill
Oracle:Landfall — Whenever a land you control enters, create a 0/1 green Plant creature token. If you control seven or more lands with different names, create a 2/2 black Zombie creature token instead.\nLand cards in your graveyard have dredge 2. (You may return a land card from your graveyard to your hand and mill two cards instead of drawing a card.)
"""

AVENGER = r"""Name:Avenger of Zendikar
ManaCost:5 G G
Types:Creature Elemental
PT:5/5
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Card.Self | Execute$ TrigToken | TriggerDescription$ When CARDNAME enters, create a 0/1 green Plant creature token for each land you control.
SVar:TrigToken:DB$ Token | TokenAmount$ X | TokenScript$ g_0_1_plant | TokenOwner$ You
SVar:X:Count$Valid Land.YouCtrl
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Land.YouCtrl | TriggerZones$ Battlefield | Execute$ TrigPutCounterAll | OptionalDecider$ You | TriggerDescription$ Landfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control.
SVar:TrigPutCounterAll:DB$ PutCounterAll | ValidCards$ Creature.Plant+YouCtrl | CounterType$ P1P1 | CounterNum$ 1 | AILogic$ Always
SVar:BuffedBy:Land
Oracle:When Avenger of Zendikar enters, create a 0/1 green Plant creature token for each land you control.\nLandfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control.
"""

BALOTHS = r"""Name:Rampaging Baloths
ManaCost:4 G G
Types:Creature Beast
PT:6/6
K:Trample
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Land.YouCtrl | TriggerZones$ Battlefield | Execute$ TrigToken | TriggerDescription$ Landfall — Whenever a land you control enters, create a 4/4 green Beast creature token.
SVar:TrigToken:DB$ Token | TokenScript$ g_4_4_beast | TokenOwner$ You
Oracle:Trample\nLandfall — Whenever a land you control enters, create a 4/4 green Beast creature token.
"""

FELIDAR_RETREAT = r"""Name:Felidar Retreat
ManaCost:3 W
Types:Enchantment
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | TriggerZones$ Battlefield | ValidCard$ Land.YouCtrl | Execute$ TrigCharm | TriggerDescription$ Landfall — Whenever a land you control enters, ABILITY
SVar:TrigCharm:DB$ Charm | Choices$ DBToken,DBPutCounterAll
SVar:DBToken:DB$ Token | TokenScript$ w_2_2_cat_beast | TokenOwner$ You | SpellDescription$ Create a 2/2 white Cat Beast creature token.
SVar:DBPutCounterAll:DB$ PutCounterAll | ValidCards$ Creature.YouCtrl | CounterType$ P1P1 | CounterNum$ 1 | SubAbility$ DBPumpAll | SpellDescription$ Put a +1/+1 counter on each creature you control. Those creatures gain vigilance until end of turn.
SVar:DBPumpAll:DB$ PumpAll | ValidCards$ Creature.YouCtrl | KW$ Vigilance
SVar:BuffedBy:Land
DeckHas:Ability$Token|Counters
Oracle:Landfall — Whenever a land you control enters, choose one —\n• Create a 2/2 white Cat Beast creature token.\n• Put a +1/+1 counter on each creature you control. Those creatures gain vigilance until end of turn.
"""

SCUTE_SWARM = r"""Name:Scute Swarm
ManaCost:2 G
Types:Creature Insect
PT:1/1
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Land.YouCtrl | TriggerZones$ Battlefield | Execute$ TrigBranch | TriggerDescription$ Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, create a token that's a copy of CARDNAME instead.
SVar:TrigBranch:DB$ Branch | BranchConditionSVar$ X | BranchConditionSVarCompare$ GE6 | TrueSubAbility$ DBCopy | FalseSubAbility$ DBToken
SVar:DBToken:DB$ Token | TokenScript$ g_1_1_insect | TokenOwner$ You
SVar:DBCopy:DB$ CopyPermanent | Defined$ Self
SVar:X:Count$Valid Land.YouCtrl
SVar:BuffedBy:Land
DeckHas:Ability$Token
Oracle:Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, create a token that's a copy of Scute Swarm instead.
"""

INTANGIBLE_VIRTUE = r"""Name:Intangible Virtue
ManaCost:1 W
Types:Enchantment
S:Mode$ Continuous | Affected$ Creature.token+YouCtrl | AddPower$ 1 | AddToughness$ 1 | AddKeyword$ Vigilance | Description$ Creature tokens you control get +1/+1 and have vigilance.
SVar:PlayMain1:TRUE
AI:RemoveDeck:Random
Oracle:Creature tokens you control get +1/+1 and have vigilance.
"""

OVERRUN = r"""Name:Overrun
ManaCost:2 G G G
Types:Sorcery
A:SP$ PumpAll | ValidCards$ Creature.YouCtrl | NumAtt$ +3 | NumDef$ +3 | KW$ Trample | SpellDescription$ Creatures you control get +3/+3 and gain trample until end of turn.
Oracle:Creatures you control get +3/+3 and gain trample until end of turn.
"""

LOTUS_COBRA = r"""Name:Lotus Cobra
ManaCost:1 G
Types:Creature Snake
PT:2/1
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Land.YouCtrl | TriggerZones$ Battlefield | Execute$ TrigMana | TriggerDescription$ Landfall — Whenever a land you control enters, add one mana of any color.
SVar:TrigMana:DB$ Mana | Produced$ Any
Oracle:Landfall — Whenever a land you control enters, add one mana of any color.
"""

RETREAT_TO_HAGRA = r"""Name:Retreat to Hagra
ManaCost:2 B
Types:Enchantment
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | TriggerZones$ Battlefield | ValidCard$ Land.YouCtrl | Execute$ TrigCharm | TriggerDescription$ Landfall — Whenever a land you control enters, ABILITY
SVar:TrigCharm:DB$ Charm | Choices$ DBPump,DBLoseLife
SVar:DBPump:DB$ Pump | ValidTgts$ Creature | NumAtt$ +1 | KW$ Deathtouch | SpellDescription$ Target creature gets +1/+0 and gains deathtouch until end of turn.
SVar:DBLoseLife:DB$ LoseLife | Defined$ Player.Opponent | LifeAmount$ 1 | SubAbility$ DBGainLife | SpellDescription$ Each opponent loses 1 life and you gain 1 life.
SVar:DBGainLife:DB$ GainLife | Defined$ You | LifeAmount$ 1
DeckHas:Ability$LifeGain
Oracle:Landfall — Whenever a land you control enters, choose one —\n• Target creature gets +1/+0 and gains deathtouch until end of turn.\n• Each opponent loses 1 life and you gain 1 life.
"""

HARROW = r"""Name:Harrow
ManaCost:2 G
Types:Instant
A:SP$ ChangeZone | Cost$ 2 G Sac<1/Land> | Origin$ Library | Destination$ Battlefield | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | ChangeNum$ 2 | SpellDescription$ Search your library for up to two basic land cards, put them onto the battlefield, then shuffle.
SVar:AIPreference:SacCost$Land.Basic
Oracle:As an additional cost to cast this spell, sacrifice a land.\nSearch your library for up to two basic land cards, put them onto the battlefield, then shuffle.
"""

CULTIVATE = r"""Name:Cultivate
ManaCost:2 G
Types:Sorcery
A:SP$ ChangeZone | Origin$ Library | Destination$ Library | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | ChangeNum$ 2 | RememberChanged$ True | Reveal$ True | Shuffle$ False | StackDescription$ SpellDescription | SubAbility$ DBChangeZone1 | SpellDescription$ Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.
SVar:DBChangeZone1:DB$ ChangeZone | Origin$ Library | Destination$ Battlefield | ChangeType$ Land.IsRemembered | ChangeNum$ 1 | Mandatory$ True | NoLooking$ True | SelectPrompt$ Select a card to put onto the battlefield | Tapped$ True | Shuffle$ False | SubAbility$ DBChangeZone2 | StackDescription$ None
SVar:DBChangeZone2:DB$ ChangeZone | Origin$ Library | Destination$ Hand | ChangeType$ Land.IsRemembered | Mandatory$ True | NoLooking$ True | SelectPrompt$ Select a card to put into your hand | StackDescription$ None | SubAbility$ DBCleanup
SVar:DBCleanup:DB$ Cleanup | ClearRemembered$ True
Oracle:Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.
"""

RAMPANT_GROWTH = r"""Name:Rampant Growth
ManaCost:1 G
Types:Sorcery
A:SP$ ChangeZone | Origin$ Library | Destination$ Battlefield | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | Tapped$ True | ChangeNum$ 1 | StackDescription$ Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle. | SpellDescription$ Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.
Oracle:Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.
"""

MIRKWOOD_BATS = r"""Name:Mirkwood Bats
ManaCost:3 B
Types:Creature Bat
PT:2/3
K:Flying
T:Mode$ TokenCreated | ValidPlayer$ You | ValidToken$ Card.token+YouCtrl | Execute$ TrigLoseLife | TriggerZones$ Battlefield | TriggerDescription$ Whenever you create or sacrifice a token, each opponent loses 1 life.
T:Mode$ Sacrificed | ValidCard$ Card.token+YouCtrl | Execute$ TrigLoseLife | TriggerZones$ Battlefield | Secondary$ True | TriggerDescription$ Whenever you create or sacrifice a token, each opponent loses 1 life.
SVar:TrigLoseLife:DB$ LoseLife | LifeAmount$ 1 | Defined$ Opponent
DeckNeeds:Ability$Token
DeckHints:Ability$Sacrifice
Oracle:Flying\nWhenever you create or sacrifice a token, each opponent loses 1 life.
"""

SIX = r"""Name:Six
ManaCost:2 G
Types:Legendary Creature Treefolk
PT:2/4
K:Reach
T:Mode$ Attacks | ValidCard$ Card.Self | Execute$ TrigMill | TriggerZones$ Battlefield | TriggerDescription$ Whenever CARDNAME attacks, mill three cards. You may put a land card from among them into your hand.
SVar:TrigMill:DB$ Mill | NumCards$ 3 | Defined$ You | RememberMilled$ True | SubAbility$ DBChangeZone
SVar:DBChangeZone:DB$ ChangeZone | Hidden$ True | Origin$ Graveyard,Exile | Destination$ Hand | ChangeType$ Land.IsRemembered | Optional$ True | SelectPrompt$ You may select a land card milled this way | SubAbility$ DBCleanup
SVar:DBCleanup:DB$ Cleanup | ClearRemembered$ True
S:Mode$ Continuous | AffectedZone$ Graveyard | Affected$ Card.nonLand+Permanent+YouOwn | Condition$ PlayerTurn | AddKeyword$ Retrace | Description$ During your turn, nonland permanent cards in your graveyard have retrace.
SVar:HasAttackEffect:TRUE
DeckHas:Ability$Graveyard|Mill
Oracle:Reach\nWhenever Six attacks, mill three cards. You may put a land card from among them into your hand.\nDuring your turn, nonland permanent cards in your graveyard have retrace.
"""

GRIZZLY_BEARS = r"""Name:Grizzly Bears
ManaCost:1 G
Types:Creature Bear
PT:2/2
Oracle:
"""

EMERIA_ANGEL = r"""Name:Emeria Angel
ManaCost:2 W W
Types:Creature Angel
PT:3/3
K:Flying
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Land.YouCtrl | TriggerZones$ Battlefield | Execute$ TrigToken | OptionalDecider$ You | TriggerDescription$ Landfall — Whenever a land you control enters, you may create a 1/1 white Bird creature token with flying.
SVar:TrigToken:DB$ Token | TokenScript$ w_1_1_bird_flying | TokenOwner$ You
Oracle:Flying\nLandfall — Whenever a land you control enters, you may create a 1/1 white Bird creature token with flying.
"""

DOUBLING_SEASON = r"""Name:Doubling Season
ManaCost:4 G
Types:Enchantment
R:Event$ CreateToken | ActiveZones$ Battlefield | ValidToken$ Card.YouCtrl | ReplaceWith$ DoubleToken | EffectOnly$ True | Description$ If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.
SVar:DoubleToken:DB$ ReplaceToken | Type$ Amount
R:Event$ AddCounter | ActiveZones$ Battlefield | ValidCard$ Permanent.YouCtrl+inZoneBattlefield | EffectOnly$ True | ReplaceWith$ DoubleCounters | Description$ If an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead.
SVar:DoubleCounters:DB$ ReplaceCounter | Amount$ Y
SVar:Y:ReplaceCount$CounterNum/Twice
Oracle:If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead.
"""

GARRUKS_UPRISING = r"""Name:Garruk's Uprising
ManaCost:2 G
Types:Enchantment
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Card.Self | IsPresent$ Creature.YouCtrl+powerGE4 | Execute$ TrigDraw | TriggerDescription$ When CARDNAME enters, if you control a creature with power 4 or greater, draw a card.
S:Mode$ Continuous | Affected$ Creature.YouCtrl | AddKeyword$ Trample | Description$ Creatures you control have trample.
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Creature.powerGE4+YouCtrl | TriggerZones$ Battlefield | Execute$ TrigDraw | TriggerDescription$ Whenever a creature you control with power 4 or greater enters, draw a card.
SVar:TrigDraw:DB$ Draw | Defined$ You
Oracle:When Garruk's Uprising enters, if you control a creature with power 4 or greater, draw a card.\nCreatures you control have trample. (They can deal excess combat damage to the player or planeswalker they're attacking.)\nWhenever a creature you control with power 4 or greater enters, draw a card.
"""

MINISTRANT_OF_OBLIGATION = r"""Name:Ministrant of Obligation
ManaCost:2 W
Types:Creature Human Cleric
PT:2/1
K:Afterlife:2
DeckHas:Ability$Token
Oracle:Afterlife 2 (When this creature dies, create two 1/1 white and black Spirit creature tokens with flying.)
"""

WANDERING_ARCHAIC = r"""Name:Wandering Archaic
ManaCost:5
Types:Creature Avatar
PT:4/4
T:Mode$ SpellCast | ValidCard$ Instant,Sorcery | ValidActivatingPlayer$ Opponent | TriggerZones$ Battlefield | Execute$ TrigCopySpell | TriggerDescription$ Whenever an opponent casts an instant or sorcery spell, they may pay {2}. If they don't, you may copy that spell. You may choose new targets for the copy.
SVar:TrigCopySpell:DB$ CopySpellAbility | UnlessCost$ 2 | UnlessPayer$ TriggeredActivator | Controller$ You | Defined$ TriggeredSpellAbility | AILogic$ Always | Optional$ True | MayChooseTarget$ True
AlternateMode:Modal
Oracle:Whenever an opponent casts an instant or sorcery spell, they may pay {2}. If they don't, you may copy that spell. You may choose new targets for the copy.

ALTERNATE

Name:Explore the Vastlands
ManaCost:3
Types:Sorcery
A:SP$ DigMultiple | Defined$ Player | DigNum$ 5 | Optional$ True | ChangeValid$ Land,Spell.!Aura | RestRandomOrder$ True | SubAbility$ DBGainLife | SpellDescription$ Each player looks at the top five cards of their library and may reveal a land card and/or an instant or sorcery card from among them. Each player puts the cards they revealed this way into their hand and the rest on the bottom of their library in a random order. Each player gains 3 life.
SVar:DBGainLife:DB$ GainLife | Defined$ Player | LifeAmount$ 3 | StackDescription$ None
DeckHas:Ability$LifeGain
DeckHints:Type$Instant|Sorcery
Oracle:Each player looks at the top five cards of their library and may reveal a land card and/or an instant or sorcery card from among them. Each player puts the cards they revealed this way into their hand and the rest on the bottom of their library in a random order. Each player gains 3 life.
"""

BALA_GED_RECOVERY = r"""Name:Bala Ged Recovery
ManaCost:2 G
Types:Sorcery
A:SP$ ChangeZone | ValidTgts$ Card.YouOwn | Origin$ Graveyard | Destination$ Hand | SpellDescription$ Return target card from your graveyard to your hand.
DeckHas:Ability$Graveyard
AlternateMode:Modal
Oracle:Return target card from your graveyard to your hand.

ALTERNATE

Name:Bala Ged Sanctuary
ManaCost:no cost
Types:Land
R:Event$ Moved | ValidCard$ Card.Self | Destination$ Battlefield | ReplacementResult$ Updated | ReplaceWith$ ETBTapped | Description$ CARDNAME enters tapped.
SVar:ETBTapped:DB$ Tap | Defined$ Self | ETB$ True
A:AB$ Mana | Cost$ T | Produced$ G | SpellDescription$ Add {G}.
Oracle:Bala Ged Sanctuary enters tapped.\n{T}: Add {G}.
"""

OPP_LANDFALL = BALOTHS.replace("ValidCard$ Land.YouCtrl", "ValidCard$ Land.OppCtrl")
# Hand-edited probes (fail-closed coverage).
IS_PRESENT_LANDFALL = BALOTHS.replace("| Execute$ TrigToken", "| IsPresent$ Creature.YouCtrl+powerGE4 | Execute$ TrigToken")
CONDITIONAL_MANA = LOTUS_COBRA.replace("DB$ Mana | Produced$ Any", "DB$ Mana | Produced$ Any | ConditionPresent$ Creature.YouCtrl | ConditionCompare$ GE2")
TRUE_ONLY_BRANCH = NECROBLOOM.replace(" | FalseSubAbility$ DBPlant", "")
SAC_COST_DAMAGE = OVERRUN.replace(
    "A:SP$ PumpAll | ValidCards$ Creature.YouCtrl | NumAtt$ +3 | NumDef$ +3 | KW$ Trample",
    "A:SP$ DealDamage | Cost$ 2 G G G Sac<1/Creature> | Defined$ Player.Opponent | NumDmg$ 3")


# ---- stage 2 scripts (verbatim; Windswept Heath, Exploration and Crucible of Worlds fetched from the pinned commit) ----

LIFE_FROM_THE_LOAM = r"""Name:Life from the Loam
ManaCost:1 G
Types:Sorcery
A:SP$ ChangeZone | Origin$ Graveyard | Destination$ Hand | TargetMin$ 0 | TargetMax$ 3 | TgtPrompt$ Choose target land card in your graveyard | ValidTgts$ Land.YouCtrl | SpellDescription$ Return up to three target land cards from your graveyard to your hand.
K:Dredge:3
Oracle:Return up to three target land cards from your graveyard to your hand.\nDredge 3 (If you would draw a card, you may mill three cards instead. If you do, return this card from your graveyard to your hand.)
"""

AZUSA = r"""Name:Azusa, Lost but Seeking
ManaCost:2 G
Types:Legendary Creature Human Monk
PT:1/2
S:Mode$ Continuous | Affected$ You | AdjustLandPlays$ 2 | Description$ You may play two additional lands on each of your turns.
Oracle:You may play two additional lands on each of your turns.
"""

RAMUNAP_EXCAVATOR = r"""Name:Ramunap Excavator
ManaCost:2 G
Types:Creature Snake Cleric
PT:2/3
S:Mode$ Continuous | Affected$ Land.YouOwn | MayPlay$ True | AffectedZone$ Graveyard | Description$ You may play lands from your graveyard.
SVar:NonStackingEffect:True
Oracle:You may play lands from your graveyard.
"""

SPLENDID_RECLAMATION = r"""Name:Splendid Reclamation
ManaCost:3 G
Types:Sorcery
A:SP$ ChangeZoneAll | ChangeType$ Land.YouCtrl | Origin$ Graveyard | Destination$ Battlefield | Tapped$ True | SpellDescription$ Return all land cards from your graveyard to the battlefield tapped.
DeckHints:Ability$Graveyard
Oracle:Return all land cards from your graveyard to the battlefield tapped.
"""

EVOLVING_WILDS = r"""Name:Evolving Wilds
ManaCost:no cost
Types:Land
A:AB$ ChangeZone | Cost$ T Sac<1/CARDNAME> | Origin$ Library | Destination$ Battlefield | Tapped$ True | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | SpellDescription$ Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.
Oracle:{T}, Sacrifice Evolving Wilds: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.
"""

MYRIAD_LANDSCAPE = r"""Name:Myriad Landscape
ManaCost:no cost
Types:Land
R:Event$ Moved | ValidCard$ Card.Self | Destination$ Battlefield | ReplacementResult$ Updated | ReplaceWith$ ETBTapped | Description$ CARDNAME enters tapped.
SVar:ETBTapped:DB$ Tap | Defined$ Self | ETB$ True
A:AB$ Mana | Cost$ T | Produced$ C | SpellDescription$ Add {C}.
A:AB$ ChangeZone | Cost$ 2 T Sac<1/CARDNAME> | Origin$ Library | Destination$ Battlefield | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | Tapped$ True | ChangeNum$ 2 | ShareLandType$ True | SpellDescription$ Search your library for up to two basic land cards that share a land type, put them onto the battlefield tapped, then shuffle.
Oracle:Myriad Landscape enters tapped.\n{T}: Add {C}.\n{2}, {T}, Sacrifice Myriad Landscape: Search your library for up to two basic land cards that share a land type, put them onto the battlefield tapped, then shuffle.
"""

KROSAN_VERGE = r"""Name:Krosan Verge
ManaCost:no cost
Types:Land
R:Event$ Moved | ValidCard$ Card.Self | Destination$ Battlefield | ReplacementResult$ Updated | ReplaceWith$ ETBTapped | Description$ CARDNAME enters tapped.
SVar:ETBTapped:DB$ Tap | Defined$ Self | ETB$ True
A:AB$ Mana | Cost$ T | Produced$ C | SpellDescription$ Add {C}.
A:AB$ ChangeZone | Cost$ 2 T Sac<1/CARDNAME> | Origin$ Library | Destination$ Battlefield | ChangeType$ EACH Forest & Plains | Tapped$ True | SpellDescription$ Search your library for a Forest card and a Plains card, put them onto the battlefield tapped, then shuffle.
Oracle:Krosan Verge enters tapped.\n{T}: Add {C}.\n{2}, {T}, Sacrifice Krosan Verge: Search your library for a Forest card and a Plains card, put them onto the battlefield tapped, then shuffle.
"""

WINDSWEPT_HEATH = r"""Name:Windswept Heath
ManaCost:no cost
Types:Land
A:AB$ ChangeZone | Cost$ T PayLife<1> Sac<1/CARDNAME> | Origin$ Library | Destination$ Battlefield | ChangeType$ Forest,Plains | SpellDescription$ Search your library for a Forest or Plains card, put it onto the battlefield, then shuffle.
Oracle:{T}, Pay 1 life, Sacrifice Windswept Heath: Search your library for a Forest or Plains card, put it onto the battlefield, then shuffle.
"""

AFTERMATH_ANALYST = r"""Name:Aftermath Analyst
ManaCost:1 G
Types:Creature Elf Detective
PT:1/3
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Card.Self | Execute$ TrigMill | TriggerDescription$ When CARDNAME enters, mill three cards.
SVar:TrigMill:DB$ Mill | Defined$ You | NumCards$ 3
A:AB$ ChangeZoneAll | Cost$ 3 G Sac<1/CARDNAME> | ChangeType$ Land.YouCtrl | Origin$ Graveyard | Destination$ Battlefield | Tapped$ True | SpellDescription$ Return all land cards from your graveyard to the battlefield tapped.
DeckHas:Ability$Mill|Sacrifice|Graveyard
DeckHints:Ability$Mill|Graveyard
Oracle:When Aftermath Analyst enters, mill three cards.\n{3}{G}, Sacrifice Aftermath Analyst: Return all land cards from your graveyard to the battlefield tapped.
"""

GITROG = r"""Name:The Gitrog Monster
ManaCost:3 B G
Types:Legendary Creature Frog Horror
PT:6/6
K:Deathtouch
T:Mode$ Phase | Phase$ Upkeep | ValidPlayer$ You | TriggerZones$ Battlefield | Execute$ TrigUpkeep | TriggerDescription$ At the beginning of your upkeep, sacrifice CARDNAME unless you sacrifice a land.
SVar:TrigUpkeep:DB$ Sacrifice | UnlessPayer$ You | UnlessCost$ Sac<1/Land>
S:Mode$ Continuous | Affected$ You | AdjustLandPlays$ 1 | Description$ You may play an additional land on each of your turns.
T:Mode$ ChangesZoneAll | ValidCards$ Land.YouOwn+!token | Origin$ Any | Destination$ Graveyard | TriggerZones$ Battlefield | Execute$ TrigDraw | TriggerDescription$ Whenever one or more land cards are put into your graveyard from anywhere, draw a card.
SVar:TrigDraw:DB$ Draw | Defined$ You | NumCards$ 1
DeckHas:Ability$Graveyard
Oracle:Deathtouch\nAt the beginning of your upkeep, sacrifice The Gitrog Monster unless you sacrifice a land.\nYou may play an additional land on each of your turns.\nWhenever one or more land cards are put into your graveyard from anywhere, draw a card.
"""

TITANIA = r"""Name:Titania, Protector of Argoth
ManaCost:3 G G
Types:Legendary Creature Elemental
PT:5/3
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Card.Self | Execute$ TrigChangeZone | TriggerDescription$ When CARDNAME enters, return target land card from your graveyard to the battlefield.
SVar:TrigChangeZone:DB$ ChangeZone | Origin$ Graveyard | Destination$ Battlefield | ValidTgts$ Land.YouCtrl
T:Mode$ ChangesZone | Origin$ Battlefield | Destination$ Graveyard | ValidCard$ Land.YouCtrl | TriggerZones$ Battlefield | Execute$ TrigToken | TriggerDescription$ Whenever a land you control is put into a graveyard from the battlefield, create a 5/3 green Elemental creature token.
SVar:TrigToken:DB$ Token | TokenScript$ g_5_3_elemental | TokenOwner$ You
Oracle:When Titania, Protector of Argoth enters, return target land card from your graveyard to the battlefield.\nWhenever a land you control is put into a graveyard from the battlefield, create a 5/3 green Elemental creature token.
"""

ROILING_REGROWTH = r"""Name:Roiling Regrowth
ManaCost:2 G
Types:Instant
A:SP$ Sacrifice | Defined$ You | SacValid$ Land | SubAbility$ DBChangeZone | StackDescription$ SpellDescription | SpellDescription$ Sacrifice a land. Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.
SVar:DBChangeZone:DB$ ChangeZone | Origin$ Library | Destination$ Battlefield | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | ChangeNum$ 2 | Tapped$ True | StackDescription$ None
SVar:AIPreference:SacCost$Land.Basic+tapped
Oracle:Sacrifice a land. Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.
"""

ENTISH_RESTORATION = r"""Name:Entish Restoration
ManaCost:2 G
Types:Instant
A:SP$ Sacrifice | Defined$ You | SacValid$ Land | SubAbility$ DBChangeZone | SpellDescription$ Sacrifice a land. Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle. If you control a creature with power 4 or greater, instead search your library for up to three basic land cards, put them onto the battlefield tapped, then shuffle.
SVar:DBChangeZone:DB$ ChangeZone | Origin$ Library | Destination$ Battlefield | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | ChangeNum$ X | Tapped$ True
SVar:AIPreference:SacCost$Land.Basic+tapped
SVar:X:Count$Compare Y GE1.3.2
SVar:Y:Count$Valid Creature.YouCtrl+powerGE4
DeckHas:Ability$Sacrifice
Oracle:Sacrifice a land. Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle. If you control a creature with power 4 or greater, instead search your library for up to three basic land cards, put them onto the battlefield tapped, then shuffle.
"""

SPRINGBLOOM_DRUID = r"""Name:Springbloom Druid
ManaCost:2 G
Types:Creature Elf Druid
PT:1/1
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Card.Self | Execute$ TrigRamp | TriggerDescription$ When CARDNAME enters, you may sacrifice a land. If you do, search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.
SVar:TrigRamp:AB$ ChangeZone | Cost$ Sac<1/Land> | Origin$ Library | Destination$ Battlefield | Tapped$ True | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | ChangeNum$ 2 | ShuffleNonMandatory$ True
Oracle:When Springbloom Druid enters, you may sacrifice a land. If you do, search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.
"""

SAKURA_TRIBE_ELDER = r"""Name:Sakura-Tribe Elder
ManaCost:1 G
Types:Creature Snake Shaman
PT:1/1
A:AB$ ChangeZone | Cost$ Sac<1/CARDNAME> | Origin$ Library | Destination$ Battlefield | Tapped$ True | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | SpellDescription$ Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.
SVar:SacMeAfterBlock:TRUE
Oracle:Sacrifice Sakura-Tribe Elder: Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.
"""

EXPLORE = r"""Name:Explore
ManaCost:1 G
Types:Sorcery
A:SP$ Effect | StaticAbilities$ Exploration | AILogic$ Always | SubAbility$ DBDraw | SpellDescription$ You may play an additional land this turn. Draw a card.
SVar:Exploration:Mode$ Continuous | Affected$ You | AdjustLandPlays$ 1 | Description$ You may play an additional land this turn.
SVar:NeedsToPlayVar:ZZ GE1
SVar:ZZ:Count$ValidHand Land.YouOwn
SVar:DBDraw:DB$ Draw | Defined$ You | NumCards$ 1
Oracle:You may play an additional land this turn.\nDraw a card.
"""

ORACLE_OF_MUL_DAYA = r"""Name:Oracle of Mul Daya
ManaCost:3 G
Types:Creature Elf Shaman
PT:2/2
S:Mode$ Continuous | Affected$ You | AdjustLandPlays$ 1 | Description$ You may play an additional land on each of your turns.
S:Mode$ Continuous | Affected$ Card.TopLibrary+YouCtrl | AffectedZone$ Library | MayLookAt$ Player | Description$ Play with the top card of your library revealed.
S:Mode$ Continuous | Affected$ Land.TopLibrary+YouCtrl | AffectedZone$ Library | MayPlay$ True | Description$ You may play lands from the top of your library.
Oracle:You may play an additional land on each of your turns.\nPlay with the top card of your library revealed.\nYou may play lands from the top of your library.
"""

ANCIENT_GREENWARDEN = r"""Name:Ancient Greenwarden
ManaCost:4 G G
Types:Creature Elemental
PT:5/7
K:Reach
S:Mode$ Continuous | Affected$ Land.YouCtrl | MayPlay$ True | AffectedZone$ Graveyard | Description$ You may play lands from your graveyard.
S:Mode$ Panharmonicon | ValidMode$ ChangesZone,ChangesZoneAll | ValidCard$ Permanent.YouCtrl | ValidCause$ Land | Destination$ Battlefield | Description$ If a land entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.
Oracle:Reach\nYou may play lands from your graveyard.\nIf a land entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.
"""

EXPLORATION = r"""Name:Exploration
ManaCost:G
Types:Enchantment
S:Mode$ Continuous | Affected$ You | AdjustLandPlays$ 1 | Description$ You may play an additional land on each of your turns.
Oracle:You may play an additional land on each of your turns.
"""

CRUCIBLE_OF_WORLDS = r"""Name:Crucible of Worlds
ManaCost:3
Types:Artifact
S:Mode$ Continuous | Affected$ Land.YouOwn | MayPlay$ True | AffectedZone$ Graveyard | Description$ You may play lands from your graveyard.
SVar:NonStackingEffect:True
Oracle:You may play lands from your graveyard.
"""

THE_MENDING_OF_DOMINARIA = r"""Name:The Mending of Dominaria
ManaCost:3 G G
Types:Enchantment Saga
K:Chapter:3:TrigMill,TrigMill,DBChangeZoneAll
SVar:TrigMill:DB$ Mill | NumCards$ 2 | Defined$ You | SubAbility$ DBChangeZone | SpellDescription$ Mill two cards, then you may return a creature card from your graveyard to your hand.
SVar:DBChangeZone:DB$ ChangeZone | Hidden$ True | Origin$ Graveyard | Destination$ Hand | ChangeType$ Creature.YouOwn
SVar:DBChangeZoneAll:DB$ ChangeZoneAll | ChangeType$ Land.YouCtrl | Origin$ Graveyard | Destination$ Battlefield | SubAbility$ DBShuffle | SpellDescription$ Return all land cards from your graveyard to the battlefield, then shuffle your graveyard into your library.
SVar:DBShuffle:DB$ ChangeZoneAll | ChangeType$ Card.YouOwn | Origin$ Graveyard | Destination$ Library | Shuffle$ True
DeckHints:Ability$Graveyard
Oracle:(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Mill two cards, then you may return a creature card from your graveyard to your hand.\nIII — Return all land cards from your graveyard to the battlefield, then shuffle your graveyard into your library.
"""

ETERNAL_WITNESS = r"""Name:Eternal Witness
ManaCost:1 G G
Types:Creature Human Shaman
PT:2/1
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Card.Self | Execute$ TrigChangeZone | OptionalDecider$ You | TriggerDescription$ When CARDNAME enters, you may return target card from your graveyard to your hand.
SVar:TrigChangeZone:DB$ ChangeZone | Origin$ Graveyard | Destination$ Hand | ValidTgts$ Card.YouCtrl
Oracle:When Eternal Witness enters, you may return target card from your graveyard to your hand.
"""

KNIGHT_OF_THE_RELIQUARY = r"""Name:Knight of the Reliquary
ManaCost:1 G W
Types:Creature Human Knight
PT:2/2
A:AB$ ChangeZone | Cost$ T Sac<1/Forest;Plains/Forest or Plains> | Origin$ Library | Destination$ Battlefield | ChangeType$ Land | ChangeNum$ 1 | SpellDescription$ Search your library for a land card, put it onto the battlefield, then shuffle.
S:Mode$ Continuous | AffectedDefined$ Self | AddPower$ X | AddToughness$ X | Description$ CARDNAME gets +1/+1 for each land card in your graveyard.
SVar:X:Count$ValidGraveyard Land.YouOwn
Oracle:Knight of the Reliquary gets +1/+1 for each land card in your graveyard.\n{T}, Sacrifice a Forest or Plains: Search your library for a land card, put it onto the battlefield, then shuffle.
"""

THALIA_AND_GITROG = r"""Name:Thalia and The Gitrog Monster
ManaCost:1 W B G
Types:Legendary Creature Human Frog Horror
PT:4/4
K:First Strike
K:Deathtouch
S:Mode$ Continuous | Affected$ You | AdjustLandPlays$ 1 | Description$ You may play an additional land on each of your turns.
R:Event$ Moved | ValidCard$ Creature.OppCtrl,Land.nonBasic+OppCtrl | Destination$ Battlefield | ReplaceWith$ ETBTapped | ReplacementResult$ Updated | ActiveZones$ Battlefield | Description$ Creatures and nonbasic lands your opponents control enter tapped.
SVar:ETBTapped:DB$ Tap | ETB$ True | Defined$ ReplacedCard
T:Mode$ Attacks | ValidCard$ Card.Self | Execute$ TrigSac | TriggerDescription$ Whenever CARDNAME attacks, sacrifice a creature or land, then draw a card.
SVar:TrigSac:DB$ Sacrifice | Defined$ You | SacValid$ Land,Creature | SubAbility$ DBDraw
SVar:DBDraw:DB$ Draw
SVar:HasAttackEffect:TRUE
DeckHas:Ability$Sacrifice
Oracle:First strike, deathtouch\nYou may play an additional land on each of your turns.\nCreatures and nonbasic lands your opponents control enter tapped.\nWhenever Thalia and The Gitrog Monster attacks, sacrifice a creature or land, then draw a card.
"""

DREAD_RETURN = r"""Name:Dread Return
ManaCost:2 B B
Types:Sorcery
K:Flashback:Sac<3/Creature>
A:SP$ ChangeZone | Origin$ Graveyard | Destination$ Battlefield | TgtPrompt$ Choose target creature card in your graveyard | ValidTgts$ Creature.YouCtrl | SpellDescription$ Return target creature card from your graveyard to the battlefield.
Oracle:Return target creature card from your graveyard to the battlefield.\nFlashback—Sacrifice three creatures. (You may cast this card from your graveyard for its flashback cost. Then exile it.)
"""

SUN_TITAN = r"""Name:Sun Titan
ManaCost:4 W W
Types:Creature Giant
PT:6/6
K:Vigilance
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Card.Self | Execute$ TrigChange | OptionalDecider$ You | TriggerDescription$ Whenever CARDNAME enters or attacks, you may return target permanent card with mana value 3 or less from your graveyard to the battlefield.
T:Mode$ Attacks | ValidCard$ Card.Self | Execute$ TrigChange | TriggerZones$ Battlefield | OptionalDecider$ You | Secondary$ True | TriggerDescription$ Whenever CARDNAME enters or attacks, you may return target permanent card with mana value 3 or less from your graveyard to the battlefield.
SVar:TrigChange:DB$ ChangeZone | Origin$ Graveyard | Destination$ Battlefield | ValidTgts$ Permanent.YouCtrl+cmcLE3
SVar:HasAttackEffect:TRUE
Oracle:Vigilance\nWhenever Sun Titan enters or attacks, you may return target permanent card with mana value 3 or less from your graveyard to the battlefield.
"""

SEVINNES_RECLAMATION = r"""Name:Sevinne's Reclamation
ManaCost:2 W
Types:Sorcery
A:SP$ ChangeZone | Origin$ Graveyard | Destination$ Battlefield | TgtPrompt$ Choose target permanent card with mana value 3 or less from your graveyard | ValidTgts$ Permanent.cmcLE3+YouCtrl | SubAbility$ DBCopy | SpellDescription$ Return target permanent card with mana value 3 or less from your graveyard to the battlefield. If this spell was cast from a graveyard, you may copy this spell and may choose a new target for the copy.
SVar:DBCopy:DB$ CopySpellAbility | Defined$ Parent | Optional$ True | MayChooseTarget$ True | ConditionDefined$ Self | ConditionPresent$ Card.wasCastFromGraveyard
AI:RemoveDeck:Random
K:Flashback:4 W
Oracle:Return target permanent card with mana value 3 or less from your graveyard to the battlefield. If this spell was cast from a graveyard, you may copy this spell and may choose a new target for the copy.\nFlashback {4}{W} (You may cast this card from your graveyard for its flashback cost. Then exile it.)
"""

WORLD_SHAPER = r"""Name:World Shaper
ManaCost:3 G
Types:Creature Merfolk Shaman
PT:3/3
T:Mode$ Attacks | ValidCard$ Card.Self | Execute$ TrigMill | TriggerDescription$ Whenever CARDNAME attacks, you may mill three cards.
SVar:TrigMill:DB$ Mill | NumCards$ 3 | Defined$ You | Optional$ True
T:Mode$ ChangesZone | Origin$ Battlefield | Destination$ Graveyard | ValidCard$ Card.Self | Execute$ TrigChangeZoneAll | TriggerDescription$ When CARDNAME dies, put all land cards from your graveyard onto the battlefield tapped.
SVar:TrigChangeZoneAll:DB$ ChangeZoneAll | ChangeType$ Land.YouCtrl | Origin$ Graveyard | Destination$ Battlefield | Tapped$ True
DeckHints:Ability$Graveyard
Oracle:Whenever World Shaper attacks, you may mill three cards.\nWhen World Shaper dies, return all land cards from your graveyard to the battlefield tapped.
"""

HEDGE_SHREDDER = r"""Name:Hedge Shredder
ManaCost:2 G G
Types:Artifact Vehicle
PT:5/5
T:Mode$ Attacks | ValidCard$ Card.Self | Execute$ TrigMill | TriggerDescription$ Whenever CARDNAME attacks, you may mill two cards.
SVar:TrigMill:DB$ Mill | NumCards$ 2 | Defined$ You | Optional$ True
T:Mode$ ChangesZoneAll | ValidCards$ Land.YouOwn | Origin$ Library | Destination$ Graveyard | TriggerZones$ Battlefield | Execute$ TrigChangeZoneAll | TriggerDescription$ Whenever one or more land cards are put into your graveyard from your library, put them onto the battlefield tapped.
SVar:TrigChangeZoneAll:DB$ ChangeZoneAll | ChangeType$ Card.TriggeredCards | Origin$ Graveyard | Destination$ Battlefield | Tapped$ True
K:Crew:1
Oracle:Whenever Hedge Shredder attacks, you may mill two cards.\nWhenever one or more land cards are put into your graveyard from your library, put them onto the battlefield tapped.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)
"""

EERIE_ULTIMATUM = r"""Name:Eerie Ultimatum
ManaCost:W W B B B G G
Types:Sorcery
A:SP$ ChangeZone | Origin$ Graveyard | Destination$ Battlefield | ChangeType$ Permanent.YouOwn | ChangeNumDesc$ any number of | ChangeTypeDesc$ permanent cards with different names | DifferentNames$ True | ChangeNum$ X | Hidden$ True | SpellDescription$ Return any number of permanent cards with different names from your graveyard to the battlefield.
SVar:X:Count$ValidGraveyard Permanent.YouOwn$DifferentCardNames
SVar:IsReanimatorCard:TRUE
DeckHas:Ability$Graveyard
Oracle:Return any number of permanent cards with different names from your graveyard to the battlefield.
"""

INSIDIOUS_ROOTS = r"""Name:Insidious Roots
ManaCost:B G
Types:Enchantment
S:Mode$ Continuous | Affected$ Creature.token+YouCtrl | AddAbility$ AnyMana | Description$ Creature tokens you control have "{T}: Add one mana of any color."
SVar:AnyMana:AB$ Mana | Cost$ T | Produced$ Any | Amount$ 1 | SpellDescription$ Add one mana of any color.
T:Mode$ ChangesZoneAll | ValidCards$ Creature.YouOwn | Origin$ Graveyard | Destination$ Any | TriggerZones$ Battlefield | Execute$ TrigToken | TriggerDescription$ Whenever one or more creature cards leave your graveyard, create a 0/1 green Plant creature token, then put a +1/+1 counter on each Plant you control.
SVar:TrigToken:DB$ Token | TokenScript$ g_0_1_plant | SubAbility$ DBCounters
SVar:DBCounters:DB$ PutCounterAll | ValidCards$ Plant.YouCtrl | CounterType$ P1P1 | CounterNum$ 1
DeckHas:Ability$Graveyard|Token|Counters & Type$Plant
DeckHints:Type$Plant
Oracle:Creature tokens you control have "{T}: Add one mana of any color."\nWhenever one or more creature cards leave your graveyard, create a 0/1 green Plant creature token, then put a +1/+1 counter on each Plant you control.
"""

CORRUPTED_CONVICTION = r"""Name:Corrupted Conviction
ManaCost:B
Types:Instant
A:SP$ Draw | Cost$ B Sac<1/Creature> | NumCards$ 2 | SpellDescription$ Draw two cards.
DeckHas:Ability$Sacrifice
Oracle:As an additional cost to cast this spell, sacrifice a creature.\nDraw two cards.
"""

REANIMATE = r"""Name:Reanimate
ManaCost:B
Types:Sorcery
A:SP$ ChangeZone | Origin$ Graveyard | Destination$ Battlefield | GainControl$ True | TgtPrompt$ Choose target creature card in a graveyard | ValidTgts$ Creature | ChangeNum$ 1 | RememberLKI$ True | SubAbility$ DBLoseLifeYou | SpellDescription$ Put target creature card from a graveyard onto the battlefield under your control. You lose life equal to its mana value.
SVar:DBLoseLifeYou:DB$ LoseLife | Defined$ You | LifeAmount$ X | SubAbility$ DBCleanup
SVar:DBCleanup:DB$ Cleanup | ClearRemembered$ True
SVar:X:RememberedLKI$CardManaCost
Oracle:Put target creature card from a graveyard onto the battlefield under your control. You lose life equal to its mana value.
"""

HORIZON_CANOPY = r"""Name:Horizon Canopy
ManaCost:no cost
Types:Land
A:AB$ Mana | Cost$ T PayLife<1> | Produced$ Combo G W | SpellDescription$ Add {G} or {W}.
A:AB$ Draw | Cost$ 1 T Sac<1/CARDNAME> | NumCards$ 1 | SpellDescription$ Draw a card.
Oracle:{T}, Pay 1 life: Add {G} or {W}.\n{1}, {T}, Sacrifice Horizon Canopy: Draw a card.
"""

HEDGE_SHREDDER_OPP = HEDGE_SHREDDER.replace("ValidCards$ Land.YouOwn", "ValidCards$ Land.OppCtrl")

AZUSA_NOT_YOU = AZUSA.replace("Affected$ You", "Affected$ Player")
SPRINGBLOOM_WITH_MANA = SPRINGBLOOM_DRUID.replace("Cost$ Sac<1/Land>", "Cost$ 1 Sac<1/Land>")


def _card(name: str, type_line: str = "Creature") -> CardData:
    return CardData.from_scryfall(make_card(name, type_line=type_line))


def _read(script: str | None, special: SpecialBehaviour | None = None) -> CardEffects:
    return effects_for(_card("Test Card"), script, special)


def test_parse_script_splits_fields():
    s = parse_script(AVENGER)
    assert len(s.triggers) == 2 and s.abilities == [] and s.statics == []
    assert s.triggers[0]["Mode"] == "ChangesZone" and s.triggers[0]["Execute"] == "TrigToken"
    assert s.svars["TrigToken"] == {"DB": "Token", "TokenAmount": "X", "TokenScript": "g_0_1_plant", "TokenOwner": "You"}
    assert s.svars["X"] == {"Count": "Valid Land.YouCtrl"}
    assert parse_script(BALOTHS).keywords == ("Trample",)


def test_necrobloom_branch_upgrades_plant_to_zombie():
    ce = _read(NECROBLOOM)
    zombie = Effect("landfall", "token", 1, 2, 2, "Zombie", when="distinct_lands >= 7")
    assert ce.effects == (Effect("landfall", "token", 1, 0, 1, "Plant", upgrade=zombie), Effect("static", "dredge", 2, type="lands"))
    assert ce.source == "forge" and ce.unread == ()


def test_avenger_tokens_per_land_and_plant_counters():
    ce = _read(AVENGER)
    assert ce.effects == (Effect("etb", "token", "lands", 0, 1, "Plant"), Effect("landfall", "counters", 1, type="Plant"))
    assert ce.unread == () and not ce.partial


def test_baloths_beast():
    ce = _read(BALOTHS)
    assert ce.effects == (Effect("landfall", "token", 1, 4, 4, "Beast"),) and ce.unread == ()


def test_felidar_retreat_first_charm_choice():
    ce = _read(FELIDAR_RETREAT)
    # Forge's token script is w_2_2_cat_beast: the token is a Cat Beast.
    assert ce.effects == (Effect("landfall", "token", 1, 2, 2, "Cat Beast"),)
    assert len(ce.unread) == 1 and "PutCounterAll" in ce.unread[0] and ce.partial


def test_token_script_ability_suffix_is_not_a_type():
    assert _read(EMERIA_ANGEL).effects == (Effect("landfall", "token", 1, 1, 1, "Bird"),)


def test_scute_swarm_copy_branch_unread():
    ce = _read(SCUTE_SWARM)
    assert ce.effects == (Effect("landfall", "token", 1, 1, 1, "Insect"),)
    assert len(ce.unread) == 1 and "CopyPermanent" in ce.unread[0] and ce.partial


def test_intangible_virtue_token_anthem():
    ce = _read(INTANGIBLE_VIRTUE)
    assert ce.effects == (Effect("static", "anthem", 1, 1, 1, "tokens"),) and ce.unread == ()


def test_overrun_pump():
    ce = _read(OVERRUN)
    assert ce.effects == (Effect("cast", "pump", 1, 3, 3, ""),) and ce.unread == ()


def test_lotus_cobra_landfall_mana():
    ce = _read(LOTUS_COBRA)
    assert ce.effects == (Effect("landfall", "mana", 1),) and ce.unread == ()


def test_retreat_to_hagra_drain_is_first_understood_choice():
    ce = _read(RETREAT_TO_HAGRA)
    assert ce.effects == (Effect("landfall", "drain", 1),) and ce.effects[0].each_opponent
    assert len(ce.unread) == 1 and "DB$ Pump" in ce.unread[0] and ce.partial is True


def test_mirkwood_bats_token_created_drain():
    ce = _read(MIRKWOOD_BATS)
    assert ce.effects == (Effect("token_created", "drain", 1),)
    assert len(ce.unread) == 1 and ce.unread[0].startswith("T:Mode$ Sacrificed") and ce.partial is True


def test_ramp_spells():
    assert (_read(HARROW).ramp_to_battlefield, _read(HARROW).ramp_to_hand) == (2, 0)
    assert (_read(CULTIVATE).ramp_to_battlefield, _read(CULTIVATE).ramp_to_hand) == (1, 1)
    assert (_read(RAMPANT_GROWTH).ramp_to_battlefield, _read(RAMPANT_GROWTH).ramp_to_hand) == (1, 0)
    for script in (HARROW, CULTIVATE, RAMPANT_GROWTH):
        assert _read(script).unread == () and _read(script).effects == ()


def test_opponent_landfall_is_unread():
    ce = _read(OPP_LANDFALL)
    assert ce.effects == () and ce.unread == ("T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield",) and not ce.partial


def test_six_reads_nothing():
    ce = _read(SIX)
    assert ce.effects == () and ce.unread and ce.source == "forge"


def test_vanilla_creature_is_read_and_empty():
    ce = _read(GRIZZLY_BEARS)
    assert ce.effects == () and ce.unread == () and ce.source == "forge"


def test_no_script_is_source_none():
    ce = _read(None)
    assert ce == CardEffects((), "none", ())


def test_table_takes_precedence_over_script():
    goat = Effect("landfall", "token", 1, 1, 1, "Goat")
    ce = effects_for(_card("Rampaging Baloths"), BALOTHS, SpecialBehaviour("Rampaging Baloths", None, 0, effects=(goat,)))
    assert ce.effects == (goat,) and ce.source == "table" and ce.unread == ()


def test_table_entry_without_effects_falls_back_to_script():
    ce = effects_for(_card("Rampaging Baloths"), BALOTHS, SpecialBehaviour("Rampaging Baloths", "rock", 1))
    assert ce.source == "forge" and ce.effects[0].type == "Beast"


def test_condition_holds():
    assert condition_holds("", 0, 0, 0)
    assert condition_holds("distinct_lands >= 7", 7, 7, 0) and not condition_holds("distinct_lands >= 7", 6, 9, 0)
    assert condition_holds("lands >= 6", 1, 6, 0) and not condition_holds("lands >= 6", 9, 5, 0)
    assert condition_holds("tokens >= 3", 0, 0, 3) and not condition_holds("tokens >= 3", 9, 9, 2)


def test_parse_effects_table_with_upgrade():
    raw = [{"on": "landfall", "do": "token", "power": 0, "toughness": 1, "type": "Plant",
            "upgrade": {"on": "landfall", "do": "token", "power": 2, "toughness": 2, "type": "Zombie", "when": "distinct_lands >= 7"}},
           {"on": "etb", "do": "token", "n": "lands", "toughness": 1, "type": "Plant"},
           {"on": "landfall", "do": "drain", "each_opponent": False}]
    assert parse_effects_table(raw) == (
        Effect("landfall", "token", 1, 0, 1, "Plant", upgrade=Effect("landfall", "token", 1, 2, 2, "Zombie", when="distinct_lands >= 7")),
        Effect("etb", "token", "lands", 0, 1, "Plant"),
        Effect("landfall", "drain", 1, each_opponent=False),
    )


@pytest.mark.parametrize("bad, key", [({"on": "bogus", "do": "token"}, "on"), ({"on": "landfall", "do": "bogus"}, "do"),
                                      ({"on": "landfall", "do": "token", "colour": "g"}, "colour"),
                                      ({"on": "landfall", "do": "token", "n": "all"}, "n"),
                                      ({"on": "landfall", "do": "token", "type": "lands"}, "type"),
                                      ({"on": "activated", "do": "return_lands", "n": "all", "cost": "X"}, "cost")])
def test_parse_effects_table_rejects_unknown(bad, key):
    with pytest.raises(ValueError, match=key):
        parse_effects_table([bad])


def test_replacement_lines_are_unread_except_self_enters_tapped():
    ce = _read(DOUBLING_SEASON)
    assert ce.effects == () and len(ce.unread) == 2 and all(u.startswith("R:Event$") for u in ce.unread)


def test_trigger_with_unknown_condition_is_unread():
    ce = _read(IS_PRESENT_LANDFALL)
    assert IS_PRESENT_LANDFALL != BALOTHS and ce.effects == () and len(ce.unread) == 1 and ce.unread[0].startswith("T:Mode$ ChangesZone")
    assert len(_read(GARRUKS_UPRISING).unread) == 2  # IsPresent ETB and the power-4 creature trigger


def test_conditional_step_is_unread():
    ce = _read(CONDITIONAL_MANA)
    assert CONDITIONAL_MANA != LOTUS_COBRA and ce.effects == () and len(ce.unread) == 1


def test_keywords_outside_the_allowlist_are_unread():
    assert _read(MINISTRANT_OF_OBLIGATION).unread == ("K:Afterlife:2",)
    assert _read(BALOTHS).unread == ()  # K:Trample is ignored


def test_back_face_is_unread_unless_it_is_a_land():
    assert "ALTERNATE: Modal" in _read(WANDERING_ARCHAIC).unread
    assert not any(u.startswith(("ALTERNATE", "R:")) for u in _read(BALA_GED_RECOVERY).unread)


def test_true_only_branch_keeps_its_condition():
    ce = _read(TRUE_ONLY_BRANCH)
    assert TRUE_ONLY_BRANCH != NECROBLOOM
    assert ce.effects == (Effect("landfall", "token", 1, 2, 2, "Zombie", when="distinct_lands >= 7"), Effect("static", "dredge", 2, type="lands"))
    assert ce.unread == ()


def test_ramp_land_sacrifice_cost():
    harrow = _read(HARROW)
    assert (harrow.ramp_to_battlefield, harrow.ramp_to_hand, harrow.ramp_sacrifice_lands) == (2, 0, 1)
    assert _read(CULTIVATE).ramp_sacrifice_lands == 0


def test_other_sacrifice_cost_is_unread():
    ce = _read(SAC_COST_DAMAGE)
    assert SAC_COST_DAMAGE != OVERRUN
    assert ce.effects == (Effect("cast", "drain", 3),) and ce.unread == ("Cost$ 2 G G G Sac<1/Creature>",) and ce.partial


UNLESS_DRAIN = MIRKWOOD_BATS.replace("LifeAmount$ 1 | Defined$ Opponent", "LifeAmount$ 1 | Defined$ Opponent | UnlessCost$ 2 | UnlessPayer$ Player.Opponent")
UNLESS_PAYER_ONLY = MIRKWOOD_BATS.replace("LifeAmount$ 1 | Defined$ Opponent", "LifeAmount$ 1 | Defined$ Opponent | UnlessPayer$ Opponent")
UNLESS_TRIGGER = BALOTHS.replace("| Execute$ TrigToken", "| UnlessCost$ 1 | Execute$ TrigToken")
UNLESS_SPELL = SAC_COST_DAMAGE.replace("Cost$ 2 G G G Sac<1/Creature> | ", "UnlessCost$ 3 | ")


def test_punisher_unless_cost_is_unread():
    for script in (UNLESS_DRAIN, UNLESS_PAYER_ONLY):
        ce = _read(script)
        assert script != MIRKWOOD_BATS and ce.effects == ()
        assert any(u.startswith("T:Mode$ TokenCreated") for u in ce.unread)
    ce = _read(UNLESS_TRIGGER)
    assert UNLESS_TRIGGER != BALOTHS and ce.effects == () and ce.unread[0].startswith("T:Mode$ ChangesZone")
    ce = _read(UNLESS_SPELL)
    assert "UnlessCost" in UNLESS_SPELL and ce.effects == () and ce.unread[0].startswith("A:SP$ DealDamage")


# ---------------------------------------------------------------------------------- payoffs.py / effects.py agreement
from pathlib import Path  # noqa: E402

from edhpower.payoffs import detect  # noqa: E402
from edhpower.profile import load_special_behaviours  # noqa: E402

from .conftest import fixture_facts  # noqa: E402

# payoff category <-> the (trigger, action) effects.py reads for the same oracle ability
_AGREEING = {"landfall_tokens": ("landfall", "token"), "landfall_payoff": ("landfall", "drain"), "token_drain": ("token_created", "drain")}
_FIXTURE_NAMES = sorted(p.name.removesuffix(".facts.json") for p in (Path(__file__).parent / "fixtures").glob("*.facts.json"))


def _matches(want: tuple[str, str], fx: CardEffects, script: str | None) -> bool:
    if any((e.on, e.do) == want for e in fx.effects):
        return True
    # a Treasure token is read as mana (it is spent, not attacked with); for this comparison it is a token maker
    return want == ("landfall", "token") and "TokenScript$ c_a_treasure_sac" in (script or "") and any(
        (e.on, e.do) == ("landfall", "mana") for e in fx.effects)


@pytest.mark.parametrize("name", _FIXTURE_NAMES)
def test_payoffs_and_effects_agree(name):
    """Spec: payoffs.py and sim/effects.py read the same abilities; a disagreement is a test failure."""
    facts = fixture_facts(name)
    payoffs, specials = detect(facts), load_special_behaviours()
    disagree: list[str] = []
    for e in facts.entries:
        fx = effects_for(e.card, e.forge_script, specials.get(e.name))
        for cat, want in _AGREEING.items():
            detected = e.name in payoffs.by_category.get(cat, [])
            if detected != _matches(want, fx, e.forge_script):
                disagree.append(f"{e.name}: payoffs {cat}={detected}, effects {[(x.on, x.do) for x in fx.effects]}")
    assert disagree == []


def test_necrobloom_lands_have_dredge_two():
    assert Effect("static", "dredge", 2, type="lands") in _read(NECROBLOOM).effects


def test_loam_returns_lands_and_has_dredge():
    ce = _read(LIFE_FROM_THE_LOAM)
    assert ce.effects == (Effect("cast", "return_lands_to_hand", 3), Effect("static", "dredge", 3)) and ce.unread == ()


def test_extra_land_statics():
    assert _read(AZUSA).effects == (Effect("static", "extra_land", 2),)
    assert _read(EXPLORATION).effects == (Effect("static", "extra_land", 1),)
    ce = _read(ORACLE_OF_MUL_DAYA)
    assert ce.effects == (Effect("static", "extra_land", 1),) and len(ce.unread) == 1 and ce.partial is True


def test_play_lands_from_graveyard():
    for script in (RAMUNAP_EXCAVATOR, CRUCIBLE_OF_WORLDS):
        ce = _read(script)
        assert ce.effects == (Effect("static", "play_lands_from_graveyard"),) and ce.unread == ()
    ce = _read(ANCIENT_GREENWARDEN)
    assert ce.effects == (Effect("static", "play_lands_from_graveyard"),) and len(ce.unread) == 1 and "Panharmonicon" in ce.unread[0]


def test_mass_return():
    assert _read(SPLENDID_RECLAMATION).effects == (Effect("cast", "return_lands", "all"),)
    ce = _read(AFTERMATH_ANALYST)
    assert ce.effects == (Effect("etb", "mill", 3), Effect("activated", "return_lands", "all", cost="3 G Sac<1/CARDNAME>"))
    assert ce.unread == ()


def test_fetch_lands():
    assert _read(EVOLVING_WILDS).effects == (Effect("activated", "fetch", 1, cost="T Sac<1/CARDNAME>"),)
    assert _read(MYRIAD_LANDSCAPE).effects == (Effect("activated", "fetch", 2, cost="2 T Sac<1/CARDNAME>"),)
    assert _read(KROSAN_VERGE).effects == (Effect("activated", "fetch", 2, cost="2 T Sac<1/CARDNAME>"),)
    assert _read(WINDSWEPT_HEATH).effects == (Effect("activated", "fetch", 1, cost="T PayLife<1> Sac<1/CARDNAME>"),)
    for script in (EVOLVING_WILDS, MYRIAD_LANDSCAPE, KROSAN_VERGE, WINDSWEPT_HEATH):
        assert _read(script).unread == ()


def test_triggered_and_creature_fetches():
    assert _read(SPRINGBLOOM_DRUID).effects == (Effect("etb", "fetch", 2, cost="Sac<1/Land>"),)
    assert _read(SAKURA_TRIBE_ELDER).effects == (Effect("activated", "fetch", 1, cost="Sac<1/CARDNAME>"),)


def test_ramp_with_sacrifice_step():
    roiling = _read(ROILING_REGROWTH)
    assert (roiling.ramp_to_battlefield, roiling.ramp_to_hand, roiling.ramp_sacrifice_lands) == (2, 0, 1)
    assert roiling.land_search and roiling.effects == () and roiling.unread == ()
    entish = _read(ENTISH_RESTORATION)
    assert (entish.ramp_to_battlefield, entish.ramp_to_hand, entish.ramp_sacrifice_lands) == (2, 0, 1)
    assert len(entish.unread) == 1 and "read as 2" in entish.unread[0] and entish.land_search
    assert _read(HARROW).land_search and _read(CULTIVATE).land_search
    assert not _read(LIFE_FROM_THE_LOAM).land_search and not _read(SPLENDID_RECLAMATION).land_search


def test_gitrog_full():
    ce = _read(GITROG)
    assert ce.effects == (Effect("upkeep", "sacrifice_land", 1), Effect("land_milled", "draw", 1),
                          Effect("land_sacrificed", "draw", 1), Effect("static", "extra_land", 1))
    assert ce.unread == () and ce.partial is False


def test_titania():
    assert _read(TITANIA).effects == (Effect("etb", "return_lands", 1), Effect("land_sacrificed", "token", 1, 5, 3, "Elemental"))


def test_explore_draws():
    ce = _read(EXPLORE)
    assert ce.effects == (Effect("cast", "extra_land", 1), Effect("cast", "draw", 1)) and ce.unread == ()


def test_stage2_negatives():
    mending = _read(THE_MENDING_OF_DOMINARIA)
    assert mending.effects == () and any(u.startswith("K:Chapter") for u in mending.unread)
    assert _read(ETERNAL_WITNESS).effects == ()
    knight = _read(KNIGHT_OF_THE_RELIQUARY)
    assert knight.effects == () and len(knight.unread) == 2
    thalia = _read(THALIA_AND_GITROG)
    assert thalia.effects == (Effect("static", "extra_land", 1),) and thalia.partial is True
    assert _read(AZUSA_NOT_YOU).effects == () and _read(AZUSA_NOT_YOU).unread
    assert _read(SPRINGBLOOM_WITH_MANA).effects == () and _read(SPRINGBLOOM_WITH_MANA).unread


def test_parse_effects_table_stage2():
    raw = [{"on": "activated", "do": "return_lands", "n": "all", "cost": "3 G Sac<1/CARDNAME>"},
           {"on": "static", "do": "dredge", "n": 2, "type": "lands"}]
    assert parse_effects_table(raw) == (Effect("activated", "return_lands", "all", cost="3 G Sac<1/CARDNAME>"),
                                        Effect("static", "dredge", 2, type="lands"))


def test_land_milled_return():
    ce = _read(HEDGE_SHREDDER)
    assert ce.effects == (Effect("land_milled", "return_lands", "milled"),) and ce.partial is True
    assert any("Attacks" in u for u in ce.unread) and any(u.startswith("K:Crew") for u in ce.unread)
    opp = _read(HEDGE_SHREDDER_OPP)
    assert opp.effects == () and any("Land.OppCtrl" in u for u in opp.unread)


def test_dies_trigger():
    ce = _read(WORLD_SHAPER)
    assert ce.effects == (Effect("dies", "return_lands", "all"),) and ce.partial is True


def test_reanimation():
    creature = (Effect("cast", "reanimate", 1, type="creature"),)
    dread = _read(DREAD_RETURN)
    assert dread.effects == creature and dread.partial is True and any(u.startswith("K:Flashback") for u in dread.unread)
    ce = _read(REANIMATE)
    assert ce.effects == creature and ce.unread == ()
    titan = _read(SUN_TITAN)
    assert titan.effects == (Effect("etb", "reanimate", 1, type="permanent", mv_max=3),) and titan.partial is True
    sevinne = _read(SEVINNES_RECLAMATION)
    assert sevinne.effects == (Effect("cast", "reanimate", 1, type="permanent", mv_max=3),) and sevinne.partial is True
    assert _read(EERIE_ULTIMATUM).effects == ()
    uncapped = _read(SUN_TITAN.replace("Permanent.YouCtrl+cmcLE3", "Permanent.YouCtrl"))
    assert uncapped.effects == (Effect("etb", "reanimate", 1, type="permanent"),)


def test_draw_abilities():
    canopy = _read(HORIZON_CANOPY)
    assert canopy.effects == (Effect("activated", "draw", 1, cost="1 T Sac<1/CARDNAME>"),) and canopy.unread == ()
    assert _read(CORRUPTED_CONVICTION).effects == (Effect("cast", "draw", 2, cost="B Sac<1/Creature>"),)
    other = _read(GITROG.replace("Defined$ You | NumCards$ 1", "Defined$ Player | NumCards$ 1"))
    assert not any(e.do == "draw" for e in other.effects) and other.unread


def test_stage3_negatives():
    roots = _read(INSIDIOUS_ROOTS)
    assert roots.effects == () and len(roots.unread) == 2
    zuran = "Name:Zuran Orb\nTypes:Artifact\nA:AB$ GainLife | Cost$ Sac<1/Land> | LifeAmount$ 2\n"
    assert _read(zuran).effects == () and _read(zuran).unread


def test_parse_effects_table_stage3():
    raw = [{"on": "cast", "do": "reanimate", "n": 2, "type": "creature", "cost": "Sac<1/Creature>"},
           {"on": "etb", "do": "reanimate", "type": "permanent", "mv_max": 3},
           {"on": "land_milled", "do": "return_lands", "n": "milled"}]
    assert parse_effects_table(raw) == (Effect("cast", "reanimate", 2, type="creature", cost="Sac<1/Creature>"),
                                        Effect("etb", "reanimate", 1, type="permanent", mv_max=3),
                                        Effect("land_milled", "return_lands", "milled"))
    for bad in ({"on": "etb", "do": "return_lands", "n": "milled"}, {"on": "land_milled", "do": "draw", "n": "milled"}):
        with pytest.raises(ValueError, match="milled"):
            parse_effects_table([bad])


def test_reanimate_table_type_and_mv_max_are_validated():
    for bad in ({"on": "cast", "do": "reanimate", "type": "artifact"}, {"on": "cast", "do": "reanimate"},
                {"on": "etb", "do": "reanimate", "type": "Creature"}):
        with pytest.raises(ValueError, match="type"):
            parse_effects_table([bad])
    with pytest.raises(ValueError, match="mv_max"):
        parse_effects_table([{"on": "etb", "do": "reanimate", "type": "permanent", "mv_max": -1}])
    assert parse_effects_table([{"on": "etb", "do": "reanimate", "type": "permanent", "mv_max": 0}])[0].mv_max == 0
