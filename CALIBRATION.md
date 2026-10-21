# Calibration table

Simulator reference numbers for the six frozen fixtures in `tests/fixtures/`, at 20 000 games
with each deck's own seed (`uv run edhpower --from-facts tests/fixtures/<deck>.facts.json`).
This is a reference table, not a set of assertions: `tests/test_golden.py` pins the 500-game
numbers. Only compare rows with the same `config_version` and `sim_version`.

`win` is the first turn of table lethal (3 opponents × 40 life, combat and drain) or a lethal
combo; `fast` is the turn by which 5% of games got there; `>T12` means fewer than half (or, for
`fast`, fewer than 5%) of games reached it by turn 12. `combat` is 40 cumulative combat damage
to one opponent, counting effective power (tokens, counters, anthems, pumps).

## Simulator (config 1, sim v3, 2026-10-21, 20 000 games)

| deck | sim | win median | win fast | lethal_table median | combat median |
|---|---|---|---|---|---|
| necrobloom-v3 | 3 | >T12 | T11 | >T12 | T10 |
| precon-eldrazi-unbound | 3 | >T12 | T11 | >T12 | T9 |
| ulalek-b5 | 3 | >T12 | T12 | >T12 | >T12 |
| ulalek-bracket3-v2 | 3 | >T12 | T12 | >T12 | T11 |
| ulalek-bracket4-v2 | 3 | >T12 | T8 | >T12 | >T12 |
| zhulodok-bracket3 | 3 | T12 | T10 | T12 | T9 |

Win route (share of games won by T12): necrobloom-v3 combat 30%; precon-eldrazi-unbound combat
30%; ulalek-b5 combo 6%; ulalek-bracket3-v2 combat 9%; ulalek-bracket4-v2 combo 15%;
zhulodok-bracket3 combat 53%. Forge pin `33aecdd6adac36a42af9eab75d2e654626a0e7db`.

## Simulator (config 1, sim v4, 2026-10-21, 20 000 games)

Stage 2: graveyard, sacrifice and mill, several land drops, lands played from the graveyard,
fetch lands, activated abilities, upkeep land sacrifice, dredge, land chains, mass land return,
and instants/sorceries with a read effect (the `spell` role).

| deck | sim | win median | win fast | lethal_table median | combat median |
|---|---|---|---|---|---|
| necrobloom-v3 | 4 | >T12 | T10 | >T12 | T10 |
| precon-eldrazi-unbound | 4 | >T12 | T11 | >T12 | T9 |
| ulalek-b5 | 4 | >T12 | T12 | >T12 | >T12 |
| ulalek-bracket3-v2 | 4 | >T12 | T12 | >T12 | T10 |
| ulalek-bracket4-v2 | 4 | >T12 | T8 | >T12 | T12 |
| zhulodok-bracket3 | 4 | T12 | T10 | T12 | T9 |

Win route (share of games won by T12): necrobloom-v3 combat 47%; precon-eldrazi-unbound combat
31%; ulalek-b5 combo 6%; ulalek-bracket3-v2 combat 11%; ulalek-bracket4-v2 combo 17%;
zhulodok-bracket3 combat 54%. Forge pin `33aecdd6adac36a42af9eab75d2e654626a0e7db`.

Where the Eldrazi decks moved earlier, the cause is cards that stage 2 now reads. The fetch
lands in the two Ulalek lists (Misty Rainforest, Scalding Tarn, Wooded Foothills, Urza's Cave)
were 0-mana lands in sim v3; they now fetch a tapped 1-mana land. That moves ulalek-bracket3-v2
combat from T11 to T10 and ulalek-bracket4-v2 combat from >T12 to T12. Stripping those effects
gives the v3 medians back (checked at the 500-game golden count).

Necrobloom's win median stays >T12. It plays one land in about 80% of its turns (1.3 lands
enter per turn on average). Its reanimation and draw engines are stage 3, and the Gitrog loop
is not modelled (see the block below).

### necrobloom-v3 benchmark (sim v4)

**Stamps:** edhpower 0.3.0 · config 1 · profiles edhpowerlevel-2026-08 / v1 · sim v4 · 20 000 games ·
seed 1189066043824635889 · tags ok · Spellbook 6.4.0 · 100/100 cards resolved · Forge
`33aecdd6adac36a42af9eab75d2e654626a0e7db`

