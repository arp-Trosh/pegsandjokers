"""The game board as a scrollable Textual widget.

The board is drawn at its true, unsquashed size (same Layout geometry the
game always used) regardless of how large that is -- a big 8-player
octagon just means more virtual canvas, and the player scrolls/pans to see
the rest of it, the same way any page taller than the window would. This
is what actually solves "the board doesn't fit," instead of shrinking the
board's own proportions to force a fit.
"""
import random

from rich.segment import Segment
from rich.style import Style

from textual import events
from textual.geometry import Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip

from ..game.state import COLORS
from . import colors


class BoardView(ScrollView):
    class SpaceClicked(Message):
        def __init__(self, space_id):
            self.space_id = space_id
            super().__init__()

    def __init__(self, board_layout, **kwargs):
        super().__init__(**kwargs)
        self.set_layout(board_layout)

    def set_layout(self, board_layout) -> None:
        """(Re)plant the whole board on a new Layout -- used at startup, and
        again once teams are finalized and the server reseats players so
        teammates sit opposite each other, since that reshuffles which arm
        of the board each player's home/safe/track holes are drawn on."""
        # Named board_layout, not layout -- Widget already reserves that name.
        self.board_layout = board_layout
        self.virtual_size = Size(board_layout.width, board_layout.height)
        # Reverse lookup for clicks: (row, col) -> space_id. Layout.positions
        # keys are already in exactly the ("track", gid) / (kind, owner, slot)
        # shape that game/rules.py move steps use, so no translation needed.
        self.space_at_cell = {(r, c): space_id for space_id, (r, c) in board_layout.positions.items()}
        self._cell_render = {}
        self._key_tags = {}  # single-char -> space_id, for the keyboard fallback
        # space_id -> style, chosen once when the game ends so the empty
        # "." spaces light up in random player colors without re-rolling
        # (and thus flickering) on every redraw.
        self._win_colors = {}
        self.refresh()

    def update_from_controller(self, controller):
        highlight = controller.current_highlight()
        game_over = bool(controller.state) and controller.state.get("phase") == "finished"
        if game_over and not self._win_colors:
            self._win_colors = {
                space_id: colors.player_style(random.choice(COLORS))
                for space_id in self.board_layout.positions
            }
        elif not game_over:
            self._win_colors = {}
        cell_render = {}
        tags = {}
        # b/c/e/q/r/x are GameScreen-level key bindings (host begin/cancel/
        # host end/quit/host restart/discard) -- Textual resolves those
        # bindings before a key ever reaches our on_key fallback, so a
        # highlighted space must never be tagged with one of them or
        # pressing it would trigger that action instead of selecting the
        # space.
        tag_chars = (ch for ch in "abcdefghijklmnopqrstuvwxyz" if ch not in "bcerqx")
        for space_id, (r, c) in self.board_layout.positions.items():
            occ_color = controller.occupant_color(space_id)
            is_hl = space_id in highlight
            if occ_color:
                ch = occ_color[0].upper()
                style = colors.player_style(occ_color)
            elif game_over:
                ch = "."
                style = self._win_colors.get(space_id, colors.DIM_STYLE)
            elif space_id[0] in ("home", "safe"):
                ch = "."
                style = colors.owner_home_safe_style(controller.owner_color(space_id))
            else:
                ch = "."
                style = colors.owner_track_style(controller.owner_color(space_id))
            if is_hl:
                style = colors.HIGHLIGHT_STYLE
                tag = next(tag_chars, None)
                if tag:
                    ch = tag
                    tags[tag] = space_id
            cell_render[(r, c)] = (ch, style)
        self._cell_render = cell_render
        self._key_tags = tags
        self.refresh()

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        row = y + scroll_y
        segments = []
        for col in range(scroll_x, scroll_x + self.size.width):
            ch, style = self._cell_render.get((row, col), (" ", ""))
            segments.append(Segment(ch, Style.parse(style) if style else None))
        return Strip(segments)

    def on_click(self, event: events.Click) -> None:
        # event.x/y are relative to this widget's OUTER region, which
        # includes the border -- not the content area. Without subtracting
        # the border's thickness (gutter.left/top), every click lands one
        # cell off from the space actually under the pointer, which is
        # exactly why clicking a highlighted peg appeared to do nothing:
        # the click was landing on a neighboring, non-highlighted cell.
        gutter = self.gutter
        content_x = event.x - gutter.left + self.scroll_offset.x
        content_y = event.y - gutter.top + self.scroll_offset.y
        space_id = self.space_at_cell.get((content_y, content_x))
        if space_id is not None:
            self.post_message(self.SpaceClicked(space_id))

    def activate_key_tag(self, char):
        space_id = self._key_tags.get(char)
        if space_id is not None:
            self.post_message(self.SpaceClicked(space_id))
            return True
        return False
