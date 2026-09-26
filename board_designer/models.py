"""Data model for the Pegs & Jokers board-layout designer.

Deliberately standalone from the pegsandjokers game package -- this tool
only needs to agree with the game on a *file format* (see README.md), not
on code. The constants below (ARM_LEN, HOME_COUNT, SAFE_COUNT, BOARD_SLOTS)
mirror pegsandjokers/game/board.py as of when this tool was written; if
that module's numbers ever change, update these too so seeded layouts stay
the right shape.

A "space" is one hole on the board, identified by a tuple:
  ("track", gid)      -- gid 0..slots*ARM_LEN-1, the shared ring
  ("home", seat, i)    -- i 0..HOME_COUNT-1, one seat's HOME cluster
  ("safe", seat, i)    -- i 0..SAFE_COUNT-1, one seat's SAFE line

"seat" is a board position 0..slots-1, same numbering game/board.py uses
for player_at_seat/seat_of_player (for 6/8 players, seat == player index).
"""
import json
import math
import os

ARM_LEN = 18
HOME_COUNT = 5
SAFE_COUNT = 5
BOARD_SLOTS = {6: 6, 8: 8}

# Position, within one seat's own 18-hole arm, of the two special track
# holes: COME OUT SPOT (where a peg leaves the main track for HOME) and
# IN SPOT (where a peg leaves the main track for SAFE). Same indices as
# pegsandjokers/game/board.py's COME_OUT_LOCAL_INDEX/IN_SPOT_LOCAL_INDEX.
COME_OUT_LOCAL_INDEX = 8
IN_SPOT_LOCAL_INDEX = 3

ROW_SCALE = 1
COL_SCALE = 2
HOLE_UNIT = 1.0

# Same anchor offsets game/board.py seeds HOME with -- see that module's
# HOME_OFFSETS comment for what "along"/"perp" mean.
HOME_OFFSETS = [(-1, 2), (-2, 1), (0, 1), (-2, 3), (0, 3)]

# Empty cells always kept free on every edge so there's room to drag
# spaces outward without falling off the canvas.
MARGIN = 20

LAYOUTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "layouts")


def default_path(num_players):
    return os.path.join(LAYOUTS_DIR, f"{num_players}player.json")


def space_id_to_key(space_id):
    if space_id[0] == "track":
        return f"track:{space_id[1]}"
    kind, seat, i = space_id
    return f"{kind}:{seat}:{i}"


def key_to_space_id(key):
    parts = key.split(":")
    if parts[0] == "track":
        return ("track", int(parts[1]))
    kind, seat, i = parts
    return (kind, int(seat), int(i))


def space_order(num_players):
    """Canonical order for Tab-cycling: seat by seat, each seat's arm holes
    then its HOME cluster then its SAFE line."""
    slots = BOARD_SLOTS[num_players]
    order = []
    for seat in range(slots):
        for i in range(ARM_LEN):
            order.append(("track", seat * ARM_LEN + i))
        for i in range(HOME_COUNT):
            order.append(("home", seat, i))
        for i in range(SAFE_COUNT):
            order.append(("safe", seat, i))
    return order


def seat_of(space_id):
    if space_id[0] == "track":
        return space_id[1] // ARM_LEN
    return space_id[1]


def is_come_out(space_id):
    return space_id[0] == "track" and space_id[1] % ARM_LEN == COME_OUT_LOCAL_INDEX


def is_in_spot(space_id):
    return space_id[0] == "track" and space_id[1] % ARM_LEN == IN_SPOT_LOCAL_INDEX


