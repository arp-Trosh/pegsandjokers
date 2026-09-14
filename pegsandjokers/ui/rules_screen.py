from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .rules_text import RULES_LINES


class RulesScreen(ModalScreen):
    CSS = """
    RulesScreen {
        align: center middle;
    }
    #rules_box {
        width: 80%;
        height: 80%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #rules_box > VerticalScroll {
        height: 1fr;
    }
    """
    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        with Vertical(id="rules_box"):
            with VerticalScroll():
                yield Static("\n".join(RULES_LINES))
            yield Button("Close", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_dismiss(self, result=None) -> None:
        self.dismiss(result)
