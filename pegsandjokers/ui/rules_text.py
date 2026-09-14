"""Static rules reference text shown by the /rules chat command.

Wording follows the official "How to Play Pegs & Jokers" rules sheet.
Each entry is a paragraph (wrapped to the terminal width at draw time);
an empty string is a blank line between sections.
"""

RULES_LINES = [
    "COMING OUT",
    "Play begins by using a King, Queen, Jack, or Ace to move a peg from "
    "any of the five HOME positions to the COME OUT SPOT.",
    "ACE or FACE or JOKER gets you OUT! All face cards, including the "
    "JOKER, that are used to come out must land in the COME OUT SPOT.",
    "",
    "CARD MOVES (once you have a peg out)",
    "Ace   - moves forward one hole (or GETS a peg OUT!)",
    "2     - moves forward two holes",
    "3     - moves forward three holes",
    "4     - moves forward four holes",
    "5     - moves forward five holes",
    "6     - moves forward six holes",
    "7     - moves forward seven holes, but can be split between two "
    "pegs (both must move forward)",
    "8     - moves BACKWARD eight holes",
    "9     - moves forward nine holes, but can be split between two "
    "pegs (one must move FORWARD and the other BACKWARD)",
    "10    - moves forward ten holes",
    "Jack  - moves forward eleven holes (or GETS a peg OUT!)",
    "Queen - moves forward twelve holes (or GETS a peg OUT!)",
    "King  - moves forward thirteen holes (or GETS a peg OUT!)",
    "Joker - a WILD CARD: replaces any other peg in play with your own "
    "peg (or GETS a peg OUT!)",
    "",
    "OTHER RULES",
    "- Anytime your peg lands on an opponent's peg, it returns to its "
    "HOME area.",
    "- Anytime your peg lands on your partner's peg, you send it to its "
    "IN SPOT (the hole leading into its SAFE area).",
    "- You cannot pass, or land on, your own peg on the main track or "
    "in the SAFE area.",
    "- Once a peg is in the SAFE area, it is safe and cannot be removed.",
    "- You cannot back into the SAFE area, even with an 8 card.",
    "- When entering the SAFE area, if your only move is for more holes "
    "than the SAFE area allows, you cannot enter the SAFE area and must "
    "go past it. An 8 or 9 can potentially move you back so you don't "
    "have to go all the way around again.",
    "- You must move if you have a play. The Joker is the one exception: "
    "you never have to play it, even if it's the only card in your hand "
    "with a legal move.",
    "- You must use the full count of the card played; i.e. a 4 card "
    "requires four moves, even into the SAFE position.",
    "- Each player must play his own pegs until all five pegs are in "
    "the SAFE position. Then he can help his teammate.",
    "- If a Joker is used to get out of HOME, the peg cannot go "
    "anywhere else other than the COME OUT SPOT.",
    "- At no point can teammates discuss what cards they have with "
    "each other. NO TABLE TALK!",
]
