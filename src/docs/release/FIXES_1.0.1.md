# S.A.V.I.O.R. 1.0.1 - fixes since 1.0.0 (for the release notes)

- Fixed levels where the player could fly up into a wall and get stuck with his head in
  it: openings between stacked rooms now match exactly (level 18 room 5, and two more
  places on that level).
- Flooded rooms no longer have an entry or exit at their bottom, so you can no longer
  fly up out of the room below straight into the water.
- Bats no longer sit in an exit gap or floor hole where you could not avoid them.
- Extra miners are never placed within a spider's reach.
- Spiders and moths start in a direction that does not run them into walls or the screen
  edge, also after the generator's repairs.
- Crusher rooms: when you enter a room the crusher restarts in its retract phase, so
  entering from below leaves time to climb through.
- All 20 levels regenerated with the new rules.
- NTSC, PAL60 and PAL builds of the same game.
- Tools: the Map viewer draws the water like the editor/game, the playbot can check for
  forced life losses (`--safe`, `--log`).
