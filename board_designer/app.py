"""WYSIWYG TUI for designing the 6- and 8-player Pegs & Jokers board
layouts. Completely separate tool from the pegsandjokers game itself --
see README.md for how its JSON output is meant to be wired back into the
game in a later session.
"""
from rich.segment import Segment
from rich.style import Style

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.geometry import Size
from textual.message import Message
from textual.screen import ModalScreen
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import Input, Static

from . import models

SEAT_COLORS = [
    "#ff5555", "#5599ff", "#55cc55", "#e6c94d",
    "#e066e0", "#4dd0d0", "#e8e8e8", "#ff9933",
]

SCOPES_BY_KIND = {
    "track": ("single", "seat"),
    "home": ("single", "cluster", "seat"),
    "safe": ("single", "cluster", "seat"),
}

SCOPE_LABEL = {
    "single": "single space",
    "cluster": "whole cluster",
    "seat": "whole seat/arm",
}


class BoardCanvas(ScrollView):
    """Read-only-to-Textual grid of the board; the App owns all state and
    just tells this widget what to draw."""

    can_focus = False  # key bindings live on the App so plain arrows work everywhere

    class CellClicked(Message):
        def __init__(self, cell):
            self.cell = cell
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.positions = {}
        self._cell_render = {}

    def sync(self, positions, selected, group_members, collision_cells):
        self.positions = positions
        height, width = models.bounds(positions)
        self.virtual_size = Size(width, height)

        cell_render = {}
        for sid, cell in positions.items():
            seat = models.seat_of(sid)
            color = SEAT_COLORS[seat % len(SEAT_COLORS)]
            if models.is_come_out(sid):
                ch, style = "H", f"bold {color}"
            elif models.is_in_spot(sid):
                ch, style = "S", f"bold {color}"
            elif sid[0] == "track":
                ch, style = "·", f"dim {color}"
            elif sid[0] == "home":
                ch, style = "o", f"bold {color}"
            else:
                ch, style = "+", f"bold {color}"

            if cell in collision_cells:
                style = "bold white on red"
            if sid == selected:
                style = "black on yellow bold"
            elif sid in group_members:
                style = f"{color} on grey30 bold"

            cell_render[cell] = (ch, style)
        self._cell_render = cell_render
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
        gutter = self.gutter
        content_x = event.x - gutter.left + self.scroll_offset.x
        content_y = event.y - gutter.top + self.scroll_offset.y
        self.post_message(self.CellClicked((content_y, content_x)))


