"""The Host/Join screen shown when the app starts."""
import time

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, RadioButton, RadioSet, Select, Static

from ..game.state import COLORS
from ..net.client import ClientConnection
from ..net.server import GameServer

DEFAULT_PORT = 5555


class ConnectScreen(Screen):
    CSS = """
    ConnectScreen {
        align: center bottom;
    }
    #title {
        dock: top;
        width: 100%;
        text-align: center;
    }
    #form {
        width: 60;
        height: auto;
        border: round $accent;
        padding: 1 2 0 2;
    }
    #form > Static.label {
        margin-top: 1;
    }
    #form > Horizontal {
        height: auto;
        margin-top: 1;
    }
    #status {
        margin-top: 1;
        color: $error;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[b]Pegs and Jokers[/b]", id="title")
        with Vertical(id="form"):
            yield Static("[b]Host/Join Game[/b]", id="mode_title")
            with RadioSet(id="mode"):
                yield RadioButton("Host a new game", value=True, id="mode_host")
                yield RadioButton("Join a game", id="mode_join")

            yield Static("Number of players (host only)", classes="label")
            yield Select(((str(n), n) for n in (2, 4, 6, 8)), value=4, id="num_players", allow_blank=False)

            yield Static("Server address (join only)", classes="label")
            yield Input(value="127.0.0.1", id="address")

            yield Static("Port", classes="label")
            yield Input(value=str(DEFAULT_PORT), id="port")

            yield Static("Your name", classes="label")
            yield Input(value="", placeholder="Player", id="name")

            yield Static("Your color", classes="label")
            yield Select(((c.capitalize(), c) for c in COLORS), value=COLORS[0], id="color", allow_blank=False)

            yield Static("", id="status")
            with Horizontal():
                yield Button("Connect", variant="primary", id="connect")
        yield Footer()

    def on_mount(self) -> None:
        self._update_field_visibility()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        self._update_field_visibility()

    def _is_hosting(self) -> bool:
        mode = self.query_one("#mode", RadioSet)
        return mode.pressed_button is None or mode.pressed_button.id == "mode_host"

    def _update_field_visibility(self) -> None:
        hosting = self._is_hosting()
        self.query_one("#num_players").display = hosting
        self.query_one("#address").display = not hosting
        self.query_one("#connect", Button).label = "Host" if hosting else "Connect"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "connect":
            return
        self._set_status("")
        event.button.disabled = True
        name = self.query_one("#name", Input).value.strip() or "Player"
        color = self.query_one("#color", Select).value
        try:
            port = int(self.query_one("#port", Input).value.strip() or DEFAULT_PORT)
        except ValueError:
            self._set_status("Port must be a number.")
            event.button.disabled = False
            return

        if self._is_hosting():
            num_players = self.query_one("#num_players", Select).value
            self.run_worker(
                lambda: self._connect_blocking(host=True, num_players=num_players, port=port, name=name, color=color),
                thread=True,
            )
        else:
            address = self.query_one("#address", Input).value.strip() or "127.0.0.1"
            self.run_worker(
                lambda: self._connect_blocking(host=False, address=address, port=port, name=name, color=color),
                thread=True,
            )

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    # -- runs in a worker thread; never touch widgets directly from here -----
    def _connect_blocking(self, *, host, port, name, color, num_players=None, address=None):
        try:
            if host:
                server = GameServer(num_players, port)
                server.start()
                conn = ClientConnection("127.0.0.1", port)
            else:
                server = None
                conn = ClientConnection(address, port)
            welcome, leftover = self._join_handshake(conn, name, color)
        except (ConnectionError, TimeoutError, OSError) as e:
            self.app.call_from_thread(self._on_connect_failed, str(e))
            return
        self.app.call_from_thread(self._on_connected, conn, welcome, leftover, name)

    @staticmethod
    def _join_handshake(conn, name, color, timeout=8.0):
        """Send the join request and wait for the 'welcome' reply.

        conn.poll() can return several queued messages in one batch (e.g.
        'welcome' immediately followed by the first 'state' broadcast) --
        returning the instant 'welcome' is seen would silently throw the
        rest of that batch away, since poll() has already drained them off
        the queue. Any such leftovers are returned alongside the welcome so
        the caller can feed them into the controller once it exists.
        """
        conn.send({"type": "join", "name": name, "color": color})
        deadline = time.time() + timeout
        last_error = None
        leftover = []
        while time.time() < deadline:
            # Drain the *whole* batch before deciding anything -- returning
            # as soon as 'welcome' is seen mid-iteration would still lose
            # whatever else was in this same batch behind it.
            welcome_msg = None
            for msg in conn.poll():
                if msg.get("type") == "welcome":
                    welcome_msg = msg
                    continue
                if msg.get("type") == "system_msg":
                    last_error = msg["text"]
                if msg.get("type") == "_connection_lost":
                    raise ConnectionError(last_error or "Server closed the connection.")
                leftover.append(msg)
            if welcome_msg is not None:
                return welcome_msg, leftover
            time.sleep(0.05)
        raise TimeoutError(last_error or "Timed out waiting for the server.")

    def _on_connect_failed(self, message: str) -> None:
        self._set_status(f"Could not connect: {message}")
        self.query_one("#connect", Button).disabled = False

    def _on_connected(self, conn, welcome, leftover, name) -> None:
        from .game_screen import GameScreen

        screen = GameScreen(
            conn=conn,
            name=name,
            color=welcome["color"],
            num_players=welcome["num_players"],
            player_id=welcome["player_id"],
            is_host=welcome["is_host"],
        )
        for msg in leftover:
            screen.controller.apply_message(msg)
        self.app.push_screen(screen)