Reproduce with `uv run edhpower --from-facts tests/fixtures/necrobloom-v3.facts.json --iterations 20000`.

```
Goldfish simulation (sim v4, 20000 games, seed 1189066043824635889)
  clock                                                median  fast    T2    T3    T4    T5    T6    T7    T8    T9    T10   T11   T12  
  win (table lethal or lethal combo)                   >T12    T10       0%    0%    0%    0%    0%    0%    0%    3%   12%   27%   47% 
  lethal to the table (3 × 40, combat and drain)       >T12    T10       0%    0%    0%    0%    0%    0%    0%    3%   12%   27%   47% 
  first opponent dead (40 life, combat and drain)      >T12    T10       0%    0%    0%    0%    0%    0%    1%    4%   12%   28%   49% 
  commander castable                                   T4      T3        0%   13%   53%   78%   87%   92%   94%   96%   97%   98%   99% 
  7 mana available                                     T6      T5        0%    0%    5%   23%   51%   73%   85%   90%   93%   95%   96% 
  3 mana available (closed-form tipping target)        T3      T1       23%   69%   96%   98%   99%   99%  100%  100%  100%  100%  100% 
  MV 7+ spell cast from hand                           >T12    T7        0%    0%    0%    1%    4%    9%   13%   16%   18%   20%   22% 
  40 combat damage to one opponent (no blockers)       T10     T8        0%    0%    0%    0%    0%    2%   17%   50%   77%   90%   95% 
  combo line assembled                                 >T12    >T12      0%    0%    0%    0%    0%    0%    0%    0%    0%    0%    0% 
  lethal combo line assembled                          >T12    >T12      0%    0%    0%    0%    0%    0%    0%    0%    0%    0%    0% 
  avg mana produced                                                     2.0   3.1   4.3   5.5   6.5   7.5   8.5   9.5  10.4  11.3  12.4 
  share of games casting nothing                                        60%   32%   15%   12%   17%   30%   47%   60%   68%   70%   74% 
  damage this turn                                                      0.0   0.2   0.7   1.9   4.3   8.3  13.4  19.1  25.1  31.8  38.7 
  board power                                                           0.0   0.1   0.6   1.8   4.0   7.7  12.6  18.1  24.0  30.4  37.5 
  lands on battlefield                                                  2.2   3.4   4.5   5.4   6.4   7.3   8.2   9.1   9.9  11.0  11.8 
  lands entering this turn                                              1.3   1.4   1.3   1.2   1.2   1.3   1.3   1.3   1.3   1.6   1.4 
  lands in graveyard                                                    0.1   0.4   0.6   0.8   0.9   1.1   1.3   1.5   1.8   1.8   2.2 
  distinct land names                                                   2.1   3.2   4.2   5.1   5.9   6.7   7.4   8.1   8.8   9.7  10.3 
  tokens: Beast                                                         0.0   0.0   0.0   0.0   0.0   0.1   0.2   0.3   0.4   0.6   0.8 
  tokens: Bird                                                          0.0   0.0   0.0   0.0   0.0   0.1   0.2   0.3   0.5   0.6   0.8 
  tokens: Cat Beast                                                     0.0   0.0   0.0   0.0   0.0   0.1   0.2   0.3   0.4   0.6   0.8 
  tokens: Elemental                                                     0.0   0.0   0.0   0.0   0.0   0.0   0.1   0.1   0.2   0.2   0.3 
  tokens: Insect                                                        0.0   0.0   0.0   0.1   0.1   0.2   0.3   0.5   0.6   0.8   1.0 
  tokens: Plant                                                         0.0   0.0   0.1   0.6   1.2   1.8   2.2   2.5   2.7   2.8   3.0 
  tokens: Zombie                                                        0.0   0.0   0.0   0.1   0.5   1.3   2.2   3.3   4.5   6.0   7.2 
  win route: combat 47% · combo 0% · none 53%
  biggest swing (median) 29
  lines simulated: none
  not simulated: The Gitrog Monster + The Necrobloom (notable prerequisites)
  payoffs: go-wide finisher: Rumbleweed; token drain: Mirkwood Bats; landfall drain: Retreat to Hagra; landfall tokens (fuel): Emeria Angel, Felidar Retreat, Rampaging Baloths, Scute Swarm, … (+2)
  model coverage: lands 40 · rocks 3 · dorks 0 · one-shot 2 · reducers 1 · ramp spells 8 · draw spells 1 · tutors 2 · threats 2 · creatures 22 · engines 0 · other permanents 9 · spells 3 · held 6 · unmodelled 25
  effects: table 0 (none) · forge 60 · unmodelled: Assassin's Trophy, Beast Within, Corrupted Conviction, Dread Return, … (+21) · partial: Ancient Greenwarden, Entish Restoration, Explore, Felidar Retreat, … (+7)
  not modelled: fetch then dredge in one turn (Gitrog loop), Sylvan Library dredges, Field of the Dead counting lands that enter with it, Saga chapters, attack triggers, life as a resource, Room cards, reanimation, blockers/interaction
  note: on the play, 20000 games, seed 1189066043824635889; one London mulligan when the opener holds fewer than 2 or more than 5 lands; no opponent, no interaction; combat counts printed power, counters, anthems and pumps cast for lethal; tokens attack from the turn after they enter; no haste, no blockers; colours are enforced
  note: tokens entering do not fire token-making creature-enters effects, and token-created triggers do not make more tokens
  note: lands fetched by ramp spells enter tapped
  note: attackers are assigned greedily to the opponent with the most life, not optimally
  note: at most one pump spell is cast per turn, and only when it kills an opponent
  note: a pump spell cast for another role (a threat, a draw tag) does not apply its pump
  note: lands returned from the graveyard enter tapped, one at a time
  note: fetch lands find a 1-mana land, tapped; free fetches are cracked the turn they enter
  note: dredge replaces the draw only when the hand lacks a land for this turn's drops, never the opening hand
  note: mass land return is cast with 4+ lands in the graveyard and a landfall source out, or on the last two turns
  note: activated abilities are paid from mana left after the main phase
  note: a draw granted by a trigger is a plain draw, never a dredge
  note: no maximum hand size
  note: 6 instant/sorcery card(s) with no modelled effect are never cast (a goldfish has nothing to interact with)
  note: 25 nonland card(s) have no effect the model applies (script lines it does not read): ["Assassin's Trophy", 'Beast Within', 'Corrupted Conviction', 'Dread Return']…
  note: 11 card(s) modelled in part (a mode, branch or script line is skipped): ['Ancient Greenwarden', 'Entish Restoration', 'Explore', 'Felidar Retreat']…
  note: 0 of 1 Spellbook line(s) simulated; the rest are listed as not simulated, not assumed free
```

