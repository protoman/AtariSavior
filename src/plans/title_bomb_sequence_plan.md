# Title Bomb Sequence Plan

## Goal

Extend the existing title flight into one scripted pass: fly from the left to
the right, land, face left, drop a bomb, walk to screen center, wait for the
game bomb fuse and explosion to finish, walk back to the starting X position,
then face right and hold.

## Implementation

1. Use `$F2` as the title-only phase while `DropTarget=$FD`. Reuse the existing
   flight, then advance through drop, walk-to-center, wait, walk-home, and done.
   Clear the phase before leaving the intro so the existing title SELECT flag
   starts in its expected state.
2. Keep flight sprites from the current title renderer. During grounded
   movement, point at the game's existing `PlayerWalkA`/`PlayerWalkB` frames
   and mirror them using `PlayerDir`.
3. Start the bomb through the game's `BombPacked`/`BombX`/`BombY`/`BombTimer`
   state. `TitleTailAudio` already calls `BombTick`; wait for its state bits to
   return to zero rather than duplicating fuse timing.
4. Render the bomb with GRP1 at its saved position, positioned through
   `SetObjectXPos`. Show the game's four-phase explosion colors only in the
   title player band, then restore black before the footer so copyright stays
   isolated.
5. Keep this demonstration title-only: do not consume gameplay bomb inventory,
   damage room walls, score, or cost a life. Clear temporary bomb state when
   SELECT/RESET exits the intro.

## Verification

- Extend `tools/test_title_demo.py` with phase/order, bomb countdown, final
  position/facing, game-sprite, and fixed-kernel-budget assertions.
- Run `./build.sh`; retain the `sim_bomb_fuse` and `sim_frame_budget` gates.
- Capture a Stella screenshot and check the full sequence, especially bomb
  visibility/explosion and unchanged copyright placement.
