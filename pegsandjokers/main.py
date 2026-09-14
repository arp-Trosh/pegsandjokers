#!/usr/bin/env python3
"""Pegs and Jokers -- networked TUI game, built on Textual.

Run this file (or `python -m pegsandjokers`) and use the on-screen form to
host a new game or join one already running.
"""
from .ui.app import PegsAndJokersApp


def main():
    PegsAndJokersApp().run()


if __name__ == "__main__":
    main()
