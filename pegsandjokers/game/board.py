"""Board geometry and layout for Pegs and Jokers.

The physical game is played on a ring of 4, 6, or 8 identical boards
arranged into a rectangle, hexagon, or octagon. Two-player games still use
the 4-board rectangle, but only two of the four arms are occupied (the
players sit across from one another).

This module has two jobs:

1. Logical layout: how many holes are on the shared main track, where each
   player's COME OUT SPOT / IN SPOT / HOME / SAFE areas are, and who is on
   whose team. (used by game/rules.py and game/state.py)

2. Visual layout: a pure-data ASCII/character grid describing where every
   space should be drawn on screen, independent of curses, so it can be
   unit tested by simply printing it.
"""
import math

HOME_COUNT = 5
SAFE_COUNT = 5
ARM_LEN = 18  # main-track holes per side/arm, including the COME OUT SPOT and IN SPOT

# Position of COME OUT SPOT and IN SPOT within a seat's own arm block,
# counting from 0. Per the reference board: counting the 18 holes of one
# arm from one end, COME OUT SPOT is hole #9 and IN SPOT is hole #4.
COME_OUT_LOCAL_INDEX = 8
IN_SPOT_LOCAL_INDEX = 3

# Number of physical boards (sides of the polygon) used for a given player count.
BOARD_SLOTS = {2: 4, 4: 4, 6: 6, 8: 8}


