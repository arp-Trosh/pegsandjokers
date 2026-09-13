"""Curses TUI: renders the board / chat / hand, and turns mouse clicks and
key presses into game actions. All game-legality decisions still come from
the server; this file only narrows the server-provided list of legal moves
down as the player clicks pegs and destinations.
"""
import curses
import string
import textwrap

from ..game.board import Board, Layout
from ..game.cards import Card
from . import colors
from .rules_text import RULES_LINES

CHAT_H = 8
HAND_H = 2
CHAT_MAX_LEN = 300  # keep in sync with the server's own cap in net/server.py
CHAT_WARN_LEN = int(CHAT_MAX_LEN * 0.8)  # start showing a counter this close to the cap

KEY_TAGS = string.ascii_lowercase


def _loceq(a, b):
    return tuple(a) == tuple(b)


class TuiApp:
    def __init__(self, stdscr, conn, name, color, num_players, player_id, is_host):
        self.stdscr = stdscr
        self.conn = conn
        self.name = name
        self.color = color
        self.num_players = num_players
        self.board = Board(num_players)
        self.layout = Layout(self.board)

        self.player_id = player_id
        self.is_host = is_host
        self.state = None
        self.chat_log = []  # (kind, color, text)

        self.card_idx = None
        self.candidates = []
        self.step_index = 0
        self.pending_from = None

        self.chat_typing = False
        self.chat_buffer = ""

        self.overlay = None  # None, or {"title": str, "lines": [str, ...]}
        self.overlay_scroll = 0

        self.hit_map = {}
        self.key_tag_map = {}
        self.running = True
        self.game_over_msg = None

    # ------------------------------------------------------------------
    def run(self):
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.timeout(100)
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        except curses.error:
            pass
        colors.init_colors()

        while self.running:
            self._drain_network()
            self._handle_input()
            self._draw()

    # -- networking ------------------------------------------------------
    def _drain_network(self):
        for msg in self.conn.poll():
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
                self.game_over_msg = f"GAME OVER -- team {msg['winner_team']} wins!"
            elif t == "_connection_lost":
                self.chat_log.append(("system", None, "Connection to server lost."))
        if len(self.chat_log) > 300:
            self.chat_log = self.chat_log[-300:]

    # -- input -------------------------------------------------------------
    def _handle_input(self):
        try:
            ch = self.stdscr.getch()
        except curses.error:
            return
        if ch == -1:
            return

        if self.overlay is not None:
            self._handle_overlay_key(ch)
            return

        if self.chat_typing:
            self._handle_chat_key(ch)
            return

        if ch == curses.KEY_MOUSE:
            try:
                _, mx, my, _, _ = curses.getmouse()
            except curses.error:
                return
            entity = self.hit_map.get((my, mx))
            if entity:
                self._activate(entity)
            return

        if ch in (ord("q"), ord("Q")):
            self.running = False
            return
        if ch in (ord("t"), ord("T")):
            self.chat_typing = True
            self.chat_buffer = ""
            return
        if ch in (ord("c"), ord("C")):
            self._cancel_selection()
            return
        if ch in (ord("x"), ord("X")):
            self._try_discard()
            return
        if ord("1") <= ch <= ord("5"):
            self._select_card(ch - ord("1"))
            return
        if self.is_host and ch in (ord("b"), ord("B")):
            self.conn.send({"type": "host_control", "action": "begin"})
            return
        if self.is_host and ch in (ord("r"), ord("R")):
            self.conn.send({"type": "host_control", "action": "restart"})
            return
        if self.is_host and ch in (ord("e"), ord("E")):
            self.conn.send({"type": "host_control", "action": "end"})
            return
        if 0 <= ch < 256:
            c = chr(ch)
            if c in self.key_tag_map:
                self._activate(self.key_tag_map[c])

    def _handle_overlay_key(self, ch):
        lines = self.overlay["wrapped"]
        page = max(1, self._overlay_page_size())
        if ch in (curses.KEY_UP, ord("k")):
            self.overlay_scroll = max(0, self.overlay_scroll - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.overlay_scroll = min(max(0, len(lines) - page), self.overlay_scroll + 1)
        elif ch in (curses.KEY_PPAGE,):
            self.overlay_scroll = max(0, self.overlay_scroll - page)
        elif ch in (curses.KEY_NPAGE,):
            self.overlay_scroll = min(max(0, len(lines) - page), self.overlay_scroll + page)
        else:
            # Any other key (Enter, Esc, q, a click via KEY_MOUSE, ...) closes it.
            self.overlay = None
            self.overlay_scroll = 0

    def _overlay_page_size(self):
        h, _ = self.stdscr.getmaxyx()
        return max(1, h - 4)

    def _open_rules_overlay(self):
        self.overlay = {"title": "Pegs & Jokers -- Rules", "raw": RULES_LINES, "wrapped": []}
        self.overlay_scroll = 0

    def _handle_command(self, text):
        parts = text[1:].strip().split()
        cmd = parts[0].lower() if parts else ""
        if cmd == "rules":
            self._open_rules_overlay()
        else:
            self.chat_log.append(("system", None, f"Unknown command: /{cmd}. Try /rules."))

    def _handle_chat_key(self, ch):
        if ch in (10, 13, curses.KEY_ENTER):
            text = self.chat_buffer.strip()
            if text.startswith("/"):
                self._handle_command(text)
            elif text:
                self.conn.send({"type": "chat", "text": text})
            self.chat_typing = False
            self.chat_buffer = ""
        elif ch == 27:  # Esc
            self.chat_typing = False
            self.chat_buffer = ""
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            self.chat_buffer = self.chat_buffer[:-1]
        elif 32 <= ch < 127:
            if len(self.chat_buffer) < CHAT_MAX_LEN:
                self.chat_buffer += chr(ch)

    # -- game actions ------------------------------------------------------
    def _activate(self, entity):
        kind = entity[0]
        if kind == "card":
            self._select_card(entity[1])
        elif kind == "cancel":
            self._cancel_selection()
        elif kind == "discard":
            self._try_discard()
        elif kind == "space":
            self._click_space(entity[1])
        elif kind == "chat_input":
            self.chat_typing = True
            self.chat_buffer = ""

    def _my_turn(self):
        return self.state and self.state.get("turn_player") == self.player_id \
            and self.state.get("phase") == "playing"

    def _select_card(self, idx):
        if not self._my_turn():
            return
        hand = self._my_hand()
        if hand is None or idx >= len(hand):
            return
        if self.card_idx == idx:
            return
        self.card_idx = idx
        self.candidates = []
        self.step_index = 0
        self.pending_from = None
        self.conn.send({"type": "request_moves", "card_index": idx})

    def _cancel_selection(self):
        self.card_idx = None
        self.candidates = []
        self.step_index = 0
        self.pending_from = None

    def _try_discard(self):
        if self.card_idx is not None and self._my_turn():
            self.conn.send({"type": "forced_discard", "card_index": self.card_idx})
        self._cancel_selection()

    def _click_space(self, space):
        if not self.candidates:
            return
        k = self.step_index
        if self.pending_from is None:
            matches = [m for m in self.candidates
                       if k < len(m["steps"]) and _loceq(m["steps"][k]["from"], space)]
            if not matches:
                return
            self.candidates = matches
            self.pending_from = space
        else:
            matches = [m for m in self.candidates
                       if _loceq(m["steps"][k]["from"], self.pending_from)
                       and _loceq(m["steps"][k]["to"], space)]
            if not matches:
                return
            self.candidates = matches
            self.pending_from = None
            self.step_index += 1
            complete = [m for m in self.candidates if len(m["steps"]) == self.step_index]
            if complete:
                self._submit(complete[0])

    def _submit(self, move):
        self.conn.send({"type": "submit_move", "move": move})
        self._cancel_selection()

    def _my_hand(self):
        if not self.state or self.player_id is None:
            return None
        p = self.state["players"].get(str(self.player_id))
        if not p:
            return None
        return p.get("hand")

    def _current_highlight(self):
        """Return dict space_tuple -> True for spaces to highlight right now."""
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

    # -- drawing -------------------------------------------------------------
    def _safe_addstr(self, win, y, x, text, attr=0):
        try:
            h, w = win.getmaxyx()
        except curses.error:
            return
        if y < 0 or y >= h or x >= w:
            return
        if x < 0:
            text = text[-x:]
            x = 0
        maxlen = w - x - 1 if x + len(text) >= w else len(text)
        if maxlen <= 0:
            return
        try:
            win.addstr(y, x, text[:maxlen], attr)
        except curses.error:
            pass

    def _draw(self):
        stdscr = self.stdscr
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        self.hit_map = {}
        self.key_tag_map = {}

        if self.overlay is not None:
            self._draw_overlay(stdscr, h, w)
            stdscr.refresh()
            return

        self._draw_status(stdscr, w)

        board_top = 1
        self._draw_board(stdscr, board_top, h, w)

        chat_top = board_top + self.layout.height + 1
        self._draw_chat_and_players(stdscr, chat_top, h, w)

        hand_top = chat_top + CHAT_H + 1
        self._draw_hand(stdscr, hand_top, h, w)

        self._draw_input_line(stdscr, hand_top + HAND_H, w)

        stdscr.refresh()

    def _draw_overlay(self, stdscr, h, w):
        wrap_width = max(20, w - 4)
        wrapped = []
        for line in self.overlay["raw"]:
            if line == "":
                wrapped.append("")
            else:
                wrapped.extend(textwrap.wrap(line, wrap_width) or [""])
        self.overlay["wrapped"] = wrapped

        page = self._overlay_page_size()
        self.overlay_scroll = max(0, min(self.overlay_scroll, max(0, len(wrapped) - page)))

        title = self.overlay["title"]
        self._safe_addstr(stdscr, 0, 0, title, colors.turn_attr())
        for i in range(page):
            src = self.overlay_scroll + i
            if src >= len(wrapped):
                break
            self._safe_addstr(stdscr, 1 + i, 2, wrapped[src], colors.dim_attr())
        footer_y = min(h - 1, page + 1)
        more = " -- more below, [j]/Down to scroll" if self.overlay_scroll + page < len(wrapped) else ""
        self._safe_addstr(stdscr, footer_y, 0,
                           f"[Up/Down] scroll  [Enter/Esc/q] close{more}", colors.turn_attr())

    def _draw_status(self, stdscr, w):
        if self.state is None:
            self._safe_addstr(stdscr, 0, 0, "Connecting...", colors.dim_attr())
            return
        phase = self.state["phase"]
        if self.game_over_msg:
            self._safe_addstr(stdscr, 0, 0, self.game_over_msg, colors.turn_attr())
            return
        if phase == "lobby":
            n = sum(1 for p in self.state["players"].values())
            msg = f"LOBBY: {n}/{self.num_players} players joined."
            if self.is_host:
                msg += "  [b]egin  " if n >= self.num_players else "  (waiting for players)  "
            self._safe_addstr(stdscr, 0, 0, msg, colors.dim_attr())
            return
        if phase == "finished":
            msg = "GAME ENDED by host."
            if self.is_host:
                msg += "  [r]estart"
            self._safe_addstr(stdscr, 0, 0, msg, colors.turn_attr())
            return

        turn_pid = self.state["turn_player"]
        turn_p = self.state["players"].get(str(turn_pid), {})
        turn_name = turn_p.get("name", "?")
        if turn_pid == self.player_id:
            if self.card_idx is None:
                instr = "Your turn: click a card to play."
            elif not self.candidates:
                instr = "No legal moves with that card -- pick another, or [x] to discard if you're stuck."
            elif self.pending_from is None:
                instr = "Click the highlighted peg you want to move (or [c]ancel)."
            else:
                instr = "Click a highlighted destination (or [c]ancel)."
            msg = f"YOUR TURN -- {instr}"
            attr = colors.turn_attr()
        else:
            msg = f"Turn: {turn_name}"
            attr = colors.dim_attr()
        if self.is_host:
            msg += "   [host: r=restart e=end]"
        self._safe_addstr(stdscr, 0, 0, msg, attr)

    def _occupant_color(self, space_id):
        if self.state is None:
            return None
        for peg in self.state["pegs"]:
            if tuple(peg["location"]) == tuple(space_id):
                p = self.state["players"].get(str(peg["owner"]))
                return p["color"] if p else None
        return None

    def _draw_board(self, stdscr, top, screen_h, screen_w):
        left = max(0, (screen_w - self.layout.width) // 2)
        highlight = self._current_highlight()
        tag_iter = iter(KEY_TAGS)

        for space_id, (r, c) in self.layout.positions.items():
            y = top + r
            x = left + c
            if y < 0 or y >= screen_h or x < 0 or x >= screen_w:
                continue
            # normalize space_id for lookups: ("track", gid) or ("home"/"safe", owner, slot)
            if space_id[0] == "track":
                lookup_id = ("track", space_id[1])
            else:
                lookup_id = (space_id[0], space_id[1], space_id[2])

            occ_color = self._occupant_color(lookup_id)
            is_hl = lookup_id in highlight
            ch = "."
            attr = colors.home_safe_attr() if space_id[0] in ("home", "safe") else colors.dim_attr()
            if occ_color:
                ch = occ_color[0].upper()
                attr = colors.player_attr(occ_color)
            if is_hl:
                attr = colors.highlight_attr()
                tag = next(tag_iter, None)
                if tag:
                    self.key_tag_map[tag] = ("space", list(lookup_id))
                    ch = tag
            self._safe_addstr(stdscr, y, x, ch, attr)
            self.hit_map[(y, x)] = ("space", list(lookup_id))

    def _wrap_chat_log(self, chat_w):
        """Word-wrap every chat/system log entry to chat_w, returning a flat
        list of (kind, color, display_line) -- one entry per display row.
        Wrapping (instead of truncating) is what lets a player on a narrow
        terminal still read a long message from someone on a wider one;
        continuation lines are indented so a new message is easy to spot."""
        out = []
        width = max(10, chat_w)
        for kind, color, text in self.chat_log:
            for line in textwrap.wrap(text, width, subsequent_indent="  ") or [""]:
                out.append((kind, color, line))
        return out

    def _draw_chat_and_players(self, stdscr, top, screen_h, screen_w):
        chat_w = max(20, int(screen_w * 0.62))
        for i in range(CHAT_H):
            y = top + i
            if y >= screen_h:
                break
            self._safe_addstr(stdscr, y, 0, " " * min(screen_w, chat_w + 20))
        wrapped = self._wrap_chat_log(chat_w)
        lines = wrapped[-CHAT_H:]
        for i, (kind, color, text) in enumerate(lines):
            y = top + i
            attr = colors.game_msg_attr() if kind == "system" else colors.player_attr(color or "white")
            self._safe_addstr(stdscr, y, 0, text, attr)

        # player / turn panel to the right of chat
        panel_x = chat_w + 2
        if self.state and panel_x < screen_w - 5:
            self._safe_addstr(stdscr, top, panel_x, "Players:", colors.dim_attr())
            row = top + 1
            for pid_str, p in sorted(self.state["players"].items(), key=lambda kv: int(kv[0])):
                if row >= top + CHAT_H:
                    break
                safe_count = sum(
                    1 for peg in self.state["pegs"]
                    if peg["owner"] == int(pid_str) and peg["location"][0] == "safe"
                )
                you = " (you)" if int(pid_str) == self.player_id else ""
                turn_marker = ">" if self.state.get("turn_player") == int(pid_str) else " "
                label = f"{turn_marker}{p['name']}{you} [{safe_count}/5 safe]"
                attr = colors.player_attr(p["color"])
                if not p.get("connected", True):
                    attr = colors.dim_attr()
                self._safe_addstr(stdscr, row, panel_x, label, attr)
                row += 1

    def _draw_hand(self, stdscr, top, screen_h, screen_w):
        hand = self._my_hand() or []
        x = 0
        y = top
        if y >= screen_h:
            return
        self._safe_addstr(stdscr, y, x, " " * screen_w)
        for i, card in enumerate(hand):
            c = Card.from_dict(card)
            label = f"[{i + 1}:{c.short()}]"
            attr = colors.player_attr(self.color)
            if self.card_idx == i:
                attr = colors.highlight_attr()
            self._safe_addstr(stdscr, y, x, label, attr)
            for dx in range(len(label)):
                self.hit_map[(y, x + dx)] = ("card", i)
            x += len(label) + 1

        cancel_label = "[Cancel]"
        self._safe_addstr(stdscr, y, x, cancel_label, colors.dim_attr())
        for dx in range(len(cancel_label)):
            self.hit_map[(y, x + dx)] = ("cancel",)
        x += len(cancel_label) + 1

        discard_label = "[Discard]"
        self._safe_addstr(stdscr, y, x, discard_label, colors.dim_attr())
        for dx in range(len(discard_label)):
            self.hit_map[(y, x + dx)] = ("discard",)

    def _draw_input_line(self, stdscr, y, screen_w):
        max_y = self.stdscr.getmaxyx()[0]
        if y >= max_y:
            return
        if self.chat_typing:
            # Wrap the in-progress message across as many rows as it needs
            # (growing downward past `y`) so a long message stays fully
            # visible while typing instead of scrolling off to the right.
            # This is the last thing drawn each frame and nothing else is
            # positioned below it, so extra rows never disturb the board,
            # chat, or hand above.
            prefix = "chat> "
            indent = " " * len(prefix)
            wrapped = textwrap.wrap(
                prefix + self.chat_buffer, max(10, screen_w), subsequent_indent=indent
            ) or [prefix]
            for i, line in enumerate(wrapped):
                row = y + i
                if row >= max_y:
                    break
                self._safe_addstr(stdscr, row, 0, " " * screen_w)
                self._safe_addstr(stdscr, row, 0, line, colors.player_attr(self.color))

            # A silent per-keystroke cap with no feedback just looks like
            # the game stopped responding once you hit it. Show nothing for
            # a normal-length message, a quiet counter once you're close to
            # the cap, and an impossible-to-miss notice right at it.
            length = len(self.chat_buffer)
            status_row = y + len(wrapped)
            if length >= CHAT_MAX_LEN:
                status = f"[{length}/{CHAT_MAX_LEN}] Maximum message length reached -- press Enter to send"
                status_attr = colors.highlight_attr()
            elif length >= CHAT_WARN_LEN:
                status = f"[{length}/{CHAT_MAX_LEN}]"
                status_attr = colors.dim_attr()
            else:
                status = None
            if status and status_row < max_y:
                self._safe_addstr(stdscr, status_row, 0, " " * screen_w)
                self._safe_addstr(stdscr, status_row, 0, status, status_attr)
        else:
            self._safe_addstr(stdscr, y, 0, " " * screen_w)
            hint = "[t]ype chat (/rules for help)  [1-5] pick card  click board  [c]ancel  [x]discard  [q]uit"
            self._safe_addstr(stdscr, y, 0, hint, colors.dim_attr())
            for dx in range(6):
                self.hit_map[(y, dx)] = ("chat_input",)
