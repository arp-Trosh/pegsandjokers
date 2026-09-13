"""Game state: players, pegs, hands, deck, discard pile."""
import random

from .board import Board, HOME_COUNT
from .cards import build_shoe

COLORS = ["red", "blue", "green", "yellow", "magenta", "cyan", "white", "orange"]

HAND_SIZE = 5


class Peg:
    """A single peg. Location is one of:
    ('home', owner, slot)   -- slot 0..HOME_COUNT-1, not yet in play
    ('track', pos)          -- pos 0..track_len-1 on the shared main track
    ('safe', owner, slot)   -- slot 0..SAFE_COUNT-1, slot 4 is the final resting spot

    HOME and SAFE slot numbers are only meaningful per-owner (every player
    has their own slots 0-4), so the owner is baked into the location tuple
    itself -- that's also exactly the space-id shape the board layout and
    the click-handling UI use, so a peg's location can be compared directly
    against a clicked/highlighted board space.
    """

    def __init__(self, owner, index):
        self.owner = owner
        self.index = index  # which of the player's 5 pegs (also the home slot at start)
        self.location = ("home", owner, index)

    def to_dict(self):
        return {"owner": self.owner, "index": self.index, "location": list(self.location)}

    @staticmethod
    def from_dict(d):
        p = Peg(d["owner"], d["index"])
        p.location = tuple(d["location"])
        return p


class Player:
    def __init__(self, player_id, name, color, connection_id=None):
        self.player_id = player_id
        self.name = name
        self.color = color
        self.connection_id = connection_id
        self.hand = []
        self.connected = True

    def to_dict(self, reveal_hand=False):
        return {
            "player_id": self.player_id,
            "name": self.name,
            "color": self.color,
            "connected": self.connected,
            "hand_count": len(self.hand),
            "hand": [c.to_dict() for c in self.hand] if reveal_hand else None,
        }


class GameState:
    PHASE_LOBBY = "lobby"
    PHASE_PLAYING = "playing"
    PHASE_FINISHED = "finished"

    def __init__(self, num_players, rng=None):
        self.num_players = num_players
        self.board = Board(num_players)
        self.players = {}  # player_id -> Player
        self.pegs = {}  # (owner, index) -> Peg
        self.shoe = []
        self.discard = []
        self.rng = rng
        self.phase = GameState.PHASE_LOBBY
        self.turn_player = None
        self.winner_team = None
        self.log = []  # list of (kind, text) system/chat log entries kept server-side

        for p in range(num_players):
            for i in range(HOME_COUNT):
                self.pegs[(p, i)] = Peg(p, i)

    # -- setup -------------------------------------------------------------
    def add_player(self, player_id, name, color, connection_id=None):
        self.players[player_id] = Player(player_id, name, color, connection_id)

    def start_game(self):
        self.shoe = build_shoe(self.num_players, rng=self.rng)
        self.discard = []
        order = sorted(self.players.keys())
        for pid in order:
            player = self.players[pid]
            player.hand = [self.shoe.pop() for _ in range(HAND_SIZE)]
        self.phase = GameState.PHASE_PLAYING
        self.turn_player = order[0]
        self.winner_team = None

    def draw_card(self):
        if not self.shoe:
            # reshuffle discard back into the shoe, keep top of discard out
            if len(self.discard) <= 1:
                return None
            top = self.discard[-1]
            rest = self.discard[:-1]
            (self.rng or random).shuffle(rest)
            self.shoe = rest
            self.discard = [top]
        return self.shoe.pop()

    # -- helpers -------------------------------------------------------------
    def pegs_of(self, player):
        return [self.pegs[(player, i)] for i in range(HOME_COUNT)]

    def peg_at(self, kind, *args):
        """Find a peg occupying a location. kind='track' args=(pos,); or
        kind='safe'/'home' args=(owner,slot)."""
        if kind == "track":
            (pos,) = args
            return self.track_occupant(pos)
        else:
            owner, slot = args
            return self.safe_occupant(owner, slot) if kind == "safe" else \
                next((p for p in self.pegs_of(owner) if p.location == ("home", owner, slot)), None)

    def track_occupant(self, pos):
        for peg in self.pegs.values():
            if peg.location == ("track", pos):
                return peg
        return None

    def safe_occupant(self, owner, slot):
        for peg in self.pegs_of(owner):
            if peg.location == ("safe", owner, slot):
                return peg
        return None

    def home_free_slot(self, owner):
        used = {p.location[2] for p in self.pegs_of(owner) if p.location[0] == "home"}
        for i in range(HOME_COUNT):
            if i not in used:
                return i
        return None

    def send_home(self, peg):
        slot = self.home_free_slot(peg.owner)
        peg.location = ("home", peg.owner, slot)

    def team_all_safe(self, player):
        mate = self.board.teammate(player)
        members = [player] if mate is None else [player, mate]
        for m in members:
            for peg in self.pegs_of(m):
                if peg.location[0] != "safe":
                    return False
        return True

    def next_turn(self):
        order = sorted(self.players.keys())
        i = order.index(self.turn_player)
        self.turn_player = order[(i + 1) % len(order)]

    # -- serialization -------------------------------------------------------
    def to_dict(self, for_player=None):
        return {
            "num_players": self.num_players,
            "phase": self.phase,
            "turn_player": self.turn_player,
            "winner_team": self.winner_team,
            "shoe_count": len(self.shoe),
            "discard_top": self.discard[-1].to_dict() if self.discard else None,
            "players": {
                str(pid): p.to_dict(reveal_hand=(for_player == pid))
                for pid, p in self.players.items()
            },
            "pegs": [
                {"owner": peg.owner, "index": peg.index, "location": list(peg.location)}
                for peg in self.pegs.values()
            ],
        }
