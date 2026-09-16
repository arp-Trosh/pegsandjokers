"""Decorative "Joker" sparkle background for the connect screen.

A field of "." dots, each in a random player color, fades in from a dark
hue of that color up to full brightness and back down to dark before
disappearing -- never abruptly popping in/out. Density is driven by the
IntensityMeter lever, from 0% (no dots) to 100% (every cell holds one).
Dots also drift across the screen, independently along X and Y, at a
speed set by the two "Whimsy" levers; they wrap around the edges
rather than being removed, so drift never causes the same kind of
abrupt pop that the lifetime fade avoids.
"""
import random

from rich.segment import Segment
from rich.style import Style

from textual import events
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget

from ..game.state import COLORS
from . import colors

FPS = 12
DOT_CHAR = "."
MIN_LIFETIME = 1.5
MAX_LIFETIME = 4.0
# Speed slider is a multiplier on aging; 50% reproduces the base lifetimes
# above, and moving away from 50% scales the pace, amplified by
# SPEED_SENSITIVITY so the slider feels more responsive than a 1:1 mapping.
DEFAULT_SPEED = 50.0
SPEED_SENSITIVITY = 1.4
MIN_SPEED_MULTIPLIER = 0.05
# Dots never fade all the way to black -- they start/end at this fraction
# of full brightness, so they read as "a dark hue" rather than invisible.
MIN_BRIGHTNESS = 0.15
# Max drift speed (cells/second, at each axis lever's 0%/100% extreme) at
# the default speed multiplier. Moving a sub-cell offset each tick and
# rounding to the nearest cell for display is what turns intermediate,
# non-grid-aligned velocities into the on-screen diagonal stairstep that
# approximates them.
DRIFT_SPEED = 3.0


def _blend(hex_color: str, fraction: float) -> str:
    """Scale a hex color's channels toward black by `fraction` (0..1)."""
    fraction = max(0.0, min(1.0, fraction))
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f"#{int(r * fraction):02x}{int(g * fraction):02x}{int(b * fraction):02x}"


class _Dot:
    __slots__ = ("row", "col", "color", "age", "lifetime")

    def __init__(self, row, col, color, lifetime):
        self.row = float(row)
        self.col = float(col)
        self.color = color
        self.age = 0.0
        self.lifetime = lifetime

    def cell(self, height: int, width: int) -> tuple[int, int]:
        """Nearest whole grid cell for this dot's (possibly sub-cell) position.

        Rounding a coordinate that's within half a cell of the wrap
        boundary (e.g. row 9.6 out of height 10) can round up to the
        out-of-range value equal to the size, so the result is wrapped
        again rather than just rounded.
        """
        return (round(self.row) % height, round(self.col) % width)

    def style(self) -> str:
        t = self.age / self.lifetime
        # Triangular envelope: 0 at birth/death, 1 at the midpoint.
        envelope = 1.0 - abs(1.0 - 2.0 * t)
        brightness = MIN_BRIGHTNESS + (1.0 - MIN_BRIGHTNESS) * envelope
        return _blend(self.color, brightness)


