# Pegs and Jokers

A networked, terminal-based version of **Pegs and Jokers**, the partnership
board game played with pegs and playing cards. Built in Python with
[Textual](https://textual.textualize.io/), so it runs in any modern terminal
on Windows, macOS, and Linux, and friends can join over the network.

## Features

- **2, 4, 6, or 8 players** (2-player games are played without jokers; 6 and
  8 players use an experimental "wonky" board)
- **Team play** for 4+ players, with partners seated across from each other
- **Host or join** from the start screen, no separate server needed
- **Built-in chat**, plus `/rules` for a full rules reference in-game
- Each player's section of the board is colored and turned so it faces the
  bottom of their screen
- Mouse and keyboard controls

## Download (Windows)

Get `PegsAndJokers-windows.zip` from the
[latest release](https://github.com/arp-Trosh/pegsandjokers/releases/latest),
unzip it, and run `PegsAndJokers.exe` from inside the extracted
`PegsAndJokers` folder.

The build isn't code-signed, so SmartScreen may say *"Windows protected your
PC"*. Click **More info → Run anyway**. Each release includes a SHA-256
checksum if you want to verify the download. For the best experience,
install [Windows Terminal](https://aka.ms/terminal); the game opens in it
automatically when it's available.

## Run from source

Requires Python 3.10 or newer.

```sh
git clone https://github.com/arp-Trosh/pegsandjokers.git
cd pegsandjokers
python -m venv .venv
.venv/bin/pip install .          # Windows: .venv\Scripts\pip install .
.venv/bin/pegsandjokers          # or: python -m pegsandjokers
```

## Playing a game

1. **One player hosts.** Choose *Host*, pick the number of players, a port
   (default `5555`), your name, and your color, then click **Connect**.
2. **Everyone else joins.** Choose *Join* and enter the host's IP address
   and port. Players on other machines need the host's port to be reachable
   (same LAN, or port forwarding / a VPN such as Tailscale).
3. **Pick teams** in the lobby (4+ players). Teams must be balanced, two
   players each.
4. **The host begins** the game once everyone has joined.

### Controls

| Key | Action |
|---|---|
| `1`–`5` | Pick a card from your hand |
| Click | Choose a peg or destination space |
| `c` | Cancel the current selection |
| `x` | Discard (when you have no legal move) |
| `t` | Change team (lobby) |
| `b` / `r` / `e` | Host only: begin, restart, or end the game |
| `q` | Quit |

Type in the chat box to talk to other players. `/rules` shows the rules.

## Rules in brief

Move all five of your pegs from **HOME**, around the track, and into your
**SAFE** area. With partners, a team wins once both players have all their
pegs in SAFE.

- **Getting out:** an Ace, face card, or Joker moves a peg from HOME to the
  COME OUT SPOT.
- **Cards move forward by their value** (Ace = 1, Jack = 11, Queen = 12,
  King = 13), with these exceptions:
  - **7** can be split between two pegs, both moving forward.
  - **8** moves *backward* eight.
  - **9** can be split: one peg forward, the other backward.
  - **Joker** jumps one of your pegs onto any other player's peg in play,
    sending that peg home.
- Landing on an **opponent** sends their peg back HOME. Landing on your
  **partner** sends their peg to its IN SPOT, the hole just before their SAFE area.
- You can't pass or land on your own pegs, and you can't back into SAFE.
- You must move if you can (except for a Joker) and must use the card's full count.
- Once your pegs are all SAFE, you play your partner's pegs.
- No table talk!

The full official rules are in
[How-to-Play-Pegs-and-Jokers.pdf](How-to-Play-Pegs-and-Jokers.pdf) and in the
game via `/rules`.

## Project layout

```
pegsandjokers/
  game/    board geometry, cards, rules, game state
  net/     TCP server, client, and line-based JSON protocol
  ui/      Textual screens and widgets
board_designer/   standalone tool for hand-laying out the 6/8-player boards
scripts/          Windows build helpers (PyInstaller entry point, version info)
```

The [board designer](board_designer/README.md) is a separate TUI for
improving the 6- and 8-player board layouts.

## Building the Windows executable

The [GitHub Actions workflow](.github/workflows/build-windows.yml) builds the
Windows `.exe` with PyInstaller on every push to `main`. Pushing a `v*` tag
also publishes a GitHub release with the zipped build and a checksum.
