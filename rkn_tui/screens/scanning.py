"""Live-таблица сканирования.

Запускает engine.run_scan(req) в worker-треде и через call_from_thread
по одной строке наполняет DataTable. Прогресс-бар сверху, кнопка Cancel.
По завершению — переход на заглушку результатов (реальный экран в #6).

Почему именно поток, а не asyncio: rkn_checker.core использует
ThreadPoolExecutor и блокирующий requests. Заворачивать его в async было
бы натяжкой; @work(thread=True) — стандартный textual-паттерн для таких
случаев.
"""
from __future__ import annotations

from typing import Iterable

from rkn_checker.models import CheckResult
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, ProgressBar, Static
from textual.worker import Worker, WorkerState

from .. import engine, verdicts
from ..engine import ScanRequest


class ScanningScreen(Screen):
    """Прогресс-бар + DataTable + кнопка отмены."""

    BINDINGS = [
        ("escape", "cancel", "Отмена"),
    ]

    def __init__(self, request: ScanRequest) -> None:
        super().__init__()
        self.request = request
        self.results: list[CheckResult] = []
        self._targets_count = 0
        self._cancelled = False
        self._finished = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="scan-root"):
            yield Static(self._headline(), id="scan-headline")
            yield ProgressBar(id="scan-progress", show_eta=False)
            yield Static("0 / 0", id="scan-counter")
            yield DataTable(id="scan-table", zebra_stripes=True, cursor_type="row")
            with Horizontal(id="scan-actions"):
                yield Button("Отмена (Esc)", id="scan-cancel", variant="warning")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        table = self.query_one("#scan-table", DataTable)
        table.add_columns("Сайт", "URL", "Вердикт", "Уверенность", "TLS", "HTTP")

        targets = engine.build_targets(self.request)
        self._targets_count = len(targets)
        progress = self.query_one("#scan-progress", ProgressBar)
        progress.total = self._targets_count or 1
        self._update_counter()

        if not targets:
            self.notify(
                "Нечего сканировать (пустой список целей).",
                title="Пустой запрос",
                severity="warning",
            )
            self._finish()
            return

        self._run_scan()

    def _headline(self) -> str:
        return (
            f"Сканирование · режим {self.request.mode.value} · "
            f"пресет «{self.request.preset.label}»"
        )

    @work(thread=True, exclusive=True)
    def _run_scan(self) -> None:
        iterator = engine.run_scan(self.request)
        self._consume(iterator)

    def _consume(self, iterator: Iterable[CheckResult]) -> None:
        for result in iterator:
            if self._cancelled:
                break
            self.app.call_from_thread(self._on_result, result)
        self.app.call_from_thread(self._finish)

    def _on_result(self, result: CheckResult) -> None:
        self.results.append(result)
        info = verdicts.info(result.verdict)
        confidence = verdicts.confidence_label(result.confidence)
        tls_label = self._tls_label(result)
        http_label = self._http_label(result)
        table = self.query_one("#scan-table", DataTable)
        table.add_row(
            result.name,
            result.url,
            info.short,
            confidence,
            tls_label,
            http_label,
        )
        progress = self.query_one("#scan-progress", ProgressBar)
        progress.advance(1)
        self._update_counter()

    def _update_counter(self) -> None:
        counter = self.query_one("#scan-counter", Static)
        counter.update(f"{len(self.results)} / {self._targets_count}")

    @staticmethod
    def _tls_label(r: CheckResult) -> str:
        if r.tls_ok:
            return "✓"
        if r.tls_error:
            return r.tls_error[:24]
        if r.tcp_ok is False:
            return "—"
        return "✗"

    @staticmethod
    def _http_label(r: CheckResult) -> str:
        if r.status_code is not None:
            return str(r.status_code)
        if r.http_error:
            return r.http_error[:24]
        return "—"

    def action_cancel(self) -> None:
        if self._finished:
            self.app.pop_screen()
            return
        self._cancelled = True
        self.notify("Останавливаем скан…", title="Отмена")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scan-cancel":
            self.action_cancel()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state in (WorkerState.ERROR, WorkerState.CANCELLED):
            self._finish()

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        progress = self.query_one("#scan-progress", ProgressBar)
        if self._targets_count:
            progress.update(progress=self._targets_count)

        if self._cancelled:
            button = self.query_one("#scan-cancel", Button)
            button.label = "Назад (Esc)"
            button.variant = "primary"
            self.query_one("#scan-headline", Static).update(
                f"Отменено · собрано {len(self.results)} проверок"
            )
            return

        if not self.results:
            self.query_one("#scan-headline", Static).update("Нет результатов")
            return

        from .results import ResultsScreen

        context = getattr(self.app, "context", None)
        self.app.switch_screen(
            ResultsScreen(
                self.results,
                request=self.request,
                context_result=context,
            )
        )
