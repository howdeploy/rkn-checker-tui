"""Экран сравнения двух снапшотов.

Показывает результат `snapshots.diff_snapshots(old, new)` тремя таблицами:
  - Изменилось (старый вердикт → новый)
  - Только в старом
  - Только в новом

«Без изменений» не показываем — их обычно много и они не информативны.
Цветовая подсветка: OK → блок красным, блок → OK зеленым. Это самый
важный сигнал — увидеть, что регрессировало или починилось.
"""
from __future__ import annotations

from rkn_checker.models import CheckResult, Verdict
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static

from .. import engine, verdicts
from ..snapshots import Snapshot, diff_snapshots


def _direction_marker(old: CheckResult, new: CheckResult) -> str:
    """Метка направления изменения — для колонки 'Δ'."""
    old_blocked = engine.is_blocked(old)
    new_blocked = engine.is_blocked(new)
    if old_blocked and not new_blocked:
        return "🟢 починился"
    if not old_blocked and new_blocked:
        return "🔴 заблокирован"
    if old.verdict is Verdict.OK and new.verdict is Verdict.OK:
        return "↔"
    # Был блок, остался блок, но другой вердикт.
    return "↻ другой блок"


def _short(v: Verdict) -> str:
    return verdicts.info(v).short


class DiffScreen(Screen):
    """Сводка + три DataTable: changed / only_old / only_new."""

    BINDINGS = [
        Binding("escape", "back", "Назад"),
    ]

    def __init__(self, old: Snapshot, new: Snapshot) -> None:
        super().__init__()
        self.old = old
        self.new = new
        self.diff = diff_snapshots(old, new)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="diff-root"):
            yield Static(self._headline(), id="diff-headline")
            yield Static(self._summary(), id="diff-summary", classes="muted")
            with VerticalScroll(id="diff-scroll"):
                if self.diff.changed:
                    yield Static("Изменилось", classes="diff-section-title")
                    yield DataTable(id="diff-changed", zebra_stripes=True)
                if self.diff.only_old:
                    yield Static(
                        "Только в старом снапшоте (исчезли)",
                        classes="diff-section-title",
                    )
                    yield DataTable(id="diff-only-old", zebra_stripes=True)
                if self.diff.only_new:
                    yield Static(
                        "Только в новом снапшоте (добавились)",
                        classes="diff-section-title",
                    )
                    yield DataTable(id="diff-only-new", zebra_stripes=True)
                if not any((self.diff.changed, self.diff.only_old, self.diff.only_new)):
                    yield Static(
                        "Снапшоты идентичны по составу и вердиктам.",
                        id="diff-empty",
                    )
            yield Button("Назад (Esc)", id="diff-back", variant="primary")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        if self.diff.changed:
            t = self.query_one("#diff-changed", DataTable)
            t.add_columns("Сайт", "Было", "Стало", "Δ")
            for e in self.diff.changed:
                assert e.old is not None and e.new is not None
                t.add_row(
                    e.name,
                    _short(e.old.verdict),
                    _short(e.new.verdict),
                    _direction_marker(e.old, e.new),
                )
        if self.diff.only_old:
            t = self.query_one("#diff-only-old", DataTable)
            t.add_columns("Сайт", "URL", "Вердикт")
            for e in self.diff.only_old:
                assert e.old is not None
                t.add_row(e.name, e.url, _short(e.old.verdict))
        if self.diff.only_new:
            t = self.query_one("#diff-only-new", DataTable)
            t.add_columns("Сайт", "URL", "Вердикт")
            for e in self.diff.only_new:
                assert e.new is not None
                t.add_row(e.name, e.url, _short(e.new.verdict))

    def _headline(self) -> str:
        return (
            f"Сравнение: {self.old.meta.display_date} → "
            f"{self.new.meta.display_date}"
        )

    def _summary(self) -> str:
        regressions = sum(
            1 for e in self.diff.changed
            if e.old and e.new and not engine.is_blocked(e.old) and engine.is_blocked(e.new)
        )
        recoveries = sum(
            1 for e in self.diff.changed
            if e.old and e.new and engine.is_blocked(e.old) and not engine.is_blocked(e.new)
        )
        return (
            f"Изменений: {len(self.diff.changed)} "
            f"(регрессий: {regressions}, восстановлений: {recoveries}) · "
            f"только в старом: {len(self.diff.only_old)} · "
            f"только в новом: {len(self.diff.only_new)} · "
            f"совпадают: {len(self.diff.unchanged)}"
        )

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "diff-back":
            self.action_back()
