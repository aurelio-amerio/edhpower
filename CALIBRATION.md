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
