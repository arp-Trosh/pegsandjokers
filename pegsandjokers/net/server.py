"""Authoritative game server. Accepts TCP connections, tracks the lobby,
runs the game engine, and broadcasts state to every connected client.

All game-state mutation happens on a single background thread (the "game
loop") that consumes an in-process queue fed by one reader-thread per
connection, so GameState never needs its own locking.
"""
import queue
import socket
import threading
import traceback

from ..game.state import GameState, COLORS
from ..game import rules
from .protocol import LineReader, send


class Connection:
    def __init__(self, conn_id, sock, addr):
        self.conn_id = conn_id
        self.sock = sock
        self.addr = addr
        self.player_id = None
        self.alive = True

    def send(self, msg):
        if not self.alive:
            return
        try:
            send(self.sock, msg)
        except OSError:
            self.alive = False


class GameServer:
    def __init__(self, num_players, port, bind_host="0.0.0.0"):
        self.num_players = num_players
        self.port = port
        self.bind_host = bind_host
        self.state = GameState(num_players)
        self.board = self.state.board
        self.connections = {}  # conn_id -> Connection
        self._conn_lock = threading.Lock()
        self._next_conn_id = 1
        self._next_player_id = 0
        self.host_conn_id = None
        self.queue = queue.Queue()
        self.listen_sock = None
        self._pending_move_context = {}  # player_id -> card_index most recently requested

    # -- lifecycle -----------------------------------------------------
    def start(self):
        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_sock.bind((self.bind_host, self.port))
        self.listen_sock.listen(16)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._game_loop, daemon=True).start()

    def _accept_loop(self):
        while True:
            try:
                sock, addr = self.listen_sock.accept()
            except OSError:
                return
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._conn_lock:
                conn_id = self._next_conn_id
                self._next_conn_id += 1
                conn = Connection(conn_id, sock, addr)
                self.connections[conn_id] = conn
            threading.Thread(target=self._reader_loop, args=(conn,), daemon=True).start()

    def _reader_loop(self, conn: Connection):
        reader = LineReader(conn.sock)
        try:
            while True:
                for msg in reader.read_messages():
                    self.queue.put((conn.conn_id, msg))
        except (ConnectionError, OSError):
            pass
        finally:
            conn.alive = False
            self.queue.put((conn.conn_id, {"type": "_disconnect"}))

    def _game_loop(self):
        while True:
            conn_id, msg = self.queue.get()
            try:
                self._handle(conn_id, msg)
            except Exception:
                traceback.print_exc()

    # -- broadcasting ----------------------------------------------------
    def _broadcast_state(self):
        with self._conn_lock:
            conns = list(self.connections.values())
        for conn in conns:
            if conn.player_id is None:
                conn.send({"type": "state", "state": self.state.to_dict(for_player=None)})
            else:
                conn.send({"type": "state", "state": self.state.to_dict(for_player=conn.player_id)})

    def _broadcast(self, msg):
        with self._conn_lock:
            conns = list(self.connections.values())
        for conn in conns:
            conn.send(msg)

    def _conn_for_player(self, player_id):
        with self._conn_lock:
            for c in self.connections.values():
                if c.player_id == player_id:
                    return c
        return None

    def _send_system(self, player_id, text):
        conn = self._conn_for_player(player_id)
        if conn:
            conn.send({"type": "system_msg", "text": text})

    # -- message dispatch --------------------------------------------------
    def _handle(self, conn_id, msg):
        mtype = msg.get("type")
        if mtype == "_disconnect":
            self._on_disconnect(conn_id)
            return
        with self._conn_lock:
            conn = self.connections.get(conn_id)
        if conn is None:
            return

        if mtype == "join":
            self._on_join(conn, msg)
        elif mtype == "chat":
            self._on_chat(conn, msg)
        elif mtype == "host_control":
            self._on_host_control(conn, msg)
        elif mtype == "request_moves":
            self._on_request_moves(conn, msg)
        elif mtype == "submit_move":
            self._on_submit_move(conn, msg)
        elif mtype == "forced_discard":
            self._on_forced_discard(conn, msg)
        elif mtype == "cycle_team":
            self._on_cycle_team(conn, msg)

    def _on_disconnect(self, conn_id):
        with self._conn_lock:
            conn = self.connections.pop(conn_id, None)
        if conn is None or conn.player_id is None:
            return
        player = self.state.players.get(conn.player_id)
        if player:
            player.connected = False
            self._broadcast({"type": "system_msg", "text": f"{player.name} disconnected."})
        if self.state.phase == GameState.PHASE_PLAYING and self.state.turn_player == conn.player_id:
            self.state.next_turn()
        self._broadcast_state()

    def _on_join(self, conn: Connection, msg):
        if self.state.phase != GameState.PHASE_LOBBY:
            conn.send({"type": "system_msg", "text": "Game already in progress."})
            return
        if len(self.state.players) >= self.num_players:
            conn.send({"type": "system_msg", "text": "Game is full."})
            return
        name = str(msg.get("name") or f"Player{self._next_player_id + 1}")[:20]
        color = msg.get("color")
        taken = {p.color for p in self.state.players.values()}
        if color not in COLORS or color in taken:
            available = [c for c in COLORS if c not in taken]
            color = available[0] if available else COLORS[0]

        player_id = self._next_player_id
        self._next_player_id += 1
        conn.player_id = player_id
        self.state.add_player(player_id, name, color, connection_id=conn.conn_id)
        is_host = self.host_conn_id is None
        if is_host:
            self.host_conn_id = conn.conn_id

        conn.send({
            "type": "welcome",
            "player_id": player_id,
            "color": color,
            "is_host": is_host,
            "num_players": self.num_players,
        })
        conn.send({"type": "system_msg",
                   "text": "Welcome to Pegs and Jokers! Type /rules to learn to play!"})
        self._broadcast({"type": "system_msg", "text": f"{name} joined ({len(self.state.players)}/{self.num_players})."})
        self._broadcast_state()

    def _on_chat(self, conn: Connection, msg):
        if conn.player_id is None:
            return
        player = self.state.players[conn.player_id]
        # Defensive backstop only -- the client already caps typed
        # messages at CHAT_MAX_LEN (ui/game_screen.py) before ever sending one.
        text = str(msg.get("text", ""))[:300]
        if not text:
            return
        self._broadcast({"type": "chat", "name": player.name, "color": player.color, "text": text})

    def _on_host_control(self, conn: Connection, msg):
        if conn.conn_id != self.host_conn_id:
            self._send_system(conn.player_id, "Only the host can control the game.")
            return
        action = msg.get("action")
        if action == "begin":
            if self.state.phase != GameState.PHASE_LOBBY:
                return
            if len(self.state.players) < self.num_players:
                self._send_system(conn.player_id, "Waiting for more players before you can begin.")
                return
            if not self.state.teams_balanced():
                self.state.lobby_error = "UNBALANCED TEAMS. GAME CANNOT BEGIN."
                self._broadcast_state()
                return
            self.state.start_game()
            self._broadcast({"type": "system_msg", "text": "The game has begun!"})
            self._broadcast_state()
        elif action == "restart":
            keep_players = {pid: (p.name, p.color) for pid, p in self.state.players.items()}
            self.state = GameState(self.num_players)
            self.board = self.state.board
            for pid, (name, color) in keep_players.items():
                self.state.add_player(pid, name, color)
            self._broadcast({"type": "system_msg", "text": "Host restarted the game."})
            self._broadcast_state()
        elif action == "end":
            self.state.phase = GameState.PHASE_FINISHED
            self._broadcast({"type": "system_msg", "text": "Host ended the game."})
            self._broadcast_state()

    def _on_cycle_team(self, conn: Connection, msg):
        if conn.player_id is None or self.state.phase != GameState.PHASE_LOBBY:
            return
        self.state.cycle_team(conn.player_id)
        self._broadcast_state()

    def _require_turn(self, conn: Connection):
        if conn.player_id is None:
            return False
        if self.state.phase != GameState.PHASE_PLAYING:
            self._send_system(conn.player_id, "The game hasn't started yet.")
            return False
        if self.state.turn_player != conn.player_id:
            self._send_system(conn.player_id, "It isn't your turn.")
            return False
        return True

    def _on_request_moves(self, conn: Connection, msg):
        if not self._require_turn(conn):
            return
        idx = msg.get("card_index")
        player = self.state.players[conn.player_id]
        if idx is None or not (0 <= idx < len(player.hand)):
            return
        card = player.hand[idx]
        moves = rules.legal_moves_for_card(self.state, self.board, conn.player_id, card, idx)
        conn.send({"type": "move_options", "card_index": idx, "moves": moves})
        if not moves:
            self._send_system(conn.player_id, f"No legal moves for {card.label()}.")

    def _on_submit_move(self, conn: Connection, msg):
        if not self._require_turn(conn):
            return
        move = msg.get("move")
        player = self.state.players[conn.player_id]
        idx = move.get("card_index") if move else None
        if idx is None or not (0 <= idx < len(player.hand)):
            self._send_system(conn.player_id, "Invalid move.")
            return
        card = player.hand[idx]
        legal = rules.legal_moves_for_card(self.state, self.board, conn.player_id, card, idx)
        canonical_move = _find_legal_move(move, legal)
        if canonical_move is None:
            self._send_system(conn.player_id, "Invalid move.")
            return
        move = canonical_move

        status_msg = rules.describe_move(self.state, player.name, card, move)
        messages = rules.apply_move(self.state, self.board, move)
        self._broadcast({"type": "system_msg", "text": status_msg})
        # The "got JOKERED!" line above already covers the capture for a
        # Joker wild swap -- skip apply_move's own generic capture message
        # so it isn't reported twice.
        if move["label"] != "Joker: wild swap":
            for m in messages:
                self._broadcast({"type": "system_msg", "text": m})
        played = player.hand.pop(idx)
        self.state.discard.append(played)
        drawn = self.state.draw_card()
        if drawn is not None:
            player.hand.append(drawn)

        mate = self.state.teammate(conn.player_id)
        members = [conn.player_id] if mate is None else [conn.player_id, mate]
        if any(self.state.team_all_safe(m) for m in members):
            self.state.phase = GameState.PHASE_FINISHED
            self.state.winner_team = self.state.team_id(conn.player_id)
            self._broadcast({"type": "game_over", "winner_team": self.state.winner_team,
                              "winner_name": player.name})
            self._broadcast({"type": "system_msg", "text": f"{player.name}'s team wins!"})
        else:
            self.state.next_turn()
        self._broadcast_state()

    def _on_forced_discard(self, conn: Connection, msg):
        if not self._require_turn(conn):
            return
        player = self.state.players[conn.player_id]
        if rules.any_forced_legal_move(self.state, self.board, conn.player_id):
            self._send_system(conn.player_id, "You have a legal move and must play it.")
            return
        idx = msg.get("card_index")
        if idx is None or not (0 <= idx < len(player.hand)):
            return
        card = player.hand.pop(idx)
        self.state.discard.append(card)
        drawn = self.state.draw_card()
        if drawn is not None:
            player.hand.append(drawn)
        self._broadcast({"type": "system_msg", "text": f"{player.name} had no legal move and discarded."})
        self.state.next_turn()
        self._broadcast_state()


def _find_legal_move(move, legal_moves):
    """Return the server-computed legal move matching the client's
    submission (matched on card/peg/destination only -- the client's copy
    of a move is otherwise untrusted), or None if it doesn't match any."""
    for m in legal_moves:
        if m["card_index"] != move.get("card_index"):
            continue
        if len(m["steps"]) != len(move.get("steps", [])):
            continue
        ok = True
        for sa, sb in zip(m["steps"], move["steps"]):
            if tuple(sa["peg"]) != tuple(sb["peg"]) or list(sa["to"]) != list(sb["to"]):
                ok = False
                break
        if ok:
            return m
    return None
