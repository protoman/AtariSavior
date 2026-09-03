# Atari 2600 Reference Library

This directory stores local copies of public documentation and open-source
examples used while developing the Atari 2600 HERO-like prototype.

## Sources

### Atari 2600 Memories

Author: Andrew Davie. Public tutorial site:

<https://www.randomterrain.com/atari-2600-memories.html>

`tutorial/` contains the index and sessions 07, 11-17, 19-25. These cover
display timing, initialization, playfields, sprites, positioning, and
vertical movement.

### Stella documentation

Project: Stella emulator, `stella-emu/stella`.

- <https://github.com/stella-emu/stella/blob/master/docs/index.html>
- <https://github.com/stella-emu/stella/blob/master/docs/debugger.html>

These files cover debugger commands, cartridge settings, and TIA diagnostics.

### Assembly examples

Project: `johnidm/asm-atari-2600`.

- Repository: <https://github.com/johnidm/asm-atari-2600>
- README: `examples/asm-atari-2600-README.md`
- Small examples: `hello.asm`, `pong.asm`, `redblue.asm`
- Larger examples: `adventure.asm`, `combat.asm`, `genemedic.asm`,
  `pitfall.asm`, `riverraid.asm`
- Shared support: `macro.h`, `vcs.h`

The examples were downloaded from the repository's public `master` branch.
Check the upstream repository before redistribution or reuse; this collection
is a development reference, not a replacement for upstream license notices.

## Project-specific conclusions

- Start with a plain 4K ROM and a fixed, boring kernel.
- Verify one TIA feature at a time: background color, playfield, one player,
  joystick input, then room transitions.
- Use `CTRLPF=$01` for a reflected playfield. `$00` repeats the left half, and
  `$02` enables score mode rather than reflection.
- Keep playfield and sprite writes inside a measured 76-cycle scanline.
- Use the downloaded examples as references, not as unverified drop-in code.
