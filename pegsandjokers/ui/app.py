from textual.app import App

from .connect_screen import ConnectScreen


class PegsAndJokersApp(App):
    TITLE = "Pegs and Jokers"

    def on_mount(self) -> None:
        self.push_screen(ConnectScreen())
