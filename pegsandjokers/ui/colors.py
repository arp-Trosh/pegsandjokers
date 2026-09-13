"""curses color pair setup for the 8 player colors plus UI accents."""
import curses

from ..game.state import COLORS

# pair ids
PAIR_GAME_MSG = 20
PAIR_HIGHLIGHT = 21
PAIR_TURN = 22
PAIR_DIM = 23
PAIR_BOARD = 24
PAIR_HOME_SAFE = 25

_COLOR_BASE = {
    "red": curses.COLOR_RED,
    "blue": curses.COLOR_BLUE,
    "green": curses.COLOR_GREEN,
    "yellow": curses.COLOR_YELLOW,
    "magenta": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "white": curses.COLOR_WHITE,
    "orange": curses.COLOR_YELLOW,  # 8-color fallback only; see init_colors()
}

# A real orange from the extended xterm-256 palette (used whenever the
# terminal supports it) instead of just bolding yellow, which read as
# "still yellow" rather than a distinct color.
_ORANGE_256 = 208

_player_pair_id = {}
_orange_is_true_color = False


def init_colors():
    global _orange_is_true_color
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK

    has_256 = False
    try:
        has_256 = curses.COLORS >= 256
    except curses.error:
        has_256 = False

    for i, name in enumerate(COLORS):
        pair_id = 1 + i
        if name == "orange" and has_256:
            try:
                curses.init_pair(pair_id, _ORANGE_256, bg)
                _orange_is_true_color = True
            except curses.error:
                curses.init_pair(pair_id, _COLOR_BASE[name], bg)
        else:
            curses.init_pair(pair_id, _COLOR_BASE[name], bg)
        _player_pair_id[name] = pair_id

    curses.init_pair(PAIR_GAME_MSG, curses.COLOR_WHITE, bg)
    curses.init_pair(PAIR_HIGHLIGHT, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(PAIR_TURN, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(PAIR_DIM, curses.COLOR_WHITE, bg)
    curses.init_pair(PAIR_BOARD, curses.COLOR_WHITE, bg)
    curses.init_pair(PAIR_HOME_SAFE, curses.COLOR_WHITE, bg)


def player_attr(color_name):
    pair_id = _player_pair_id.get(color_name, PAIR_BOARD)
    attr = curses.color_pair(pair_id)
    if color_name == "orange" and not _orange_is_true_color:
        # No 256-color orange available -- fall back to bold yellow so it
        # at least reads as brighter/different from the plain yellow player.
        attr |= curses.A_BOLD
    return attr


def game_msg_attr():
    return curses.color_pair(PAIR_GAME_MSG) | curses.A_DIM


def highlight_attr():
    return curses.color_pair(PAIR_HIGHLIGHT) | curses.A_BOLD


def turn_attr():
    return curses.color_pair(PAIR_TURN) | curses.A_BOLD


def dim_attr():
    return curses.color_pair(PAIR_DIM) | curses.A_DIM


def home_safe_attr():
    # Every one of the 7 non-black ANSI hues is already claimed by a player
    # color, so HOME/SAFE spaces can't be told apart from a player's peg by
    # hue alone. A_DIM (used for plain track dots) is also unreliable --
    # many terminals render it as a no-op, indistinguishable from plain
    # text. Reverse video is hue-neutral and near-universally supported, so
    # empty HOME/SAFE spaces show as a solid block instead of a color.
    return curses.color_pair(PAIR_HOME_SAFE) | curses.A_REVERSE
