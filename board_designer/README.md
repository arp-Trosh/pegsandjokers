# Board Designer

A standalone WYSIWYG TUI for hand-designing the 6- and 8-player Pegs &
Jokers board layouts. It is **not part of the `pegsandjokers` package** --
it doesn't import it and the game doesn't import this. The two only agree
on a JSON file format (below), so this tool can be used entirely on its
own, and its output can be handed to a future Claude Code session to wire
into the game.

## Why this exists

The game draws its 6- and 8-player boards by pure trigonometry (a regular
hexagon/octagon, see `pegsandjokers/game/board.py::Layout`), and the result
looks bad -- HOME/SAFE clusters crowd, overlap, or land at odd angles.
Describing a better layout in words is hard. This tool lets you drag every
hole to exactly where you want it, live, in a terminal, and save the
result as data.

## Running it

From the repo root, using the project's existing virtualenv (it already
has `textual` installed):

```
.venv/bin/python -m board_designer                # starts on the 6-player board
.venv/bin/python -m board_designer --players 8     # starts on the 8-player board
.venv/bin/python -m board_designer --load board_designer/layouts/8player.json
```

## What you're looking at

The canvas seeds itself with the game's current (imperfect) auto-generated
layout, so you have a real starting point instead of a blank grid. Each
space is a small colored glyph:

- `.` dim colored dot -- an ordinary main-track hole
- `H` bold colored letter -- the COME OUT SPOT, the one track hole per seat
  a peg leaves the main track from to enter that seat's HOME row
- `S` bold colored letter -- the IN SPOT, the one track hole per seat a peg
  leaves the main track from to enter that seat's SAFE area
- `o` bold colored dot -- a HOME cluster hole
- `+` bold colored dot -- a SAFE line hole

Color = which seat/arm the space belongs to (up to 8 distinct colors,
cycling in the same order the game uses: red, blue, green, yellow,
magenta, cyan, white, orange).

One space is always **selected** (shown highlighted in yellow). Moving the
selection moves either just that one space, its whole cluster (all 5 HOME
or all 5 SAFE dots of that seat), or that whole seat's arm (all 18 track
holes + HOME + SAFE), depending on the current **move scope** (shown in
the side panel, cycled with `g`). Everything currently in scope is shown
with a grey box behind it.

Any cell shared by two or more spaces is flagged in red -- the game
requires every space to have its own cell, so clear all red before treating
a layout as finished.

## Keybindings

| Key | Action |
|---|---|
| Arrow keys / `h j k l` | Move the current selection/scope 1 cell |
| Shift + `H J K L` | Move 5 cells at once |
| `Tab` / `Shift+Tab` | Select next / previous space (cycles seat by seat: arm holes, then HOME, then SAFE) |
| Click | Select whichever space is under the pointer |
| `g` | Cycle move scope: single space -> whole cluster -> whole seat/arm |
| `u` | Undo last move/reset (many levels) |
| `c` | Re-center the view on the current selection |
| `s` | Save current layout to a JSON file (prompts for a path) |
| `o` | Open a previously saved layout JSON file |
| `n` | Switch between the 6-player and 8-player board (reseeds, asks to confirm) |
| `Shift+R` | Reset the current board back to the seeded layout (asks to confirm) |
| `q` | Quit |

Layouts save to `board_designer/layouts/6player.json` and
`.../8player.json` by default; the save/open prompt lets you type any
other path.

## File format

```json
{
  "num_players": 8,
  "slots": 8,
  "arm_len": 18,
  "home_count": 5,
  "safe_count": 5,
  "positions": {
    "track:0": [12, 40],
    "home:3:2": [5, 22],
    "safe:5:4": [30, 18],
    "...": "one entry per space"
  }
}
```

- `positions` keys: `"track:<gid>"` where `gid` is `0 .. slots*arm_len - 1`
  (which board-wide hole on the shared ring), or `"<home|safe>:<seat>:<i>"`
  where `seat` is `0 .. slots - 1` and `i` is `0 .. home_count-1` /
  `0 .. safe_count-1`.
- Values are `[row, col]` integer grid cells. Rows grow downward, columns
  grow rightward, same convention `pegsandjokers/game/board.py::Layout`
  already uses. There's no meaning to the absolute row/col numbers or the
  canvas size -- only the *relative* positions of spaces to each other
  matter, since the game's `BoardView` scrolls to fit whatever size the
  layout comes out to.
- `seat` here matches the game's seat numbering: for 6- and 8-player games
  `seat == player index`, so `home:3:*` is player 3's HOME cluster.

A saved file is only meaningful once every space for that player count is
present exactly once and no two spaces share a cell (i.e. `board_designer`
showed zero red collisions when you saved it) -- `models.load()` already
checks that the space set is complete before accepting a file, but it
can't check for zero collisions, so re-open a saved file and glance at the
canvas before handing it off.

## Handing this off to the game

This tool intentionally stops at "here's a JSON file of hole positions" --
it doesn't touch `pegsandjokers/game/board.py`. To actually use a designed
layout in-game, a future session needs to:

1. Load the saved JSON (`board_designer/layouts/6player.json` and/or
   `8player.json`).
2. Give `game/board.py::Layout` a way to use these fixed positions for 6-
   and/or 8-player boards instead of (or as an override to) the
   trigonometric `_build()` it uses today -- e.g. a branch that, for a
   player count with a saved layout file, loads `positions` straight from
   JSON (translating `"track:<gid>"` / `"<home|safe>:<seat>:<i>"` keys back
   into the `("track", gid)` / `(kind, seat, i)` tuples `Layout.positions`
   already uses) instead of computing them.

The 2-player and 4-player boards already look and play great -- leave
those exactly as they are; only the 6- and 8-player construction should
change.
