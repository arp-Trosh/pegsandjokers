#!/usr/bin/env python3
"""Pegs and Jokers -- networked TUI game.

Run this file directly. You'll be asked whether to Host a new game or Join
one already running, then dropped into the curses interface.
"""
import curses
import sys
import time

from .game.state import COLORS
from .net.client import ClientConnection
from .net.server import GameServer
from .ui.tui import TuiApp

DEFAULT_PORT = 5555


def ask(prompt, default=None, choices=None):
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            raw = str(default)
        if choices and raw not in choices:
            print(f"  please choose one of: {', '.join(choices)}")
            continue
        if raw:
            return raw


def choose_color():
    print("Available colors: " + ", ".join(f"{i + 1}={c}" for i, c in enumerate(COLORS)))
    raw = ask("Choose your peg color (number or name)", default="1")
    if raw.isdigit() and 1 <= int(raw) <= len(COLORS):
        return COLORS[int(raw) - 1]
    if raw.lower() in COLORS:
        return raw.lower()
    return COLORS[0]


def do_join_handshake(conn, name, color, timeout=10.0):
    conn.send({"type": "join", "name": name, "color": color})
    deadline = time.time() + timeout
    while time.time() < deadline:
        for msg in conn.poll():
            if msg.get("type") == "welcome":
                return msg
            if msg.get("type") == "system_msg":
                print(msg["text"])
            if msg.get("type") == "_connection_lost":
                raise ConnectionError("Server closed the connection during join.")
        time.sleep(0.05)
    raise TimeoutError("Timed out waiting for the server to accept the join.")


def run_tui(conn, name, color, num_players, player_id, is_host):
    def _main(stdscr):
        TuiApp(stdscr, conn, name, color, num_players, player_id, is_host).run()
    curses.wrapper(_main)


def host_flow():
    print("=== Host a game ===")
    num_players = int(ask("Number of players", default="4", choices=["2", "4", "6", "8"]))
    port = int(ask("Port to host on", default=str(DEFAULT_PORT)))
    name = ask("Your name", default="Host")
    color = choose_color()

    server = GameServer(num_players, port)
    server.start()
    print(f"Hosting on 0.0.0.0:{port} for {num_players} players. "
          f"Share your address with the other players.")
    print("Connecting you as a player now...")

    conn = ClientConnection("127.0.0.1", port)
    welcome = do_join_handshake(conn, name, color)
    run_tui(conn, name, welcome["color"], welcome["num_players"], welcome["player_id"], welcome["is_host"])


def join_flow():
    print("=== Join a game ===")
    addr = ask("Server address (host:port)", default=f"127.0.0.1:{DEFAULT_PORT}")
    if ":" in addr:
        host, port_s = addr.rsplit(":", 1)
        port = int(port_s)
    else:
        host, port = addr, DEFAULT_PORT
    name = ask("Your name", default="Player")
    color = choose_color()

    print(f"Connecting to {host}:{port}...")
    conn = ClientConnection(host, port)
    welcome = do_join_handshake(conn, name, color)
    run_tui(conn, name, welcome["color"], welcome["num_players"], welcome["player_id"], welcome["is_host"])


def main():
    print("Pegs and Jokers")
    print("===============")
    choice = ask("(H)ost or (J)oin a game?", default="H", choices=["H", "J", "h", "j"])
    try:
        if choice.lower() == "h":
            host_flow()
        else:
            join_flow()
    except (ConnectionError, TimeoutError, OSError) as e:
        print(f"Could not connect: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
