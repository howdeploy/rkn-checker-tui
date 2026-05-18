"""Read-only plain-text report viewer."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ReportScreen(ModalScreen):
    """Modal with the shareable upstream-style report."""

    BINDINGS = [
        ("escape", "close", "Закрыть"),
        ("enter", "close", "Закрыть"),
    ]

    def __init__(self, report: str) -> None:
        super().__init__()
        self.report = report

    def compose(self) -> ComposeResult:
        with Container(id="report-dialog"):
            yield Static("Отчёт", id="report-title")
            with VerticalScroll(id="report-body"):
                yield Static(self.report, id="report-text")
            yield Button("Закрыть (Esc / Enter)", id="report-close", variant="primary")

    def action_close(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "report-close":
            self.action_close()
