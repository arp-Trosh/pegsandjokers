"""Cards and decks for Pegs and Jokers."""
import random

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["Spades", "Hearts", "Diamonds", "Clubs"]
SUIT_SYMBOL = {"Spades": "♠", "Hearts": "♥", "Diamonds": "♦", "Clubs": "♣"}

# Number of standard decks used per player count (jokers included except at 2 players).
DECKS_FOR_PLAYERS = {2: 2, 4: 2, 6: 3, 8: 4}

COME_OUT_RANKS = {"A", "J", "Q", "K", "JOKER"}
MOVE_VALUES = {
    "A": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "J": 11, "Q": 12, "K": 13,
}


class Card:
    __slots__ = ("rank", "suit")

    def __init__(self, rank, suit=None):
        self.rank = rank
        self.suit = suit

    @property
    def is_joker(self):
        return self.rank == "JOKER"

    @property
    def can_come_out(self):
        return self.rank in COME_OUT_RANKS

    @property
    def move_value(self):
        return MOVE_VALUES.get(self.rank)

    def label(self):
        if self.is_joker:
            return "JOKER"
        name = {"A": "Ace", "J": "Jack", "Q": "Queen", "K": "King"}.get(self.rank, self.rank)
        return f"{name} {self.suit}"

    def short(self):
        if self.is_joker:
            return "JK"
        return f"{self.rank}{SUIT_SYMBOL.get(self.suit, '')}"

    def to_dict(self):
        return {"rank": self.rank, "suit": self.suit}

    @staticmethod
    def from_dict(d):
        return Card(d["rank"], d.get("suit"))

    def __repr__(self):
        return f"Card({self.rank},{self.suit})"

    def __eq__(self, other):
        return isinstance(other, Card) and self.rank == other.rank and self.suit == other.suit


def build_shoe(num_players, rng=None):
    """Build and shuffle the draw pile appropriate for the player count."""
    rng = rng or random
    num_decks = DECKS_FOR_PLAYERS[num_players]
    include_jokers = num_players != 2
    cards = []
    for _ in range(num_decks):
        for suit in SUITS:
            for rank in RANKS:
                cards.append(Card(rank, suit))
        if include_jokers:
            cards.append(Card("JOKER"))
            cards.append(Card("JOKER"))
    rng.shuffle(cards)
    return cards
