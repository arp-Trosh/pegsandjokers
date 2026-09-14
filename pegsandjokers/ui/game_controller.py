"""UI-framework-independent game state and interaction logic.

This is the "brain" shared by whatever widget/screen ends up drawing the
board: it owns the network connection, the last state snapshot from the
server, and the click-by-click move-selection state machine. None of it
imports Textual (or curses) -- it only deals in plain data (space-id
tuples, card indices, dicts from the wire protocol), so it can be unit
tested on its own and is exactly as reusable as game/ and net/ already are.
"""


def _loceq(a, b):
    return tuple(a) == tuple(b)


class GameController:
    def __init__(self, conn, name, color, num_players, player_id, is_host, board):
        self.conn = conn
        self.name = name
        self.color = color
        self.num_players = num_players
        self.player_id = player_id
        self.is_host = is_host
        self.board = board

        self.state = None
        self.chat_log = []  # (kind, color, text)
        self.game_over_msg = None

        self.card_idx = None
        self.candidates = []
        self.step_index = 0
        self.pending_from = None

    # -- networking ----------------------------------------------------
    def drain_network(self):
        """Process every message received since the last call. Returns True
        if anything changed that the UI should redraw for."""
        changed = False
        for msg in self.conn.poll():
            self.apply_message(msg)
            changed = True
        return changed

    def apply_message(self, msg):
        """Handle exactly one message from the server. Split out from
        drain_network so the connect screen's join handshake -- which has
        to scan the same incoming queue looking for the 'welcome' reply --
        can hand any *other* messages it happened to also pull off the
        queue (a 'state' or 'system_msg' broadcast right behind it) to the
        controller instead of silently dropping them."""
        t = msg.get("type")
        if t == "welcome":
            self.player_id = msg["player_id"]
            self.is_host = msg["is_host"]
        elif t == "state":
            self.state = msg["state"]
        elif t == "chat":
            self.chat_log.append(("chat", msg["color"], f"{msg['name']}: {msg['text']}"))
        elif t == "system_msg":
            self.chat_log.append(("system", None, msg["text"]))
        elif t == "move_options":
            if msg["card_index"] == self.card_idx:
                self.candidates = msg["moves"]
                self.step_index = 0
                self.pending_from = None
        elif t == "game_over":
            self.game_over_msg = f"GAME OVER -- {msg['winner_name']} wins!"
        elif t == "_connection_lost":
            self.chat_log.append(("system", None, "Connection to server lost."))
        if len(self.chat_log) > 300:
            self.chat_log = self.chat_log[-300:]

    # -- chat / commands -------------------------------------------------
    def send_chat_or_command(self, text):
        text = text.strip()
        if not text:
            return
        if text.startswith("/"):
            return self._handle_command(text)
        else:
            self.conn.send({"type": "chat", "text": text})

    def _handle_command(self, text):
        parts = text[1:].strip().split()
        cmd = parts[0].lower() if parts else ""
        if cmd == "rules":
            return "rules"
        self.chat_log.append(("system", None, f"Unknown command: /{cmd}. Try /rules."))
        return None

    # -- host controls -----------------------------------------------------
    def host_begin(self):
        self.conn.send({"type": "host_control", "action": "begin"})

    def host_restart(self):
        self.conn.send({"type": "host_control", "action": "restart"})

    def host_end(self):
        self.conn.send({"type": "host_control", "action": "end"})

    # -- turn / hand helpers -------------------------------------------------
    def my_turn(self):
        return bool(
            self.state
            and self.state.get("turn_player") == self.player_id
            and self.state.get("phase") == "playing"
        )

    def my_hand(self):
        if not self.state or self.player_id is None:
            return None
        p = self.state["players"].get(str(self.player_id))
        return p.get("hand") if p else None

    # -- move selection state machine ---------------------------------------
    def select_card(self, idx):
        if not self.my_turn():
            return
        hand = self.my_hand()
        if hand is None or idx >= len(hand):
            return
        if self.card_idx == idx:
            return
        self.card_idx = idx
        self.candidates = []
        self.step_index = 0
        self.pending_from = None
        self.conn.send({"type": "request_moves", "card_index": idx})

    def cancel_selection(self):
        self.card_idx = None
        self.candidates = []
        self.step_index = 0
        self.pending_from = None

    def try_discard(self):
        if self.card_idx is not None and self.my_turn():
            self.conn.send({"type": "forced_discard", "card_index": self.card_idx})
        self.cancel_selection()

    def click_space(self, space):
        """Returns True if the click was consumed as part of a move (whether
        or not it completed one), False if it didn't match anything."""
        if not self.candidates:
            return False
        k = self.step_index
        if self.pending_from is None:
            matches = [
                m for m in self.candidates
                if k < len(m["steps"]) and _loceq(m["steps"][k]["from"], space)
            ]
            if not matches:
                return False
            self.candidates = matches
            self.pending_from = space
            return True
        matches = [
            m for m in self.candidates
            if _loceq(m["steps"][k]["from"], self.pending_from) and _loceq(m["steps"][k]["to"], space)
        ]
        if not matches:
            return False
        self.candidates = matches
        self.pending_from = None
        self.step_index += 1
        complete = [m for m in self.candidates if len(m["steps"]) == self.step_index]
        if complete:
            self._submit(complete[0])
        return True

    def _submit(self, move):
        self.conn.send({"type": "submit_move", "move": move})
        self.cancel_selection()

    def current_highlight(self):
        """dict: space_tuple -> True for every space that should be drawn
        as clickable right now."""
        if not self.candidates:
            return {}
        k = self.step_index
        out = {}
        if self.pending_from is None:
            for m in self.candidates:
                if k < len(m["steps"]):
                    out[tuple(m["steps"][k]["from"])] = True
        else:
            for m in self.candidates:
                if k < len(m["steps"]) and _loceq(m["steps"][k]["from"], self.pending_from):
                    out[tuple(m["steps"][k]["to"])] = True
        return out

    def occupant_color(self, space_id):
        if self.state is None:
            return None
        for peg in self.state["pegs"]:
            if tuple(peg["location"]) == tuple(space_id):
                p = self.state["players"].get(str(peg["owner"]))
                return p["color"] if p else None
        return None
