"""The Host/Join screen shown when the app starts."""
import time

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.geometry import Spacing
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    RadioButton,
    RadioSet,
    Select,
    Static,
    Switch,
)

from . import colors
from ..game.state import COLORS
from ..net.client import ClientConnection
from ..net.server import GameServer
from .sparkles import DEFAULT_SPEED, JokerSparkles, SliderMeter

DEFAULT_PORT = 5555
TITLE_TEXT = "Pegs and Jokers"
SLIDER_LABELS = ("Joker", "Smile", "Whimsy")


class ConnectScreen(Screen):
    CSS = """
    ConnectScreen {
        align: center middle;
        layers: background foreground;
    }
    JokerSparkles {
        layer: background;
    }
    #page {
        layer: foreground;
        width: auto;
        height: auto;
    }
    #bottom_bar {
        layer: foreground;
        dock: bottom;
        height: auto;
    }
    #row_direction {
        height: 1;
        align: left middle;
    }
    #row_direction.wrapped {
        layout: vertical;
        height: auto;
    }
    #row_direction > SliderMeter {
        width: auto;
    }
    #direction_x {
        padding: 0 0 0 2;
    }
    #direction_y {
        padding: 0;
        margin-left: 1;
    }
    #row_direction > Switch {
        border: none;
        padding: 0;
        height: 1;
        margin-left: 1;
    }
    #row_direction > .switch-label {
        width: auto;
        margin-left: 1;
        color: $text-muted;
    }
    #row_direction.wrapped > * {
        margin-left: 0;
    }
    #title {
        width: 100%;
        text-align: center;
        text-style: bold;
    }
    #form {
        width: 46;
        height: auto;
        border: round $accent;
        padding: 0 2;
    }
    #form .row {
        height: auto;
        align: left middle;
    }
    #form .row > .label {
        width: 9;
        color: $text-muted;
    }
    #form .row > Select, #form .row > Input, #form .row > RadioSet {
        width: 1fr;
    }
    #mode {
        layout: horizontal;
    }
    #status {
        color: $error;
        height: 1;
    }
    #connect {
        margin-top: 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield JokerSparkles(id="sparkles")
        with Vertical(id="page"):
            yield Static(colors.random_colored_markup(TITLE_TEXT), id="title")
            with Vertical(id="form"):
                with Horizontal(classes="row"):
                    yield Static("Mode", classes="label")
                    with RadioSet(id="mode", compact=True):
                        yield RadioButton("Host", value=True, id="mode_host")
                        yield RadioButton("Join", id="mode_join")

                with Horizontal(classes="row", id="row_players"):
                    yield Static("Players", classes="label")
                    yield Select(
                        (
                            (
                                f"{n} (Wonky)" if n in (6, 8) else
                                f"{n} (without jokers)" if n == 2 else
                                str(n),
                                n,
                            )
                            for n in (2, 4, 6, 8)
                        ),
                        value=4,
                        id="num_players",
                        allow_blank=False,
                        compact=True,
                    )

                with Horizontal(classes="row", id="row_address"):
                    yield Static("Address", classes="label")
                    yield Input(value="127.0.0.1", id="address", compact=True)

                with Horizontal(classes="row"):
                    yield Static("Port", classes="label")
                    yield Input(value=str(DEFAULT_PORT), id="port", compact=True)

                with Horizontal(classes="row"):
                    yield Static("Name", classes="label")
                    yield Input(value="", placeholder="Player", id="name", compact=True)

                with Horizontal(classes="row"):
                    yield Static("Color", classes="label")
                    yield Select(
                        ((f"[{colors.player_style(c)}]{c.capitalize()}[/]", c) for c in COLORS),
                        value=COLORS[0],
                        id="color",
                        allow_blank=False,
                        compact=True,
                    )

                yield Static("", id="status")
                yield Button("Connect", variant="primary", id="connect", compact=True)
        with Vertical(id="bottom_bar"):
            label_width = max(len(label) for label in SLIDER_LABELS)
            yield SliderMeter(
                SLIDER_LABELS[0], value=5.0, label_width=label_width, id="intensity"
            )
            yield SliderMeter(
                SLIDER_LABELS[1], value=DEFAULT_SPEED, label_width=label_width, id="speed"
            )
            with Horizontal(id="row_direction"):
                yield SliderMeter(
                    SLIDER_LABELS[2], value=50.0, label_width=label_width, id="direction_x"
                )
                yield SliderMeter("", value=50.0, id="direction_y")
                yield Switch(value=False, id="direction_enabled")
                yield Static("On/Off", classes="switch-label")
            yield Footer()

    def on_mount(self) -> None:
        self._update_field_visibility()
        sparkles = self.query_one("#sparkles", JokerSparkles)
        sparkles.intensity = self.query_one("#intensity", SliderMeter).value
        sparkles.speed = self.query_one("#speed", SliderMeter).value
        sparkles.direction_x = self.query_one("#direction_x", SliderMeter).value
        sparkles.direction_y = self.query_one("#direction_y", SliderMeter).value
        sparkles.direction_enabled = self.query_one("#direction_enabled", Switch).value
        self.call_after_refresh(self._update_direction_wrap)

    def on_resize(self, event: events.Resize) -> None:
        self._update_direction_wrap()

    def _update_direction_wrap(self) -> None:
        """Stack the Whimsy row's controls onto separate lines once the
        terminal is too narrow to fit them side by side."""
        row = self.query_one("#row_direction", Horizontal)
        children = list(row.children)
        if not children:
            return
        gaps = len(children) - 1
        needed = sum(child.outer_size.width for child in children) + gaps
        wrapped = needed > row.size.width
        row.set_class(wrapped, "wrapped")

        dx = self.query_one("#direction_x", SliderMeter)
        dy = self.query_one("#direction_y", SliderMeter)
        switch = self.query_one("#direction_enabled", Switch)
        label = self.query_one(".switch-label", Static)
        if wrapped:
            # Line up the 2nd bar, the switch, and its label under the "["
            # of the 1st (labeled) bar, rather than the row's left edge.
            bracket_col = dx.styles.padding.left + dx.label.index("[")
            dy_col = max(0, bracket_col - dy.styles.padding.left - dy.label.index("["))
            dy.styles.margin = Spacing(0, 0, 0, dy_col)
            switch.styles.margin = Spacing(0, 0, 0, bracket_col)
            label.styles.margin = Spacing(0, 0, 0, bracket_col)
        else:
            dy.styles.clear_rule("margin")
            switch.styles.clear_rule("margin")
            label.styles.clear_rule("margin")

    def on_slider_meter_changed(self, event: SliderMeter.Changed) -> None:
        sparkles = self.query_one("#sparkles", JokerSparkles)
        if event.slider.id == "intensity":
            sparkles.intensity = event.value
        elif event.slider.id == "speed":
            sparkles.speed = event.value
        elif event.slider.id == "direction_x":
            sparkles.direction_x = event.value
        elif event.slider.id == "direction_y":
            sparkles.direction_y = event.value

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "direction_enabled":
            self.query_one("#sparkles", JokerSparkles).direction_enabled = event.value

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        self._update_field_visibility()

    def _is_hosting(self) -> bool:
        mode = self.query_one("#mode", RadioSet)
        return mode.pressed_button is None or mode.pressed_button.id == "mode_host"

    def _update_field_visibility(self) -> None:
        hosting = self._is_hosting()
        self.query_one("#row_players").display = hosting
        self.query_one("#row_address").display = not hosting
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
