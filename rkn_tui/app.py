from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Header, Static

from rkn_tui import __version__


class RknTuiApp(App):
    """Минимальный скелет TUI. На следующих этапах вырастет в полноценное меню."""

    CSS_PATH = "styles.tcss"
    TITLE = "rkn-tui"
    SUB_TITLE = f"v{__version__} — скаффолд"

    BINDINGS = [("q", "quit", "Выход")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="stub-panel"):
            yield Static("rkn-checker-tui", id="stub-title")
            yield Static(
                "Скаффолд работает. На следующих этапах появится меню,\n"
                "сканер, история и понятные описания блокировок.",
            )
            yield Static("[Q] выход", id="stub-hint")
        yield Footer()


def main() -> int:
    RknTuiApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
