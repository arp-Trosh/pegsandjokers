"""Rich style strings for player colors and UI accents.

These MUST be hex codes, not plain ANSI names like "red" or "blue". Player
color shows up through two different renderers: the board (raw Rich
Style.parse, same as the chat RichLog) and the players panel (a Static,
which resolves markup through Textual's own CSS-style color parser).
Textual's default dark theme remaps the plain ANSI-standard color *names*
to its own curated (Monokai-like) palette for the Rich-native renderers,
but Static's CSS parser resolves the same names to their literal RGB
instead -- so a name like "blue" rendered as purple on the board/chat but
literal blue in the players panel, "yellow" rendered as orange vs literal
yellow, and "red"/"magenta" even collided onto the identical hex on the
board/chat. Hex codes skip that remap and resolve identically everywhere,
which is why "orange" (already hacked to the hex-backed 256-color name
"dark_orange") was the one color that never showed this bug.
"""
import random

PLAYER_STYLES = {
    "red": "#ff5555",
    "blue": "#5599ff",
    "green": "#55cc55",
    "yellow": "#e6c94d",
    "magenta": "#e066e0",
    "cyan": "#4dd0d0",
    "white": "#e8e8e8",
    "orange": "#ff9933",
}


def player_style(color_name):
    return PLAYER_STYLES.get(color_name, PLAYER_STYLES["white"])


def owner_track_style(owner_color):
    """Style for an empty main-track hole. Stays the generic dim grey
    until a player has actually taken that seat, then switches to a
    dimmed version of that seat's player color so each player's 18-hole
    row reads as theirs before any peg has reached it -- "dim" (rather
    than the full-brightness color used for an occupied peg) keeps an
    empty hole visually distinct from one with a peg sitting on it."""
    if owner_color is None:
        return DIM_STYLE
    return f"dim {player_style(owner_color)}"


def owner_home_safe_style(owner_color):
    """Style for an empty HOME/SAFE hole. Stays the generic reversed grey
    block until a player has taken that seat, then reverses to that
    player's own color."""
    if owner_color is None:
        return HOME_SAFE_STYLE
    return f"reverse {player_style(owner_color)}"


def random_colored_markup(text):
    """Wrap each non-space character of `text` in a random player color.

    Same effect as the main menu's "Pegs and Jokers" title -- reused
    wherever else that same playful per-character coloring is wanted.
    """
    names = list(PLAYER_STYLES)

    def markup_char(ch):
        if ch == " ":
            return " "
        # A literal "[" is otherwise indistinguishable from the start of a
        # markup tag to Textual's parser, so it must be escaped -- "]" needs
        # no such treatment since it's only special *inside* an open tag.
        escaped = "\\[" if ch == "[" else ch
        return f"[{player_style(random.choice(names))}]{escaped}[/]"

    return "".join(markup_char(ch) for ch in text)


# Also cross-rendered on both the board (Style.parse) and the players panel
# (Static) -- for disconnected players -- so it needs the same hex treatment
# as PLAYER_STYLES above, not the named "grey50" it used to be (which
# silently fell back to unstyled/undimmed text in the players panel).
DIM_STYLE = "#808080"
HOME_SAFE_STYLE = "reverse grey78"
HIGHLIGHT_STYLE = "black on yellow bold"
TURN_STYLE = "black on green bold"
GAME_MSG_STYLE = "grey70"