## Simulator (config 1, sim v5, 2026-10-21, 20 000 games)

Stage 3: reanimation, land-milled and dies triggers, triggered draw, and the `reanimate` clock
(first creature returned from the graveyard to the battlefield).

| deck | sim | win median | win fast | lethal_table median | combat median | reanimate by T12 |
|---|---|---|---|---|---|---|
| necrobloom-v3 | 5 | T12 | T10 | T12 | T9 | 14% |
| precon-eldrazi-unbound | 5 | >T12 | T11 | >T12 | T9 | 0% |
| ulalek-b5 | 5 | >T12 | T12 | >T12 | >T12 | 0% |
| ulalek-bracket3-v2 | 5 | >T12 | T12 | >T12 | T10 | 0% |
| ulalek-bracket4-v2 | 5 | >T12 | T8 | >T12 | T12 | 0% |
| zhulodok-bracket3 | 5 | T12 | T10 | T12 | T9 | 0% |

Win route (share of games won by T12): necrobloom-v3 combat 54%; precon-eldrazi-unbound combat
32%; ulalek-b5 combo 6%; ulalek-bracket3-v2 combat 11%; ulalek-bracket4-v2 combo 17%;
zhulodok-bracket3 combat 54%. Forge pin `33aecdd6adac36a42af9eab75d2e654626a0e7db`.