class JokerSparkles(Widget):
    """Full-screen backdrop of fading dots; sits behind the connect form."""

    DEFAULT_CSS = """
    JokerSparkles {
        width: 100%;
        height: 100%;
        background: transparent;
    }
    """

    intensity = reactive(5.0)
    speed = reactive(DEFAULT_SPEED)
    # X axis: 0% max left, 50% no movement, 100% max right.
    direction_x = reactive(50.0)
    # Y axis: 0% max down, 50% no movement, 100% max up.
    direction_y = reactive(50.0)
    direction_enabled = reactive(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._dots: list[_Dot] = []
        self._grid: dict[tuple[int, int], str] = {}
        self._all_cells: list[tuple[int, int]] = []
        self._grid_size = (0, 0)

    def on_mount(self) -> None:
        self.set_interval(1 / FPS, self._tick)

    def _tick(self) -> None:
        width, height = self.size.width, self.size.height
        if width <= 0 or height <= 0:
            return
        speed_multiplier = max(
            MIN_SPEED_MULTIPLIER,
            1.0 + (self.speed - DEFAULT_SPEED) / DEFAULT_SPEED * SPEED_SENSITIVITY,
        )
        dt = (1 / FPS) * speed_multiplier

        if self.direction_enabled:
            dcol = (self.direction_x - 50.0) / 50.0 * DRIFT_SPEED * dt
            drow = -(self.direction_y - 50.0) / 50.0 * DRIFT_SPEED * dt
        else:
            drow = dcol = 0.0

        alive = []
        occupied = set()
        for dot in self._dots:
            dot.age += dt
            dot.row = (dot.row + drow) % height
            dot.col = (dot.col + dcol) % width
            if dot.age < dot.lifetime:
                alive.append(dot)
                occupied.add(dot.cell(height, width))
        self._dots = alive

        target = round(width * height * (self.intensity / 100.0))
        needed = target - len(self._dots)
        if needed > 0:
            if self._grid_size != (width, height):
                self._all_cells = [(r, c) for r in range(height) for c in range(width)]
                self._grid_size = (width, height)
            free = [cell for cell in self._all_cells if cell not in occupied]
            random.shuffle(free)
            for row, col in free[:needed]:
                color = colors.player_style(random.choice(COLORS))
                lifetime = random.uniform(MIN_LIFETIME, MAX_LIFETIME)
                self._dots.append(_Dot(row, col, color, lifetime))

        self._grid = {d.cell(height, width): d.style() for d in self._dots}
        self.refresh()

    def render_line(self, y: int) -> Strip:
        segments = []
        for x in range(self.size.width):
            style = self._grid.get((y, x))
            if style:
                segments.append(Segment(DOT_CHAR, Style.parse(style)))
            else:
                segments.append(Segment(" "))
        return Strip(segments)


class SliderMeter(Widget):
    """A draggable lever that reports a 0-100% value under a given label."""

    DEFAULT_CSS = """
    SliderMeter {
        width: 100%;
        height: 1;
        padding: 0 2;
        background: transparent;
    }
    SliderMeter:focus {
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("left,down", "nudge(-5)", "Decrease", show=False),
        Binding("right,up", "nudge(5)", "Increase", show=False),
    ]

    can_focus = True
    value = reactive(5.0)
    BAR_WIDTH = 30

    class Changed(Message):
        def __init__(self, slider: "SliderMeter", value: float) -> None:
            self.slider = slider
            self.value = value
            super().__init__()

    def __init__(self, label: str, value: float = 5.0, label_width: int | None = None, **kwargs):
        super().__init__(**kwargs)
        # Padding to a shared label_width keeps the "[" (and therefore the
        # bars themselves) lined up across sliders with differing label
        # lengths.
        padded = label.ljust(label_width) if label_width else label
        self.label = f"{padded}  ["
        self._dragging = False
        self.value = value

    def render(self) -> str:
        filled = round(self.BAR_WIDTH * self.value / 100)
        bar = "█" * filled + "─" * (self.BAR_WIDTH - filled)
        text = f"{self.label}{bar}] {round(self.value):3d}%"
        return colors.random_colored_markup(text)

    def watch_value(self, value: float) -> None:
        self.post_message(self.Changed(self, value))

    def action_nudge(self, delta: int) -> None:
        self.value = max(0.0, min(100.0, self.value + delta))

    def _set_from_x(self, x: int) -> None:
        pos = x - len(self.label)
        pct = 100 * pos / self.BAR_WIDTH
        self.value = max(0.0, min(100.0, pct))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.focus()
        self._dragging = True
        self.capture_mouse()
        self._set_from_x(event.x)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._dragging:
            self._set_from_x(event.x)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self._dragging = False
        self.release_mouse()
