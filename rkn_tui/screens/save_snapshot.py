"""Модалка ввода label для снапшота.

Открывается из ResultsScreen по кнопке «Сохранить снапшот». Вводим короткое
имя (без него снапшот тоже сохранится — будет slug 'snap'), Enter
подтверждает, Esc отменяет. Сохранение делает сам ResultsScreen — модалка
только возвращает строку через dismiss(value).
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class SaveSnapshotScreen(ModalScreen[str | None]):
    """Спрашивает label для снапшота. dismiss(str) — сохранить, None — отмена."""

    BINDINGS = [
        ("escape", "cancel", "Отмена"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="snapshot-dialog"):
            yield Static("Сохранить снапшот", id="snapshot-title")
            yield Static(
                "Короткое имя — потом увидишь его в истории.\nМожно оставить пустым.",
                id="snapshot-hint",
                classes="muted",
            )
            yield Input(placeholder="например, до апдейта ТСПУ", id="snapshot-label")
            with Horizontal(id="snapshot-actions"):
                yield Button("Отмена (Esc)", id="snapshot-cancel", variant="default")
                yield Button("Сохранить (Enter)", id="snapshot-ok", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#snapshot-label", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "snapshot-cancel":
            self.action_cancel()
        elif event.button.id == "snapshot-ok":
            value = self.query_one("#snapshot-label", Input).value.strip()
            self.dismiss(value)