No Eldrazi deck's clock moved. Necrobloom's win median moved from >T12 to T12 (47% to 54% of
games won by T12), and its combat median moved from T10 to T9. Stripping the stage-3 effects
from the deck (reanimation, every draw effect, land-milled and dies triggers) gives back the v4
values at 20 000 games: win >T12 (45%) and combat T10. Stripping one group at a time shows each
group's share of the 54%:

| stripped | win by T12 |
|---|---|
| The Gitrog Monster's land-milled and land-sacrificed draws | 50% |
| reanimation (Dread Return, Victimize, Sun Titan, Sevinne's Reclamation) | 52% |
| land-milled and dies land returns (Hedge Shredder, World Shaper) | 53% |
| other draws (Explore, Spelunking) | 53% |

The binding limit is unchanged: the win needs 120 combat damage, and the hand still runs dry
(62% of games cast nothing on T12, down from 74%).

### necrobloom-v3 benchmark (sim v5)

**Stamps:** edhpower 0.3.0 · config 1 · profiles edhpowerlevel-2026-08 / v1 · sim v5 · 20 000 games ·
seed 1189066043824635889 · tags ok · Spellbook 6.4.0 · 100/100 cards resolved · Forge
`33aecdd6adac36a42af9eab75d2e654626a0e7db`

Reproduce with `uv run edhpower --from-facts tests/fixtures/necrobloom-v3.facts.json --iterations 20000`.

```
Goldfish simulation (sim v5, 20000 games, seed 1189066043824635889)
  clock                                                   median  fast    T2    T3    T4    T5    T6    T7    T8    T9    T10   T11   T12  
  win (table lethal or lethal combo)                      T12     T10       0%    0%    0%    0%    0%    0%    1%    5%   15%   33%   54% 
  lethal to the table (3 × 40, combat and drain)          T12     T10       0%    0%    0%    0%    0%    0%    1%    5%   15%   33%   54% 
  first opponent dead (40 life, combat and drain)         T12     T10       0%    0%    0%    0%    0%    0%    1%    5%   16%   35%   56% 
  commander castable                                      T4      T3        0%   13%   52%   78%   87%   91%   94%   96%   97%   98%   99% 
  7 mana available                                        T6      T5        0%    0%    5%   23%   50%   74%   86%   91%   95%   97%   98% 
  3 mana available (closed-form tipping target)           T3      T1       23%   69%   96%   98%   99%   99%  100%  100%  100%  100%  100% 
  MV 7+ spell cast from hand                              >T12    T7        0%    0%    0%    1%    4%    9%   13%   17%   20%   22%   25% 
  40 combat damage to one opponent (no blockers)          T9      T8        0%    0%    0%    0%    0%    2%   18%   52%   78%   90%   95% 
  combo line assembled                                    >T12    >T12      0%    0%    0%    0%    0%    0%    0%    0%    0%    0%    0% 
  lethal combo line assembled                             >T12    >T12      0%    0%    0%    0%    0%    0%    0%    0%    0%    0%    0% 
  creature returned from the graveyard to the battlefield >T12    T8        0%    0%    0%    0%    2%    3%    5%    8%   10%   12%   14% 
  avg mana produced                                                        2.0   3.1   4.3   5.5   6.5   7.6   8.6   9.7  10.8  12.0  13.3 
  share of games casting nothing                                           61%   33%   16%   12%   17%   28%   43%   53%   59%   59%   62% 
  damage this turn                                                         0.0   0.2   0.7   1.9   4.3   8.5  14.1  21.0  29.2  39.0  50.3 
  board power                                                              0.0   0.1   0.6   1.8   4.0   7.9  13.2  19.8  27.6  37.0  48.0 
  lands on battlefield                                                     2.2   3.4   4.5   5.4   6.4   7.4   8.4   9.4  10.5  11.8  12.9 
  lands entering this turn                                                 1.3   1.4   1.3   1.2   1.2   1.3   1.4   1.5   1.6   1.9   1.7 
  lands in graveyard                                                       0.1   0.4   0.6   0.8   0.9   1.1   1.3   1.5   1.7   1.7   2.1 
  distinct land names                                                      2.1   3.2   4.2   5.1   5.9   6.7   7.6   8.4   9.3  10.3  11.1 
  tokens: Beast                                                            0.0   0.0   0.0   0.0   0.0   0.1   0.2   0.4   0.5   0.8   1.1 
  tokens: Bird                                                             0.0   0.0   0.0   0.0   0.0   0.1   0.2   0.4   0.5   0.8   1.0 
  tokens: Cat Beast                                                        0.0   0.0   0.0   0.0   0.0   0.1   0.2   0.3   0.5   0.7   1.0 
  tokens: Elemental                                                        0.0   0.0   0.0   0.0   0.0   0.0   0.1   0.1   0.2   0.3   0.4 
  tokens: Insect                                                           0.0   0.0   0.0   0.1   0.1   0.2   0.4   0.5   0.7   1.0   1.3 
  tokens: Plant                                                            0.0   0.0   0.1   0.6   1.3   1.9   2.3   2.6   2.9   3.0   3.3 
  tokens: Zombie                                                           0.0   0.0   0.0   0.1   0.5   1.3   2.4   3.8   5.2   7.0   8.7 
  win route: combat 54% · combo 0% · none 46%
  biggest swing (median) 34
  lines simulated: none
  not simulated: The Gitrog Monster + The Necrobloom (notable prerequisites)
  payoffs: go-wide finisher: Rumbleweed; token drain: Mirkwood Bats; landfall drain: Retreat to Hagra; landfall tokens (fuel): Emeria Angel, Felidar Retreat, Rampaging Baloths, Scute Swarm, … (+2)
  model coverage: lands 40 · rocks 3 · dorks 0 · one-shot 2 · reducers 1 · ramp spells 8 · draw spells 0 · tutors 2 · threats 2 · creatures 22 · engines 0 · other permanents 9 · spells 7 · held 3 · unmodelled 17
  effects: table 1 (Victimize) · forge 59 · unmodelled: Assassin's Trophy, Beast Within, Druid Class, Eerie Ultimatum, … (+13) · partial: Ancient Greenwarden, Dread Return, Entish Restoration, Felidar Retreat, … (+11)
  not modelled: fetch then dredge in one turn (Gitrog loop), Sylvan Library dredges, Field of the Dead counting lands that enter with it, Saga chapters, attack triggers, life as a resource, Room cards, blockers/interaction
  note: on the play, 20000 games, seed 1189066043824635889; one London mulligan when the opener holds fewer than 2 or more than 5 lands; no opponent, no interaction; combat counts printed power, counters, anthems and pumps cast for lethal; tokens attack from the turn after they enter; no haste, no blockers; colours are enforced
  note: tokens entering do not fire token-making creature-enters effects, and token-created triggers do not make more tokens
  note: lands fetched by ramp spells enter tapped
  note: attackers are assigned greedily to the opponent with the most life, not optimally
  note: at most one pump spell is cast per turn, and only when it kills an opponent
  note: a pump spell cast for another role (a threat, a draw tag) does not apply its pump
  note: lands returned from the graveyard enter tapped, one at a time
  note: fetch lands find a 1-mana land, tapped; free fetches are cracked the turn they enter
  note: dredge replaces the draw only when the hand lacks a land for this turn's drops, never the opening hand
  note: mass land return is cast with 4+ lands in the graveyard and a landfall source out, or on the last two turns
  note: activated abilities are paid from mana left after the main phase
  note: a draw granted by a trigger is a plain draw, never a dredge
  note: reanimation targets the highest-MV eligible card; a reanimation spell is cast only for a creature with MV 7+ or power 4+
  note: a sacrifice cost takes a creature whose death returns lands, else a token, else the smallest creature
  note: no maximum hand size
  note: 3 instant/sorcery card(s) with no modelled effect are never cast (a goldfish has nothing to interact with)
  note: 17 nonland card(s) have no effect the model applies (script lines it does not read): ["Assassin's Trophy", 'Beast Within', 'Druid Class', 'Eerie Ultimatum']…
  note: 15 card(s) modelled in part (a mode, branch or script line is skipped): ['Ancient Greenwarden', 'Dread Return', 'Entish Restoration', 'Felidar Retreat']…
  note: 0 of 1 Spellbook line(s) simulated; the rest are listed as not simulated, not assumed free
```
