import argparse

from . import app, models


def main():
    parser = argparse.ArgumentParser(
        prog="board_designer",
        description="WYSIWYG TUI for designing Pegs & Jokers board layouts.",
    )
    parser.add_argument(
        "--players", type=int, choices=sorted(models.BOARD_SLOTS), default=6,
        help="Which board to start from (default: 6). Ignored if --load is given.",
    )
    parser.add_argument(
        "--load", type=str, default=None,
        help="Open a previously saved layout JSON file instead of seeding a fresh one.",
    )
    args = parser.parse_args()
    app.run(num_players=args.players, load_path=args.load)


if __name__ == "__main__":
    main()
