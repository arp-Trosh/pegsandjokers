"""Move legality and application for Pegs and Jokers.

The server is authoritative: it calls `legal_moves_for_card` to find every
legal way to play a given hand card, and `apply_move` to commit one of
those moves to the GameState. The UI never decides legality itself -- it
only narrows the list of legal moves down as the player clicks things.
"""
from contextlib import contextmanager

from .board import SAFE_COUNT
from .cards import MOVE_VALUES

TEAM_PARTNER = "partner"
TEAM_OPPONENT = "opponent"


def _relationship(state, mover, other_owner):
    if other_owner == mover:
        return "self"
    if state.teammate(mover) == other_owner:
        return TEAM_PARTNER
    return TEAM_OPPONENT


def _walk_forward(board, owner, pos, n):
    """Compute the path (list of locations) a peg on the main track takes
    moving forward n>=1 holes, correctly branching into the owner's SAFE
    area when it reaches/passes their IN SPOT (or passing straight over it
    if the move would overshoot the SAFE area's capacity)."""
    in_spot = board.in_spot(owner)
    dist_to_in = board.distance_forward(pos, in_spot)
    if n <= dist_to_in:
        return [("track", board.step_forward(pos, k)) for k in range(1, n + 1)]
    overflow = n - dist_to_in
    if overflow <= SAFE_COUNT:
        path = [("track", board.step_forward(pos, k)) for k in range(1, dist_to_in + 1)]
        path += [("safe", owner, s) for s in range(0, overflow)]
        return path
    # overshoots the SAFE area entirely: must pass straight by and keep
    # going around the shared main track.
    return [("track", board.step_forward(pos, k)) for k in range(1, n + 1)]


def _peg_path(board, peg, n):
    """Return the path a peg takes moving n holes (n may be negative for a
    backward move), or None if the move doesn't make sense for this peg's
    current location (e.g. asking a HOME or SAFE peg to move backward)."""
    kind = peg.location[0]
    if kind == "track":
        pos = peg.location[1]
        if n > 0:
            return _walk_forward(board, peg.owner, pos, n)
        if n < 0:
            steps = -n
            return [("track", board.step_backward(pos, k)) for k in range(1, steps + 1)]
        return None
    if kind == "safe":
        owner, val = peg.location[1], peg.location[2]
        if n <= 0:
            return None  # can't move backward within/out of SAFE
        new_slot = val + n
        if new_slot > SAFE_COUNT - 1:
            return None  # would overshoot the SAFE area
        return [("safe", owner, s) for s in range(val + 1, new_slot + 1)]
    return None  # HOME pegs don't use this path (see come_out)


def _occupant_at(state, loc):
    kind = loc[0]
    if kind == "track":
        return state.track_occupant(loc[1])
    if kind == "safe":
        return state.safe_occupant(loc[1], loc[2])
    return None


def _simulate(state, board, mover, path):
    """Walk a path checking for a mover's-own-peg blockage anywhere along
    it, and a capture only at the final square. Returns (ok, dest, capture_peg)."""
    capture = None
    for i, loc in enumerate(path):
        occ = _occupant_at(state, loc)
        if occ is None:
            continue
        rel = _relationship(state, mover, occ.owner)
        if rel == "self":
            return False, None, None
        if i == len(path) - 1:
            capture = occ
        # otherwise: legally passing over another player's peg, no effect
    return True, path[-1], capture


def compute_move(state, board, peg, n):
    """Try to move `peg` by n holes (n<0 for backward). Returns a step dict
    or None if illegal."""
    path = _peg_path(board, peg, n)
    if not path:
        return None
    ok, dest, capture = _simulate(state, board, peg.owner, path)
    if not ok:
        return None
    return {"peg": (peg.owner, peg.index), "from": peg.location, "to": dest,
            "capture": (capture.owner, capture.index) if capture else None}


def compute_come_out(state, board, owner, home_peg):
    if home_peg.location[0] != "home":
        return None
    dest = ("track", board.come_out_spot(owner))
    ok, _, capture = _simulate(state, board, owner, [dest])
    if not ok:
        return None
    return {"peg": (owner, home_peg.index), "from": home_peg.location, "to": dest,
            "capture": (capture.owner, capture.index) if capture else None}


