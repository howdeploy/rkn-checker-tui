"""Экран результатов сканирования.

После того как ScanningScreen дотек до конца, мы пушим сюда полный
список CheckResult. Здесь — сводка, фильтр (всё / OK / подозрительные)
и таблица. Enter по строке открывает модалку с человеческим разбором.

Принцип фильтра: переключатель кнопками, состояние хранится в self._filter,
перерисовка таблицы через очистку и повторное наполнение. Не сложно и
работает мгновенно — у нас десятки строк, не тысячи.

read_only=True используется когда экран открывается из истории снапшотов:
скрываем кнопку «Сохранить», заголовок берем из snapshot label.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from rkn_checker.models import CheckResult, Verdict
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static

from .. import diagnostics, engine, snapshots, verdicts
from ..engine import ScanRequest
from ..vpn_check import ContextResult


class ResultFilter(str, Enum):
    ALL = "all"
    OK = "ok"
    BLOCKED = "blocked"


_FILTER_LABEL: dict[ResultFilter, str] = {
    ResultFilter.ALL: "Все",
    ResultFilter.OK: "Только OK",
    ResultFilter.BLOCKED: "Подозрительные",
}


def filter_results(results: list[CheckResult], flt: ResultFilter) -> list[CheckResult]:
    """Чистая фильтрация — вынесена отдельной функцией под юнит-тесты."""
    if flt is ResultFilter.ALL:
        return list(results)
    if flt is ResultFilter.OK:
        return [r for r in results if r.verdict is Verdict.OK]
    return [r for r in results if engine.is_blocked(r)]


class ResultsScreen(Screen):
    """Сводка + фильтр + DataTable. Enter открывает деталь."""

    BINDINGS = [
        Binding("escape", "back", "Назад"),
        # priority=True: стрелочки циклят фильтр даже когда DataTable в фокусе.
        # Навигация по строкам — Up/Down, так что left/right не теряются.
        Binding("left", "cycle_filter(-1)", "← фильтр", priority=True),
        Binding("right", "cycle_filter(1)", "фильтр →", priority=True),
        Binding("a", "set_filter('all')", "Все", show=False),
        Binding("o", "set_filter('ok')", "OK", show=False),
        Binding("b", "set_filter('blocked')", "Блок", show=False),
        Binding("s", "save_snapshot", "Снапшот", show=False),
    ]

    _FILTER_ORDER = (ResultFilter.ALL, ResultFilter.OK, ResultFilter.BLOCKED)

    def __init__(
        self,
        results: list[CheckResult],
        *,
        request: Optional[ScanRequest] = None,
        context_result: Optional[ContextResult] = None,
        read_only: bool = False,
        title: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.results = results
        self.request = request
        self.context_result = context_result
        self.read_only = read_only
        self.title_override = title
        self._filter = ResultFilter.ALL
        self._row_to_result: dict[str, CheckResult] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="results-root"):
            if self.title_override:
                yield Static(self.title_override, id="results-title")
            yield Static(self._summary_text(), id="results-summary")
            with Horizontal(id="results-filters"):
                yield Button(
                    _FILTER_LABEL[ResultFilter.ALL],
                    id="flt-all",
                    variant="primary",
                )
                yield Button(_FILTER_LABEL[ResultFilter.OK], id="flt-ok")
                yield Button(_FILTER_LABEL[ResultFilter.BLOCKED], id="flt-blocked")
                yield Static("", id="results-filter-counter")
            yield DataTable(id="results-table", zebra_stripes=True, cursor_type="row")
            with Horizontal(id="results-actions"):
                yield Button("Назад (Esc)", id="results-back", variant="default")
                if not self.read_only:
                    yield Button(
                        "Сохранить снапшот (s)",
                        id="results-snapshot",
                        variant="default",
                    )
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_columns("Сайт", "URL", "Вердикт", "Уверенность", "TLS", "HTTP")
        self._render_rows()

    def _summary_text(self) -> str:
        summary = engine.summarize(self.results)
        ok = summary.get(Verdict.OK.value, 0)
        blocked = sum(1 for r in self.results if engine.is_blocked(r))
        parts = [f"Всего: {len(self.results)}", f"OK: {ok}", f"подозрительно: {blocked}"]
        breakdown = [
            f"{verdicts.info(Verdict[k]).short}={v}"
            for k, v in summary.items()
            if v > 0 and Verdict[k] in engine.BLOCKED_VERDICTS
        ]
        line = " · ".join(parts)
        if breakdown:
            line += "  ·  " + ", ".join(breakdown)
        return line

    def _render_rows(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear()
        self._row_to_result.clear()
        filtered = filter_results(self.results, self._filter)
        for r in filtered:
            info = verdicts.info(r.verdict)
            key = table.add_row(
                r.name,
                r.url,
                info.short,
                verdicts.confidence_label(r.confidence),
                self._tls_label(r),
                self._http_label(r),
            )
            self._row_to_result[str(key.value)] = r
        counter = self.query_one("#results-filter-counter", Static)
        counter.update(f"{len(filtered)} строк")
        self._sync_filter_buttons()

    def _sync_filter_buttons(self) -> None:
        mapping = {
            "flt-all": ResultFilter.ALL,
            "flt-ok": ResultFilter.OK,
            "flt-blocked": ResultFilter.BLOCKED,
        }
        for btn_id, flt in mapping.items():
            btn = self.query_one(f"#{btn_id}", Button)
            btn.variant = "primary" if flt is self._filter else "default"

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

    def action_set_filter(self, key: str) -> None:
        try:
            self._filter = ResultFilter(key)
        except ValueError:
            return
        self._render_rows()

    def action_cycle_filter(self, direction: int) -> None:
        idx = self._FILTER_ORDER.index(self._filter)
        idx = (idx + direction) % len(self._FILTER_ORDER)
        self._filter = self._FILTER_ORDER[idx]
        self._render_rows()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_save_snapshot(self) -> None:
        if self.read_only:
            return
        from .save_snapshot import SaveSnapshotScreen

        self.app.push_screen(SaveSnapshotScreen(), self._on_snapshot_label)

    def _on_snapshot_label(self, label: str | None) -> None:
        if label is None:
            return
        ctx = self.context_result or getattr(self.app, "context", None)
        self_info = ctx.self_info if ctx else {}
        context_status = ctx.status.value if ctx else ""
        context_headline = ctx.headline if ctx else ""
        context_detail = ctx.detail if ctx else ""
        mode = self.request.mode.value if self.request else "unknown"
        preset = self.request.preset.name if self.request else "unknown"
        try:
            path = snapshots.save_snapshot(
                self.results,
                label=label,
                mode=mode,
                preset=preset,
                self_info=self_info,
                context_status=context_status,
                context_headline=context_headline,
                context_detail=context_detail,
                diagnostics=diagnostics.collect_diagnostics(results=self.results),
            )
        except OSError as exc:
            self.notify(
                f"Не получилось сохранить: {exc}",
                title="Ошибка снапшота",
                severity="error",
            )
            return
        self.notify(
            f"Снапшот сохранен: {path.name}",
            title="Готово",
            severity="information",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "results-back":
            self.action_back()
        elif event.button.id == "flt-all":
            self.action_set_filter("all")
        elif event.button.id == "flt-ok":
            self.action_set_filter("ok")
        elif event.button.id == "flt-blocked":
            self.action_set_filter("blocked")
        elif event.button.id == "results-snapshot":
            self.action_save_snapshot()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = str(event.row_key.value)
        result = self._row_to_result.get(row_key)
        if result is None:
            return
        from .verdict_detail import VerdictDetailScreen

        self.app.push_screen(VerdictDetailScreen(result))
