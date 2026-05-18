"""Экран истории снапшотов.

ListView по `snapshots.list_snapshots()`. Слева список — справа панель с
деталями выбранной записи (label, дата, режим, сводка). Действия:
  Enter / «Открыть» — push ResultsScreen в read-only режиме.
  «Сравнить с…»     — выбор второго снапшота и push DiffScreen.
  Delete            — confirm и `snapshots.delete_snapshot`.

Пустое состояние — статичное сообщение и пункт «Назад».
"""
from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static

from .. import snapshots
from ..snapshots import SnapshotMeta


_STATUS_LABEL: dict[str, str] = {
    "vpn_or_clean": "🟢 чистая",
    "filtered": "🟡 фильтрация",
    "broken": "🔴 сеть сломана",
    "indeterminate": "⚪ неясно",
    "unknown": "—",
    "": "—",
}


def _format_meta_line(meta: SnapshotMeta) -> str:
    label = meta.label or "(без имени)"
    status = _STATUS_LABEL.get(meta.context_status, meta.context_status or "—")
    return (
        f"{meta.display_date} · {label}\n"
        f"  {meta.mode} / {meta.preset} · "
        f"{meta.total} проверок, {meta.blocked} подозрительных · {status}"
    )


class HistoryScreen(Screen):
    """Список снапшотов + детали справа + действия снизу."""

    BINDINGS = [
        Binding("escape", "back", "Назад"),
        Binding("enter", "open_selected", "Открыть", show=False),
        Binding("delete", "delete_selected", "Удалить", show=True),
        Binding("c", "start_compare", "Сравнить", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.metas: list[SnapshotMeta] = []
        # Если задан — режим выбора второго снапшота для сравнения.
        self._compare_base: Optional[SnapshotMeta] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="history-root"):
            yield Static("История снапшотов", id="history-title")
            yield Static("", id="history-mode-hint", classes="muted")
            with Horizontal(id="history-row"):
                yield ListView(id="history-list")
                with VerticalScroll(id="history-detail"):
                    yield Static("", id="history-detail-text")
            with Horizontal(id="history-actions"):
                yield Button("Открыть (Enter)", id="history-open", variant="primary")
                yield Button("Сравнить (c)", id="history-compare", variant="default")
                yield Button("Удалить (Del)", id="history-delete", variant="warning")
                yield Button("Назад (Esc)", id="history-back", variant="default")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self.metas = snapshots.list_snapshots()
        lv = self.query_one("#history-list", ListView)
        lv.clear()
        if not self.metas:
            self.query_one("#history-detail-text", Static).update(
                "Снапшотов пока нет. После сканирования открой результаты "
                "и нажми «Сохранить снапшот»."
            )
            return
        for meta in self.metas:
            lv.append(ListItem(Label(_format_meta_line(meta))))
        lv.index = 0
        self._update_detail(0)

    def _update_detail(self, index: int) -> None:
        if not self.metas or index < 0 or index >= len(self.metas):
            return
        meta = self.metas[index]
        lines = [
            f"Дата: {meta.display_date}",
            f"Label: {meta.label or '—'}",
            f"Режим: {meta.mode}",
            f"Пресет: {meta.preset}",
            f"Всего проверок: {meta.total}",
            f"Подозрительных: {meta.blocked}",
            f"Статус сети: {_STATUS_LABEL.get(meta.context_status, meta.context_status or '—')}",
            f"Файл: {meta.path.name}",
        ]
        self.query_one("#history-detail-text", Static).update("\n".join(lines))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        index = event.list_view.index
        if index is not None:
            self._update_detail(index)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index or 0
        self._handle_pick(index)

    def _selected_meta(self) -> Optional[SnapshotMeta]:
        lv = self.query_one("#history-list", ListView)
        index = lv.index
        if index is None or index < 0 or index >= len(self.metas):
            return None
        return self.metas[index]

    def _handle_pick(self, index: int) -> None:
        meta = self.metas[index] if 0 <= index < len(self.metas) else None
        if meta is None:
            return
        if self._compare_base is not None:
            self._finish_compare(meta)
        else:
            self._open_meta(meta)

    def _open_meta(self, meta: SnapshotMeta) -> None:
        snap = snapshots.load_snapshot(meta.path)
        if snap is None:
            self.notify(
                "Не удалось открыть снапшот — файл поврежден.",
                title="Ошибка",
                severity="error",
            )
            return
        from .results import ResultsScreen

        title = f"Снапшот · {meta.display_date} · {meta.label or '(без имени)'}"
        self.app.push_screen(
            ResultsScreen(
                snap.results,
                read_only=True,
                title=title,
            )
        )

    def action_back(self) -> None:
        if self._compare_base is not None:
            # Внутри compare-режима Esc отменяет выбор второго.
            self._cancel_compare()
            return
        self.app.pop_screen()

    def action_open_selected(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            return
        self._handle_pick(self.metas.index(meta))

    def action_start_compare(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            return
        if self._compare_base is None:
            self._compare_base = meta
            hint = self.query_one("#history-mode-hint", Static)
            hint.update(
                f"Выбран базовый: «{meta.label or '(без имени)'}» от "
                f"{meta.display_date}. Выбери второй снапшот для сравнения "
                "и нажми Enter. Esc — отмена."
            )
        else:
            self._finish_compare(meta)

    def _finish_compare(self, other: SnapshotMeta) -> None:
        base = self._compare_base
        if base is None:
            return
        if base.path == other.path:
            self.notify(
                "Нельзя сравнивать снапшот с самим собой.",
                title="Сравнение",
                severity="warning",
            )
            return
        old_meta, new_meta = (base, other) if base.timestamp <= other.timestamp else (other, base)
        old = snapshots.load_snapshot(old_meta.path)
        new = snapshots.load_snapshot(new_meta.path)
        self._cancel_compare()
        if old is None or new is None:
            self.notify(
                "Один из снапшотов не читается.",
                title="Ошибка",
                severity="error",
            )
            return
        from .diff import DiffScreen

        self.app.push_screen(DiffScreen(old, new))

    def _cancel_compare(self) -> None:
        self._compare_base = None
        self.query_one("#history-mode-hint", Static).update("")

    def action_delete_selected(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            return

        def _on_confirm(ok: bool | None) -> None:
            if not ok:
                return
            if snapshots.delete_snapshot(meta.path):
                self.notify(
                    f"Снапшот удалён: {meta.label or meta.path.name}",
                    title="Готово",
                )
                self._reload()

        self.app.push_screen(
            _ConfirmModal(
                f"Удалить снапшот «{meta.label or meta.path.name}»? "
                "Это действие нельзя отменить."
            ),
            _on_confirm,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "history-back":
            self.action_back()
        elif event.button.id == "history-open":
            self.action_open_selected()
        elif event.button.id == "history-compare":
            self.action_start_compare()
        elif event.button.id == "history-delete":
            self.action_delete_selected()


class _ConfirmModal(ModalScreen[bool]):  # type: ignore[type-arg]
    """Простое да/нет подтверждение."""

    BINDINGS = [
        ("escape", "cancel", "Нет"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog"):
            yield Static(self.message, id="confirm-text")
            with Horizontal(id="confirm-actions"):
                yield Button("Нет (Esc)", id="confirm-no", variant="default")
                yield Button("Да", id="confirm-yes", variant="warning")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-no":
            self.dismiss(False)
        elif event.button.id == "confirm-yes":
            self.dismiss(True)
