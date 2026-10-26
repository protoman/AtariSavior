
## 10. Gate and phase rooms are enemy-free (2026-10-26)

User ruling after `screenshots/bugs/enemy_double_kill`: crossing a Gate/Phase
room cost two lives (the gate crush, then the bat the player fell back onto).
`FillRoom` now leaves Gate/Phase rooms empty and the twogap spider pass skips
Phase rooms too. Keys are items and may still sit elsewhere. `test_generator`
fails any phase/door room that carries a non-key enemy.
