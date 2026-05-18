from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from rkn_tui import __version__, storage
from rkn_tui.screens.splash import SplashScreen


class RknTuiApp(App):
    """Корень TUI: стартует со splash → main_menu → scanning/results."""

    CSS_PATH = "styles.tcss"
    TITLE = "rkn-tui"
    SUB_TITLE = f"v{__version__}"

    BINDINGS = [
        ("q", "quit", "Выход"),
        Binding("ctrl+p", "command_palette", "Меню команд", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Конфиг живет на уровне App — экраны видят актуальную версию,
        # SettingsScreen мутирует тот же объект.
        self.config = storage.load()

    def on_mount(self) -> None:
        self.push_screen(SplashScreen())


def main() -> int:
    RknTuiApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