class PromptModal(ModalScreen):
    """Single free-text input, used for save/load paths and yes/no confirms."""

    DEFAULT_CSS = """
    PromptModal {
        align: center middle;
    }
    PromptModal > Vertical {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $panel;
        padding: 1 2;
    }
    PromptModal Static {
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, prompt, default, callback):
        super().__init__()
        self.prompt = prompt
        self.default = default
        self.callback = callback

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.prompt)
            yield Input(value=self.default, id="prompt-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value
        self.dismiss()
        self.callback(value)

    def action_cancel(self) -> None:
        self.dismiss()


class BoardDesignerApp(App):
    TITLE = "Pegs & Jokers -- Board Designer"

    CSS = """
    Screen {
        layout: horizontal;
    }
    BoardCanvas {
        width: 1fr;
        border: solid $accent;
    }
    #panel {
        width: 46;
        border: solid $accent;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("tab", "cycle(1)", "Next space"),
        Binding("shift+tab", "cycle(-1)", "Prev space"),
        Binding("up", "nudge(-1,0,1)", "Up", show=False),
        Binding("down", "nudge(1,0,1)", "Down", show=False),
        Binding("left", "nudge(0,-1,1)", "Left", show=False),
        Binding("right", "nudge(0,1,1)", "Right", show=False),
        Binding("k", "nudge(-1,0,1)", "Up", show=False),
        Binding("j", "nudge(1,0,1)", "Down", show=False),
        Binding("h", "nudge(0,-1,1)", "Left", show=False),
        Binding("l", "nudge(0,1,1)", "Right", show=False),
        Binding("K", "nudge(-1,0,5)", "Up x5", show=False),
        Binding("J", "nudge(1,0,5)", "Down x5", show=False),
        Binding("H", "nudge(0,-1,5)", "Left x5", show=False),
        Binding("L", "nudge(0,1,5)", "Right x5", show=False),
        Binding("g", "cycle_scope", "Move scope"),
        Binding("u", "undo", "Undo"),
        Binding("c", "center", "Center view"),
        Binding("s", "save_dialog", "Save"),
        Binding("o", "load_dialog", "Open"),
        Binding("n", "switch_players", "6/8 toggle"),
        Binding("R", "reset_dialog", "Reset"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, num_players=6, load_path=None):
        super().__init__()
        self.num_players = num_players
        self.positions = {}
        self.order = []
        self.selected_index = 0
        self.scope = "single"
        self.undo_stack = []
        self.dirty = False
        self.last_saved = None
        self._pending_load_path = load_path
        self._reseed(num_players)

    # -- state -------------------------------------------------------
    def _reseed(self, num_players):
        self.num_players = num_players
        self.order = models.space_order(num_players)
        self.positions = models.generate_seed(num_players)
        self.selected_index = 0
        self.scope = "single"
        self.undo_stack = []
        self.dirty = False
        self.last_saved = None

    @property
    def selected(self):
        if not self.order:
            return None
        return self.order[self.selected_index]

    def _group_members(self):
        sid = self.selected
        if sid is None:
            return set()
        if self.scope == "single":
            return {sid}
        seat = models.seat_of(sid)
        if self.scope == "cluster":
            kind = sid[0]
            if kind == "track":
                return {sid}
            return {s for s in self.positions if s[0] == kind and models.seat_of(s) == seat}
        if self.scope == "seat":
            return {s for s in self.positions if models.seat_of(s) == seat}
        return {sid}

    def _push_undo(self):
        self.undo_stack.append(dict(self.positions))
        if len(self.undo_stack) > 500:
            self.undo_stack.pop(0)

    # -- compose / mount ----------------------------------------------
    def compose(self) -> ComposeResult:
        yield BoardCanvas(id="canvas")
        yield Static(id="panel")

    def on_mount(self) -> None:
        if self._pending_load_path:
            self._do_load(self._pending_load_path)
            self._pending_load_path = None
        self._refresh_all()

    # -- rendering ------------------------------------------------------
    def _refresh_all(self):
        canvas = self.query_one(BoardCanvas)
        collided = models.collisions(self.positions)
        canvas.sync(self.positions, self.selected, self._group_members(), collided)
        self._ensure_visible()
        self._update_panel(collided)

    def _update_panel(self, collided=None):
        if collided is None:
            collided = models.collisions(self.positions)
        sid = self.selected
        if sid is None:
            sel_desc, sel_pos = "-", "-"
        else:
            seat = models.seat_of(sid)
            if models.is_come_out(sid):
                sel_desc = f"track hole {sid[1]} -- COME OUT SPOT 'H' (seat {seat})"
            elif models.is_in_spot(sid):
                sel_desc = f"track hole {sid[1]} -- IN SPOT 'S' (seat {seat})"
            elif sid[0] == "track":
                sel_desc = f"track hole {sid[1]} (seat {seat})"
            else:
                sel_desc = f"{sid[0]} {sid[2]} (seat {seat})"
            r, c = self.positions[sid]
            sel_pos = f"row {r}, col {c}"

        text = (
            f"[b]Pegs & Jokers -- Board Designer[/]\n"
            f"Players: {self.num_players}   Board: {models.BOARD_SLOTS[self.num_players]}-gon\n\n"
            f"Selected: {sel_desc}\n"
            f"  at {sel_pos}\n"
            f"Move scope: {SCOPE_LABEL[self.scope]}\n\n"
            f"Collisions: {len(collided)} cell(s) shared "
            f"{'[b red](fix these!)[/]' if collided else ''}\n"
            f"Unsaved changes: {'yes' if self.dirty else 'no'}\n"
            f"Last saved: {self.last_saved or '(not yet)'}\n\n"
            f"[b]Keys[/]\n"
            f"arrows / hjkl   move 1 cell\n"
            f"Shift+HJKL      move 5 cells\n"
            f"Tab / Shift+Tab next / prev space\n"
            f"g               cycle move scope\n"
            f"                (single -> cluster -> seat)\n"
            f"click           select space under cursor\n"
            f"u               undo\n"
            f"c               re-center view on selection\n"
            f"s               save to JSON...\n"
            f"o               open JSON...\n"
            f"n               switch 6<->8 players (reseeds)\n"
            f"Shift+R         reset layout (reseeds)\n"
            f"q               quit\n\n"
            f"[dim]. dim = track hole   o = HOME dot   + = SAFE dot\n"
            f"H = COME OUT SPOT (track hole into HOME)\n"
            f"S = IN SPOT (track hole into SAFE)\n"
            f"yellow = selected   grey box = move group\n"
            f"red = colliding spaces -- must be fixed before use[/]"
        )
        self.query_one("#panel", Static).update(text)

    def _ensure_visible(self):
        sid = self.selected
        if sid is None:
            return
        canvas = self.query_one(BoardCanvas)
        row, col = self.positions[sid]
        ox, oy = canvas.scroll_offset
        w, h = canvas.size.width, canvas.size.height
        if w <= 0 or h <= 0:
            return
        pad = 3
        if not (oy + pad <= row <= oy + h - pad and ox + pad <= col <= ox + w - pad):
            canvas.scroll_to(x=max(0, col - w // 2), y=max(0, row - h // 2), animate=False)

    # -- actions ----------------------------------------------------------
    def action_nudge(self, dr: int, dc: int, n: int) -> None:
        if self.selected is None:
            return
        self._push_undo()
        members = self._group_members()
        for sid in members:
            r, c = self.positions[sid]
            self.positions[sid] = (max(0, r + dr * n), max(0, c + dc * n))
        self.positions = models.shift_into_bounds(self.positions)
        self.dirty = True
        self._refresh_all()

    def action_cycle(self, direction: int) -> None:
        if not self.order:
            return
        self.selected_index = (self.selected_index + direction) % len(self.order)
        self.scope = "single"
        self._refresh_all()

    def action_cycle_scope(self) -> None:
        sid = self.selected
        if sid is None:
            return
        options = SCOPES_BY_KIND[sid[0]]
        idx = options.index(self.scope) if self.scope in options else 0
        self.scope = options[(idx + 1) % len(options)]
        self._refresh_all()

    def action_undo(self) -> None:
        if not self.undo_stack:
            return
        self.positions = self.undo_stack.pop()
        self.dirty = True
        self._refresh_all()

    def action_center(self) -> None:
        self._ensure_visible_force()
        self._refresh_all()

    def _ensure_visible_force(self):
        sid = self.selected
        if sid is None:
            return
        canvas = self.query_one(BoardCanvas)
        row, col = self.positions[sid]
        w, h = canvas.size.width, canvas.size.height
        canvas.scroll_to(x=max(0, col - w // 2), y=max(0, row - h // 2), animate=False)

    def on_board_canvas_cell_clicked(self, message: BoardCanvas.CellClicked) -> None:
        for sid, cell in self.positions.items():
            if cell == message.cell:
                self.selected_index = self.order.index(sid)
                self.scope = "single"
                self._refresh_all()
                return

    # -- save / load / reset / player-count switch -------------------------
    def action_save_dialog(self) -> None:
        default = self.last_saved or models.default_path(self.num_players)
        self.push_screen(PromptModal("Save layout to:", default, self._do_save))

    def _do_save(self, path):
        if not path:
            return
        models.save(path, self.num_players, self.positions)
        self.last_saved = path
        self.dirty = False
        self._refresh_all()

    def action_load_dialog(self) -> None:
        default = self.last_saved or models.default_path(self.num_players)
        self.push_screen(PromptModal("Open layout from:", default, self._do_load))

    def _do_load(self, path):
        if not path:
            return
        try:
            num_players, positions = models.load(path)
        except (OSError, ValueError, KeyError) as exc:
            self.query_one("#panel", Static).update(f"[b red]Load failed:[/] {exc}")
            return
        self.num_players = num_players
        self.order = models.space_order(num_players)
        self.positions = positions
        self.selected_index = 0
        self.scope = "single"
        self.undo_stack = []
        self.dirty = False
        self.last_saved = path
        self._refresh_all()

    def action_reset_dialog(self) -> None:
        self.push_screen(
            PromptModal(
                f"Reseed the {self.num_players}-player layout and lose unsaved changes? "
                f"Type 'yes' to confirm.",
                "",
                self._do_reset,
            )
        )

    def _do_reset(self, answer):
        if answer.strip().lower() != "yes":
            return
        self._push_undo()
        self.positions = models.generate_seed(self.num_players)
        self.dirty = True
        self._refresh_all()

    def action_switch_players(self) -> None:
        other = 8 if self.num_players == 6 else 6
        self.push_screen(
            PromptModal(
                f"Switch to the {other}-player board and lose unsaved changes? "
                f"Type 'yes' to confirm.",
                "",
                lambda answer, other=other: self._do_switch(answer, other),
            )
        )

    def _do_switch(self, answer, other):
        if answer.strip().lower() != "yes":
            return
        self._reseed(other)
        self._refresh_all()


def run(num_players=6, load_path=None):
    BoardDesignerApp(num_players=num_players, load_path=load_path).run()