def compute_joker_swap(state, board, owner, mover_peg, target_peg):
    """The Joker's wild swap: teleport any of `owner`'s own pegs -- whether
    still in HOME or already out on the track -- onto any other peg
    currently in play, sending that peg home. Not a normal step-by-step
    move, so unlike compute_move it doesn't walk/check a path."""
    if mover_peg.location[0] not in ("home", "track") or target_peg.location[0] != "track":
        return None
    if target_peg.owner == owner:
        return None
    dest = target_peg.location
    return {"peg": (owner, mover_peg.index), "from": mover_peg.location, "to": dest,
            "capture": (target_peg.owner, target_peg.index)}


def _make_move(card_index, steps, label):
    return {"card_index": card_index, "steps": steps, "label": label}


def controlled_owner(state, board, player):
    """Whose pegs `player` is moving this turn. Normally a player moves
    their own pegs; once all five of their own pegs have reached SAFE, the
    rules let them use their cards to move their teammate's pegs instead."""
    if any(p.location[0] != "safe" for p in state.pegs_of(player)):
        return player
    mate = state.teammate(player)
    return mate if mate is not None else player


def legal_moves_for_card(state, board, player, card, card_index):
    moves = []
    owner = controlled_owner(state, board, player)
    out_pegs = [p for p in state.pegs_of(owner) if p.location[0] in ("track", "safe")]
    home_pegs = [p for p in state.pegs_of(owner) if p.location[0] == "home"]

    if card.is_joker:
        for hp in home_pegs:
            r = compute_come_out(state, board, owner, hp)
            if r:
                moves.append(_make_move(card_index, [r], "Joker: come out"))
        # The wild swap can use ANY of the player's own pegs as the mover --
        # one still in HOME, or one already out on the track -- not just
        # HOME pegs. ("Joker - a WILD CARD: replaces any other peg in play
        # with your own peg.")
        movers = home_pegs + [p for p in out_pegs if p.location[0] == "track"]
        for mover in movers:
            for target in state.pegs.values():
                if target.location[0] != "track" or target.owner == owner:
                    continue
                r = compute_joker_swap(state, board, owner, mover, target)
                if r:
                    moves.append(_make_move(card_index, [r], "Joker: wild swap"))
        return moves

    rank = card.rank

    if rank in ("A", "J", "Q", "K"):
        for hp in home_pegs:
            r = compute_come_out(state, board, owner, hp)
            if r:
                moves.append(_make_move(card_index, [r], f"{rank}: come out"))
        value = MOVE_VALUES[rank]
        for op in out_pegs:
            r = compute_move(state, board, op, value)
            if r:
                moves.append(_make_move(card_index, [r], f"Move {value}"))
        return moves

    if rank == "8":
        for op in out_pegs:
            if op.location[0] != "track":
                continue
            r = compute_move(state, board, op, -8)
            if r:
                moves.append(_make_move(card_index, [r], "Move back 8"))
        return moves

    if rank == "7":
        for op in out_pegs:
            r = compute_move(state, board, op, 7)
            if r:
                moves.append(_make_move(card_index, [r], "Move 7"))
        moves.extend(_split_forward_moves(state, board, out_pegs, card_index, 7))
        return moves

    if rank == "9":
        for op in out_pegs:
            r = compute_move(state, board, op, 9)
            if r:
                moves.append(_make_move(card_index, [r], "Move 9"))
        moves.extend(_split_9_moves(state, board, out_pegs, card_index))
        return moves

    # 2,3,4,5,6,10
    value = MOVE_VALUES[rank]
    for op in out_pegs:
        r = compute_move(state, board, op, value)
        if r:
            moves.append(_make_move(card_index, [r], f"Move {value}"))
    return moves


def _split_forward_moves(state, board, out_pegs, card_index, total):
    moves = []
    for pa in out_pegs:
        for amt_a in range(1, total):
            amt_b = total - amt_a
            ra = compute_move(state, board, pa, amt_a)
            if not ra:
                continue
            with _temp_step(state, ra):
                for pb in out_pegs:
                    if pb is pa:
                        continue
                    rb = compute_move(state, board, pb, amt_b)
                    if rb:
                        moves.append(_make_move(
                            card_index, [ra, rb],
                            f"Split 7: {amt_a}/{amt_b}"))
    return moves


def _split_9_moves(state, board, out_pegs, card_index):
    moves = []
    for pa in out_pegs:
        for f in range(1, 9):
            b = 9 - f
            ra = compute_move(state, board, pa, f)
            if not ra:
                continue
            with _temp_step(state, ra):
                for pb in out_pegs:
                    if pb is pa or pb.location[0] != "track":
                        continue
                    rb = compute_move(state, board, pb, -b)
                    if rb:
                        moves.append(_make_move(
                            card_index, [ra, rb],
                            f"Split 9: forward {f} / back {b}"))
    return moves