def generate_seed(num_players):
    """Starting layout: the same regular-polygon construction
    pegsandjokers/game/board.py::Layout uses today -- the layout that looks
    bad for 6/8 players. It's only meant as a starting point to drag into
    something better, not a source of truth.
    """
    slots = BOARD_SLOTS[num_players]
    side_length = ARM_LEN * HOLE_UNIT
    radius = side_length / (2 * math.sin(math.pi / slots))
    start_angle = math.pi / 2 + math.pi / slots
    verts = []
    for i in range(slots):
        angle = start_angle + i * (2 * math.pi / slots)
        verts.append((radius * math.cos(angle), radius * math.sin(angle)))

    def to_grid(x, y):
        return (round(y * ROW_SCALE), round(x * COL_SCALE))

    positions = {}
    for seat in range(slots):
        vx, vy = verts[seat]
        nx, ny = verts[(seat + 1) % slots]
        mx, my = (vx + nx) / 2, (vy + ny) / 2
        norm = math.hypot(mx, my) or 1.0
        out_x, out_y = mx / norm, my / norm
        arm_len_px = math.hypot(nx - vx, ny - vy) or 1.0
        along_x, along_y = (nx - vx) / arm_len_px, (ny - vy) / arm_len_px
        hole_spacing = arm_len_px / ARM_LEN

        hole_xy = {}
        for i in range(ARM_LEN):
            t = i / ARM_LEN
            x = vx + (nx - vx) * t
            y = vy + (ny - vy) * t
            hole_xy[i] = (x, y)
            positions[("track", seat * ARM_LEN + i)] = to_grid(x, y)

        diag_factor = max(abs(out_x), abs(out_y)) or 1.0
        perp_boost = 1.0 + 4.0 * (1.0 - diag_factor)

        ax, ay = hole_xy[8]
        for i, (along, perp) in enumerate(HOME_OFFSETS):
            perp *= -perp_boost
            x = ax + along * hole_spacing * along_x + perp * hole_spacing * out_x
            y = ay + along * hole_spacing * along_y + perp * hole_spacing * out_y
            positions[("home", seat, i)] = to_grid(x, y)

        in_x, in_y = hole_xy[3]
        raw_dx = -perp_boost * hole_spacing * out_x
        raw_dy = -perp_boost * hole_spacing * out_y
        dr = round(raw_dy * ROW_SCALE)
        dc = round(raw_dx * COL_SCALE)
        if dr == 0 and dc == 0:
            if abs(raw_dy * ROW_SCALE) >= abs(raw_dx * COL_SCALE):
                dr = 1 if raw_dy >= 0 else -1
            else:
                dc = 1 if raw_dx >= 0 else -1
        base_row, base_col = to_grid(in_x, in_y)
        for i in range(SAFE_COUNT):
            step = i + 1
            positions[("safe", seat, i)] = (base_row + dr * step, base_col + dc * step)

    return shift_into_bounds(positions)


def shift_into_bounds(positions):
    """Shift the whole layout so nothing is within MARGIN cells of the top
    or left edge -- keeps an effectively infinite canvas instead of letting
    dragged spaces clip at 0."""
    rows = [r for r, c in positions.values()]
    cols = [c for r, c in positions.values()]
    min_r, min_c = min(rows), min(cols)
    shift_r = MARGIN - min_r if min_r < MARGIN else 0
    shift_c = MARGIN - min_c if min_c < MARGIN else 0
    if not shift_r and not shift_c:
        return positions
    return {k: (r + shift_r, c + shift_c) for k, (r, c) in positions.items()}


def bounds(positions):
    """(height, width) needed to show every space plus a MARGIN-wide strip
    of empty canvas below/right to drag into."""
    rows = [r for r, c in positions.values()]
    cols = [c for r, c in positions.values()]
    return max(rows) + MARGIN, max(cols) + MARGIN


def collisions(positions):
    """cell -> [space_ids] for every cell shared by more than one space."""
    by_cell = {}
    for sid, cell in positions.items():
        by_cell.setdefault(cell, []).append(sid)
    return {cell: ids for cell, ids in by_cell.items() if len(ids) > 1}


def save(path, num_players, positions):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ordered = sorted(positions.items(), key=lambda kv: space_id_to_key(kv[0]))
    data = {
        "num_players": num_players,
        "slots": BOARD_SLOTS[num_players],
        "arm_len": ARM_LEN,
        "home_count": HOME_COUNT,
        "safe_count": SAFE_COUNT,
        "positions": {space_id_to_key(sid): list(cell) for sid, cell in ordered},
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load(path):
    with open(path) as f:
        data = json.load(f)
    num_players = data["num_players"]
    positions = {key_to_space_id(k): tuple(v) for k, v in data["positions"].items()}
    expected = set(space_order(num_players))
    got = set(positions)
    if got != expected:
        missing = len(expected - got)
        extra = len(got - expected)
        raise ValueError(
            f"{path} doesn't match a {num_players}-player board "
            f"({missing} space(s) missing, {extra} unexpected)"
        )
    return num_players, positions
