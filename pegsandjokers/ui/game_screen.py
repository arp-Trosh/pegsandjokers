import asyncio

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, RichLog, Static

from ..game.board import Board, Layout
from ..game.cards import Card
from . import colors
from .board_widget import BoardView
from .game_controller import GameController
from .rules_screen import RulesScreen

CHAT_MAX_LEN = 300
CHAT_WARN_LEN = int(CHAT_MAX_LEN * 0.8)


class GameScreen(Screen):
    CSS = """
    GameScreen {
        layout: vertical;
    }
    #board {
        height: 1fr;
        border: round $accent;
        border-title-color: $text;
        border-title-style: bold;
    }
    #board.status-yourturn {
        border: round green;
    }
    #board.status-ended {
        border: round yellow;
    }
    #lower {
        height: 12;
    }
    #chat_col {
        width: 2fr;
        height: 100%;
    }
    #chat_log {
        height: 1fr;
        border: round $accent;
    }
    #chat_input {
        height: 1;
        border: none;
        padding: 0 1;
    }
    #players_panel {
        width: 1fr;
        height: 100%;
        border: round $accent;
        padding: 0 1;
    }
    #hand_row {
        height: auto;
        align: left middle;
    }
    #hand_row Button {
        margin-right: 1;
        min-width: 3;
    }
    #cancel-btn, #discard-btn {
        min-width: 3;
        height: 1;
        border: none;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("1", "pick_card(0)", "Card 1", show=False),
        Binding("2", "pick_card(1)", "Card 2", show=False),
        Binding("3", "pick_card(2)", "Card 3", show=False),
        Binding("4", "pick_card(3)", "Card 4", show=False),
        Binding("5", "pick_card(4)", "Card 5", show=False),
        Binding("c", "cancel", "Cancel"),
        Binding("x", "discard", "Discard"),
        Binding("b", "host_begin", "Begin (host)"),
        Binding("r", "host_restart", "Restart (host)"),
        Binding("e", "host_end", "End (host)"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(self, conn, name, color, num_players, player_id, is_host):
        super().__init__()
        self.controller = GameController(conn, name, color, num_players, player_id, is_host, Board(num_players))
        self.board_layout = Layout(self.controller.board)
        self._chat_written = 0
        # refresh_all() is called from several independent entry points --
        # the 0.1s network poll, plus button/click/input event handlers --
        # any of which can interleave with another mid-await. _refresh_hand's
        # remove-then-mount is not safe to run concurrently with itself: two
        # overlapping calls can each pass remove_children() before either
        # mounts, then both try to mount the same widget IDs (e.g. "card-0"),
        # raising DuplicateIds. This lock serializes just that critical
        # section so overlapping refreshes queue up instead of interleaving.
        self._hand_lock = asyncio.Lock()

    def compose(self) -> ComposeResult:
        yield BoardView(self.board_layout, id="board")
        with Horizontal(id="lower"):
            with Vertical(id="chat_col"):
                yield RichLog(id="chat_log", markup=True, wrap=True)
                yield Input(placeholder="Type a message, or /rules  (Enter to send)",
                            id="chat_input", max_length=CHAT_MAX_LEN)
            yield Static(id="players_panel")
        with Horizontal(id="hand_row"):
            pass

    async def on_mount(self) -> None:
        await self.refresh_all()
        self.set_interval(0.1, self.poll_network)

    # -- networking / redraw ---------------------------------------------
    async def poll_network(self) -> None:
        if self.controller.drain_network():
            await self.refresh_all()

    async def refresh_all(self) -> None:
        self._refresh_status()
        self.query_one(BoardView).update_from_controller(self.controller)
        self._refresh_chat()
        self._refresh_players()
        await self._refresh_hand()

    def _refresh_status(self) -> None:
        # The status line lives in the board's own border title instead of a
        # separate Static row -- this saves the full row that row used to
        # occupy above the board, while the border color still gives the
        # same at-a-glance signal the old background color did.
        c = self.controller
        board = self.query_one(BoardView)

        def set_status(text, *, yourturn=False, ended=False):
            board.border_title = text
            board.set_class(yourturn, "status-yourturn")
            board.set_class(ended, "status-ended")

        if c.game_over_msg:
            set_status(c.game_over_msg, yourturn=True)
            return
        if not c.state:
            set_status("Connecting...")
            return
        phase = c.state["phase"]
        if phase == "lobby":
            n = len(c.state["players"])
            msg = f"LOBBY: {n}/{c.num_players} players joined."
            if c.is_host:
                msg += "  Press 'b' to begin" if n >= c.num_players else "  (waiting for players)"
            set_status(msg)
            return
        if phase == "finished":
            msg = "GAME ENDED by host." + ("  press 'r' to restart" if c.is_host else "")
            set_status(msg, ended=True)
            return

        turn_pid = c.state["turn_player"]
        turn_p = c.state["players"].get(str(turn_pid), {})
        if turn_pid == c.player_id:
            if c.card_idx is None:
                instr = "Your turn: click a card to play."
            elif not c.candidates:
                instr = "No legal moves with that card -- pick another, or 'x' to discard if you're stuck."
            elif c.pending_from is None:
                instr = "Click the highlighted peg you want to move (or 'c' to cancel)."
            else:
                instr = "Click a highlighted destination (or 'c' to cancel)."
            set_status(f"YOUR TURN -- {instr}", yourturn=True)
        else:
            set_status(f"Turn: {turn_p.get('name', '?')}")

    def _refresh_chat(self) -> None:
        log = self.query_one("#chat_log", RichLog)
        new_entries = self.controller.chat_log[self._chat_written:]
        for kind, color, text in new_entries:
            style = colors.GAME_MSG_STYLE if kind == "system" else colors.player_style(color or "white")
            log.write(f"[{style}]{text}[/{style}]")
        self._chat_written = len(self.controller.chat_log)

    def _refresh_players(self) -> None:
        c = self.controller
        panel = self.query_one("#players_panel", Static)
        if not c.state:
            panel.update("")
            return
        lines = ["[b]Players:[/b]"]
        for pid_str, p in sorted(c.state["players"].items(), key=lambda kv: int(kv[0])):
            safe_count = sum(
                1 for peg in c.state["pegs"]
                if peg["owner"] == int(pid_str) and peg["location"][0] == "safe"
            )
            you = " (you)" if int(pid_str) == c.player_id else ""
            marker = ">" if c.state.get("turn_player") == int(pid_str) else " "
            style = colors.player_style(p["color"])
            if not p.get("connected", True):
                style = colors.DIM_STYLE
            lines.append(f"[{style}]{marker}{p['name']}{you} [{safe_count}/5 safe][/{style}]")
        panel.update("\n".join(lines))

    async def _refresh_hand(self) -> None:
        async with self._hand_lock:
            row = self.query_one("#hand_row", Horizontal)
            await row.remove_children()
            hand = self.controller.my_hand() or []
            widgets = []
            for i, card in enumerate(hand):
                c = Card.from_dict(card)
                label = f"{i + 1}:{c.short()}"
                btn = Button(label, id=f"card-{i}", variant="primary" if self.controller.card_idx == i else "default")
                widgets.append(btn)
            widgets.append(Button("Cancel", id="cancel-btn"))
            widgets.append(Button("Discard", id="discard-btn"))
            if widgets:
                await row.mount_all(widgets)

    # -- events --------------------------------------------------------------
    def on_key(self, event: events.Key) -> None:
        """Keyboard fallback for board clicks: a-z tags (minus the letters
        already used by BINDINGS below) are drawn over highlighted spaces
        by BoardView, for terminals/setups where clicking is inconvenient.
        Only single printable letters that aren't already consumed by a
        binding ever reach here."""
        if self.focused is not None and self.focused.id == "chat_input":
            return
        char = event.character
        if not char or len(char) != 1 or not char.isalpha():
            return
        if self.query_one(BoardView).activate_key_tag(char):
            event.stop()

    async def on_board_view_space_clicked(self, message: BoardView.SpaceClicked) -> None:
        if self.controller.click_space(message.space_id):
            await self.refresh_all()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("card-"):
            self.controller.select_card(int(bid.split("-", 1)[1]))
        elif bid == "cancel-btn":
            self.controller.cancel_selection()
        elif bid == "discard-btn":
            self.controller.try_discard()
        else:
            return
        await self.refresh_all()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "chat_input":
            return
        text = event.value
        event.input.value = ""
        result = self.controller.send_chat_or_command(text)
        if result == "rules":
            self.app.push_screen(RulesScreen())
        await self.refresh_all()

    # -- key-bound actions -------------------------------------------------
    async def action_pick_card(self, idx: int) -> None:
        if self.focused is not None and self.focused.id == "chat_input":
            return
        self.controller.select_card(idx)
        await self.refresh_all()

    async def action_cancel(self) -> None:
        if self.focused is not None and self.focused.id == "chat_input":
            return
        self.controller.cancel_selection()
        await self.refresh_all()

    async def action_discard(self) -> None:
        if self.focused is not None and self.focused.id == "chat_input":
            return
        self.controller.try_discard()
        await self.refresh_all()

    def action_host_begin(self) -> None:
        if self.controller.is_host:
            self.controller.host_begin()

    def action_host_restart(self) -> None:
        if self.controller.is_host:
            self.controller.host_restart()

    def action_host_end(self) -> None:
        if self.controller.is_host:
            self.controller.host_end()

    def action_quit_app(self) -> None:
        if self.focused is not None and self.focused.id == "chat_input":
            return
        self.app.exit()