@contextmanager
def _temp_step(state, step):
    """Temporarily apply one move step (peg relocation + any capture-to-home)
    so a dependent second move can be legality-checked, then undo it."""
    owner, idx = step["peg"]
    peg = state.pegs[(owner, idx)]
    old_loc = peg.location
    cap = step["capture"]
    cap_peg = None
    cap_old_loc = None
    if cap:
        cap_peg = state.pegs[cap]
        cap_old_loc = cap_peg.location
        cap_peg.location = ("home", cap_peg.owner, -1)  # temporarily off-board; slot -1 never matches a real space
    peg.location = step["to"]
    try:
        yield
    finally:
        peg.location = old_loc
        if cap_peg is not None:
            cap_peg.location = cap_old_loc


def any_legal_move(state, board, player):
    for idx, card in enumerate(state.players[player].hand):
        if legal_moves_for_card(state, board, player, card, idx):
            return True
    return False


def any_forced_legal_move(state, board, player):
    """Like any_legal_move, but ignoring the Joker: the Joker is always
    optional to play, even when it's the only card in hand with a legal
    move, so it must never by itself force a player out of discarding."""
    for idx, card in enumerate(state.players[player].hand):
        if card.is_joker:
            continue
        if legal_moves_for_card(state, board, player, card, idx):
            return True
    return False


def apply_move(state, board, move):
    """Commit a fully-specified move (as returned by legal_moves_for_card)
    to the game state. Handles capture semantics: an opponent's peg is sent
    HOME, a partner's peg is sent to their own IN SPOT."""
    messages = []
    for step in move["steps"]:
        owner, idx = step["peg"]
        peg = state.pegs[(owner, idx)]
        if step["capture"]:
            c_owner, c_idx = step["capture"]
            cap_peg = state.pegs[(c_owner, c_idx)]
            rel = _relationship(state, owner, c_owner)
            if rel == TEAM_PARTNER:
                cap_peg.location = _partner_in_spot_location(board, c_owner)
                messages.append(f"{state.players[owner].name}'s peg sends teammate to their IN SPOT.")
            else:
                state.send_home(cap_peg)
                messages.append(f"{state.players[owner].name}'s peg sends an opponent HOME.")
        # step["to"] may be a plain list here (it round-tripped through JSON
        # from the client) -- normalize to a tuple so later equality-based
        # occupant lookups (track_occupant/safe_occupant) still match it.
        peg.location = tuple(step["to"])
    return messages


def _partner_in_spot_location(board, owner):
    return ("track", board.in_spot(owner))


def describe_move(state, player_name, card, move):
    """Human-readable status line for the chat log describing a just-played
    move, e.g. "Adam played 10 of Hearts, moved 10 spaces forward." or
    "Adam played JOKER. Amanda got JOKERED!"

    Reads off `move["label"]` (set alongside each move by
    legal_moves_for_card et al.) to identify which of the fixed set of move
    shapes was played, rather than re-deriving distances from board
    geometry -- that would have to re-implement the SAFE-area branching a
    second time, whereas the label already unambiguously encodes it.
    """
    label = move["label"]
    card_text = "JOKER" if card.is_joker else card.label().replace(" ", " of ", 1)

    if label == "Joker: wild swap":
        target_owner, _ = move["steps"][0]["capture"]
        target_name = state.players[target_owner].name
        return f"{player_name} played JOKER. {target_name} got JOKERED!"

    played = f"{player_name} played {card_text}"

    if label.endswith(": come out"):
        return f"{played}, came out of HOME."
    if label.startswith("Move back "):
        n = label.rsplit(" ", 1)[-1]
        return f"{played}, moved {n} spaces back."
    if label.startswith("Split 7: "):
        amt_a, amt_b = label.split(": ", 1)[1].split("/")
        return f"{played}, moved {amt_a} and {amt_b} spaces forward."
    if label.startswith("Split 9: "):
        forward_part, back_part = label.split(": ", 1)[1].split(" / ")
        f = forward_part.rsplit(" ", 1)[-1]
        b = back_part.rsplit(" ", 1)[-1]
        return f"{played}, moved {f} spaces forward and {b} spaces backwards."
    if label.startswith("Move "):
        n = label.rsplit(" ", 1)[-1]
        return f"{played}, moved {n} spaces forward."
    return f"{played}."