class Board:
    """Logical board description for a given player count."""

    def __init__(self, num_players):
        if num_players not in BOARD_SLOTS:
            raise ValueError("num_players must be one of 2, 4, 6, 8")
        self.num_players = num_players
        self.slots = BOARD_SLOTS[num_players]
        self.track_len = self.slots * ARM_LEN
        if num_players == 2:
            # sit directly across from one another on the 4-slot rectangle
            self.seat_of_player = [0, 2]
        else:
            self.seat_of_player = list(range(num_players))

    # -- seating / teams -------------------------------------------------
    def seat(self, player):
        return self.seat_of_player[player]

    def player_at_seat(self, seat):
        for p, s in enumerate(self.seat_of_player):
            if s == seat:
                return p
        return None

    def reseat(self, seat_of_player):
        """Replace the seat assignment (e.g. once teams are finalized and
        the game starts, so teammates end up sitting opposite each other).
        `seat_of_player` must still be a permutation of 0..slots-1, indexed
        by player_id."""
        self.seat_of_player = list(seat_of_player)

    def default_team(self, player):
        """Seat-opposite team index (0..num_players//2 - 1), or None for a
        2-player game (no teams). This is only the starting-lobby default --
        GameState.teammate()/team_id() are authoritative once players are
        free to pick their own team, since a chosen team need not match
        seat-opposite pairing."""
        if self.num_players < 4:
            return None
        return self.seat(player) % (self.slots // 2)

    # -- main track --------------------------------------------------------
    # COME OUT SPOT (hole #9 of this seat's own 18-hole arm) sits well past
    # IN SPOT (hole #4 of the SAME arm) in forward/clockwise order. That gap
    # -- come out at index 8, in spot at index 3, both within one arm block
    # -- is what forces a peg to travel all the way around through every
    # other player's arm before it can reach its own IN SPOT: going forward
    # from COME OUT it must finish this arm, circle every other arm, and
    # come back around to this arm's own hole #4.
    def come_out_spot(self, player):
        return self.seat(player) * ARM_LEN + COME_OUT_LOCAL_INDEX

    def in_spot(self, player):
        return self.seat(player) * ARM_LEN + IN_SPOT_LOCAL_INDEX

    def arm_holes(self, player):
        """Global main-track indices belonging to this player's arm."""
        start = self.seat(player) * ARM_LEN
        return list(range(start, start + ARM_LEN))

    def step_forward(self, pos, n):
        return (pos + n) % self.track_len

    def step_backward(self, pos, n):
        return (pos - n) % self.track_len

    def distance_forward(self, start, end):
        return (end - start) % self.track_len


# ---------------------------------------------------------------------------
# Visual layout
# ---------------------------------------------------------------------------
# HOME cluster shape: a diamond (4 corners + center), placed via
# Layout._place() below using (along, perp) offset pairs in units of one
# hole-spacing, relative to the arm's own COME OUT SPOT:
#   along: +1 = one hole further in the forward/clockwise direction
#          (toward higher hole numbers on this arm), -1 = one hole back.
#   perp:  +1 = one hole further inward, toward the polygon's interior
#          (where HOME/SAFE are drawn, keeping the board compact) --
#          _place() below flips this to outward if ever needed.
# This keeps the diamond correctly oriented no matter which side of the
# rectangle/hexagon/octagon the arm falls on, since (along, perp) is
# defined relative to the arm's own direction rather than the screen's.
#
# Shifted 1 hole-unit toward IN SPOT (all `along` values -1 from a
# centered diamond) so the HOME diamond and the SAFE line (below) sit
# close together on the arm instead of spread apart at opposite ends of
# it.
HOME_OFFSETS = [(-1, 2), (-2, 1), (0, 1), (-2, 3), (0, 3)]
# SAFE cluster: a straight line of SAFE_COUNT holes running perpendicular
# to the main track, directly off IN SPOT, extending straight into the
# polygon's interior. Unlike HOME, this is placed via
# Layout._place_radial_line() rather than a list of (along, perp)
# offsets -- a diagonal hexagon/octagon arm's continuous outward
# direction doesn't round to a constant number of grid columns/rows per
# step (it staggers, e.g. 2,3,3,2,...), which independent per-point
# rounding would render as a bent, unevenly spaced line. Rounding a
# single per-step vector once and repeating it guarantees a straight,
# uniformly spaced line instead -- see _place_radial_line() for how.

# One hole's worth of distance in the abstract layout space used to build
# the polygon (see Layout._build). Kept at 1.0 for simplicity; ROW_SCALE and
# COL_SCALE (below) are what actually turn that into terminal cells.
HOLE_UNIT = 1.0

# Terminal characters are roughly twice as tall as they are wide, so one
# unit of abstract distance is drawn as fewer rows than columns to look
# roughly square on screen. Both are whole numbers so that a hole-to-hole
# step along a perfectly horizontal or vertical arm (every arm, on the
# rectangle boards used for 2/4 players) lands on an exact, evenly spaced
# number of cells every time -- no more, no less -- instead of drifting
# between neighboring cells as float positions get rounded.
ROW_SCALE = 1
COL_SCALE = 2


class Layout:
    """Pure-data visual layout: a dict of space-id -> (row, col), plus the
    text grid dimensions. No curses/rendering here, just coordinates, so it
    can be produced and inspected without a terminal.
    """

    def __init__(self, board: Board, viewer_seat=0):
        self.board = board
        # Which physical seat is drawn on the bottom edge of the screen
        # (see _BOTTOM_VERTEX / start_angle in _build) -- defaults to seat
        # 0 so non-interactive/logical uses (e.g. tests) still get a
        # stable layout, but each player's own GameScreen passes their own
        # seat so their row always renders at the bottom of their screen
        # no matter which physical seat they're actually sitting in.
        self.viewer_seat = viewer_seat
        self.positions = {}  # space_id -> (row, col)
        self._build()

    def _build(self):
        slots = self.board.slots
        # Regular polygon vertices for `slots` sides, centered at origin,
        # with a SINGLE radius (a true regular polygon in this abstract
        # space -- aspect correction for non-square terminal characters is
        # applied later, only when converting to grid cells in _to_grid).
        # The radius is chosen so each side is exactly ARM_LEN hole-units
        # long, i.e. exactly HOLE_UNIT apart -- this is what keeps every
        # hole evenly spaced instead of drifting in and out by a cell as
        # float positions get rounded to whole terminal cells.
        side_length = ARM_LEN * HOLE_UNIT
        radius = side_length / (2 * math.sin(math.pi / slots))
        verts = []
        # Rotate so the first side is the bottom edge (nicer for rectangles).
        start_angle = math.pi / 2 + math.pi / slots
        for i in range(slots):
            angle = start_angle + i * (2 * math.pi / slots)
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            verts.append((x, y))

        # Despite the comment above, the seat-0 arm (verts[0] -> verts[1])
        # actually lands on the LEFT edge, not the bottom -- easily checked
        # by rendering it. The arm that's actually bottommost is the last
        # one, verts[slots - 1] -> verts[0]. viewer_seat rotation below
        # anchors to *that* vertex so a seat mapped there truly renders on
        # the bottom edge instead of the left one.
        _BOTTOM_VERTEX = slots - 1

        occupied_seats = set(self.board.seat_of_player)

        for seat in range(slots):
            # Rotate which vertex this seat's arm is drawn on by
            # viewer_seat, so the viewer's own seat always lands on
            # _BOTTOM_VERTEX (the true bottom edge) while every other seat
            # keeps the same relative order/adjacency around the ring --
            # just spun to match.
            vertex = (seat - self.viewer_seat + _BOTTOM_VERTEX) % slots
            vx, vy = verts[vertex]
            nx, ny = verts[(vertex + 1) % slots]
            # outward normal direction (points away from the polygon center)
            mx, my = (vx + nx) / 2, (vy + ny) / 2
            norm = math.hypot(mx, my) or 1.0
            out_x, out_y = mx / norm, my / norm
            # unit vector along the arm, in the forward/clockwise direction
            arm_len_px = math.hypot(nx - vx, ny - vy) or 1.0
            along_x, along_y = (nx - vx) / arm_len_px, (ny - vy) / arm_len_px
            hole_spacing = arm_len_px / ARM_LEN

            hole_xy = {}
            for i in range(ARM_LEN):
                # Hole 0 sits exactly on this arm's start vertex; the arm's
                # last hole (i=ARM_LEN-1) is one full hole-spacing short of
                # the *next* vertex, which is where the next arm's hole 0
                # picks up. That keeps the gap across a corner exactly the
                # same size as every other gap -- insetting by half a
                # hole-spacing on both sides of the vertex (as before)
                # instead left a visibly smaller, uneven gap right at each
                # corner.
                t = i / ARM_LEN
                x = vx + (nx - vx) * t
                y = vy + (ny - vy) * t
                hole_xy[i] = (x, y)
                gid = seat * ARM_LEN + i
                self.positions[("track", gid)] = self._to_grid(x, y)

            if seat not in occupied_seats:
                continue
            player = self.board.player_at_seat(seat)

            # A perp push of the same abstract magnitude reads as much
            # closer to the track for a diagonal arm than for an
            # axis-aligned one: on an axis-aligned rectangle arm, HOME/SAFE
            # sit purely to one side of the track (a clean 90-degree
            # offset), but on a hexagon/octagon's diagonal arms the
            # "outward" direction is itself at a diagonal angle, so the
            # cluster's dots visually read as just more steps along the
            # same diagonal trend as the track -- they blend into it as
            # clumps instead of standing apart from it. Boosting the perp
            # distance in inverse proportion to how diagonal the arm is
            # compensates for that, while leaving perfectly axis-aligned
            # arms (out_x or out_y == 0, diag_factor == 1) untouched. The
            # extra factor of 2 is empirical: measuring the actual nearest
            # home-dot-to-track-hole grid distance showed a plain 1/x
            # boost barely moved the rounded result at all (rounding to
            # character cells swallowed the small correction), while 2/x
            # reliably opened up a clearly-separated gap.
            diag_factor = max(abs(out_x), abs(out_y)) or 1.0
            perp_boost = 1.0 + 4.0 * (1.0 - diag_factor)

            def _place(cluster, anchor_xy, offsets):
                ax, ay = anchor_xy
                for i, (along, perp) in enumerate(offsets):
                    # Negate perp: offsets are authored as "outward" for
                    # readability, but HOME/SAFE are drawn inward (toward
                    # the polygon's interior) to keep the board compact.
                    perp *= -perp_boost
                    x = ax + along * hole_spacing * along_x + perp * hole_spacing * out_x
                    y = ay + along * hole_spacing * along_y + perp * hole_spacing * out_y
                    self.positions[(cluster, player, i)] = self._to_grid(x, y)

            def _place_radial_line(cluster, anchor_xy, count):
                """Like _place, but for a pure perp=1..count radial line
                (SAFE's shape): rounds each point independently the way
                _place does, on a diagonal hexagon/octagon arm the
                continuous per-step delta (e.g. 2.66 grid columns) doesn't
                round to a constant number of columns every step -- it
                staggers 2,3,3,2,... -- which reads as a bent, unevenly
                spaced line instead of a straight one. Rounding a single
                per-step (row, col) vector ONCE and then repeating that
                same integer step for every point guarantees uniform
                spacing and a straight line by construction, at the cost
                of the line's on-screen angle being the nearest reachable
                integer-step approximation of the true geometric outward
                direction rather than that exact direction.
                """
                ax, ay = anchor_xy
                raw_dx = -perp_boost * hole_spacing * out_x
                raw_dy = -perp_boost * hole_spacing * out_y
                dr = round(raw_dy * ROW_SCALE)
                dc = round(raw_dx * COL_SCALE)
                if dr == 0 and dc == 0:
                    # Degenerate only if hole_spacing/perp_boost is near
                    # zero, which doesn't happen in practice -- but fall
                    # back to a visible step along whichever axis is
                    # dominant rather than stacking every point on the
                    # anchor cell.
                    if abs(raw_dy * ROW_SCALE) >= abs(raw_dx * COL_SCALE):
                        dr = 1 if raw_dy >= 0 else -1
                    else:
                        dc = 1 if raw_dx >= 0 else -1
                base_row, base_col = self._to_grid(ax, ay)
                for i in range(count):
                    step = i + 1
                    self.positions[(cluster, player, i)] = (base_row + dr * step, base_col + dc * step)

            # Home cluster: anchored on the COME OUT SPOT hole itself, then
            # offset outward/along from there (see HOME_OFFSETS comment).
            _place("home", hole_xy[COME_OUT_LOCAL_INDEX], HOME_OFFSETS)
            # Safe cluster: anchored on the IN SPOT hole itself, running
            # straight inward from there (see SAFE_COUNT comment above).
            _place_radial_line("safe", hole_xy[IN_SPOT_LOCAL_INDEX], SAFE_COUNT)

        self._deconflict()

        rows = [r for (r, c) in self.positions.values()]
        cols = [c for (r, c) in self.positions.values()]
        pad = 2
        min_r, min_c = min(rows) - pad, min(cols) - pad
        self.positions = {k: (r - min_r, c - min_c) for k, (r, c) in self.positions.items()}
        self.height = max(r for r, c in self.positions.values()) + pad + 1
        self.width = max(c for r, c in self.positions.values()) + pad + 1

    @staticmethod
    def _to_grid(x, y):
        return (round(y * ROW_SCALE), round(x * COL_SCALE))

    # Search order for nudging a space to a free cell when float-to-int
    # rounding makes two distinct spaces land on the same character cell.
    # Closest cells first, spiraling outward.
    _NUDGES = [
        (0, 1), (0, -1), (1, 0), (-1, 0),
        (1, 1), (1, -1), (-1, 1), (-1, -1),
        (0, 2), (0, -2), (2, 0), (-2, 0),
    ]

    def _deconflict(self):
        """Guarantee every space gets its own character cell. Rounding
        real-valued layout coordinates to integer terminal cells can
        occasionally collide two distinct (and independently clickable)
        spaces onto the same cell, especially on the tighter hexagon/
        octagon layouts -- silently hiding and making one of them
        unclickable. Nudge later-inserted duplicates to the nearest free
        neighboring cell instead."""
        seen = {}
        for space_id, cell in self.positions.items():
            if cell not in seen:
                seen[cell] = space_id
                continue
            r, c = cell
            for dr, dc in self._NUDGES:
                candidate = (r + dr, c + dc)
                if candidate not in seen:
                    self.positions[space_id] = candidate
                    seen[candidate] = space_id
                    break

    def render_ascii(self, occupants=None, highlights=None):
        """Render a plain-text grid for quick visual sanity checking.

        occupants: dict space_id -> single-character label (e.g. player color initial)
        highlights: set of space_id to wrap in [] to show as selectable
        """
        occupants = occupants or {}
        highlights = highlights or set()
        grid = [[" "] * self.width for _ in range(self.height)]
        for space_id, (r, c) in self.positions.items():
            ch = occupants.get(space_id, ".")
            grid[r][c] = ch
        lines = ["".join(row) for row in grid]
        return "\n".join(lines)
