"""Экран ad-hoc проверки одного или нескольких URL.

Сюда попадаем из главного меню, пункт «Ad-hoc URL». Что показано:
  * Input — куда вбить URL (валидация на http/https при добавлении)
  * Левая колонка — список добавленных URL для текущего запуска
  * Правая колонка — список из storage.recent_adhoc (последние что
    пробовал пользователь), Enter перекидывает в левую
  * Снизу — кнопка «Запустить проверку»

При запуске собирается ScanRequest(mode=AD_HOC, custom_urls=...) и
пушится ScanningScreen. URL также пишутся в storage.recent_adhoc.

Имя для CheckResult: берем хост из URL (мы не претендуем на красивые
имена, главное — отличать одну строку от другой).
"""
from __future__ import annotations

from typing import Iterable
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from .. import storage
from ..engine import ScanMode, ScanRequest
from ..presets import DEFAULT, by_name
from ..storage import Config
from ..url_utils import normalize_http_url, url_host_label


def normalize_url(raw: str) -> str | None:
    """Привести URL к нормальной форме или вернуть None если он не URL.

    Принимаем «example.com» — автодоплним до https://. Не принимаем
    нестандартные схемы (ftp, javascript). Валидируем что есть netloc.
    """
    return normalize_http_url(raw)


def url_to_name(url: str) -> str:
    """Имя строки для CheckResult — хост (или fallback на сам URL)."""
    return url_host_label(url)


class AdhocScreen(Screen):
    """Экран ввода ad-hoc URL и запуска проверки."""

    BINDINGS = [
        Binding("escape", "back", "Назад"),
        # F5 вместо Ctrl+Enter: ctrl+enter в большинстве терминалов не
        # доходит как отдельный код (нужен kitty keyboard protocol),
        # а F5 ловится везде и не конфликтует с Input в фокусе.
        Binding("f5", "start", "Запустить", priority=True),
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._pending: list[str] = []
        self._recent_by_id: dict[str, str] = {
            f"recent-{i}": u for i, u in enumerate(config.recent_adhoc)
        }

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="adhoc-root"):
            yield Static(
                "Введи URL (например, https://example.com). "
                "Можно добавить несколько — Enter, потом «Запустить».",
                id="adhoc-hint",
            )
            yield Input(
                placeholder="https://… (Enter — добавить)",
                id="adhoc-input",
            )
            yield Static("", id="adhoc-error", classes="muted")
            with Horizontal(id="adhoc-columns"):
                with Vertical(id="adhoc-pending-col"):
                    yield Label("В этом запуске", classes="adhoc-col-title")
                    yield ListView(id="adhoc-pending")
                with Vertical(id="adhoc-recent-col"):
                    yield Label("Недавние (Enter — добавить)", classes="adhoc-col-title")
                    yield ListView(
                        *(
                            ListItem(Label(u), id=f"recent-{i}")
                            for i, u in enumerate(self.config.recent_adhoc)
                        ),
                        id="adhoc-recent",
                    )
            with Horizontal(id="adhoc-actions"):
                yield Button("Запустить (F5)", id="adhoc-start", variant="primary")
                yield Button("Назад (Esc)", id="adhoc-back", variant="default")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self.query_one("#adhoc-input", Input).focus()

    def _add(self, raw: str) -> None:
        url = normalize_url(raw)
        err = self.query_one("#adhoc-error", Static)
        if url is None:
            err.update(f"«{raw}» не похоже на корректный URL.")
            return
        if url in self._pending:
            err.update(f"{url} уже в списке.")
            return
        self._pending.append(url)
        err.update("")
        pending_list = self.query_one("#adhoc-pending", ListView)
        pending_list.append(
            ListItem(Label(url), id=f"pending-{len(self._pending) - 1}")
        )
        self.query_one("#adhoc-input", Input).value = ""

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "adhoc-input":
            self._add(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "adhoc-recent" and event.item.id:
            url = self._recent_by_id.get(event.item.id)
            if url:
                self._add(url)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_start(self) -> None:
        self._start_scan()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "adhoc-start":
            self._start_scan()
        elif event.button.id == "adhoc-back":
            self.action_back()

    def _start_scan(self) -> None:
        if not self._pending:
            self.notify(
                "Сначала добавь хотя бы один URL.",
                title="Пустой список",
                severity="warning",
            )
            return

        for url in self._pending:
            storage.remember_adhoc(self.config, url)
        try:
            storage.save(self.config)
        except OSError as e:
            self.notify(
                f"Не удалось сохранить недавние URL: {e}",
                title="Хранилище",
                severity="warning",
            )

        custom = self._build_custom_urls(self._pending)
        preset = _safe_preset(self.config.default_preset)
        request = ScanRequest(
            mode=ScanMode.AD_HOC,
            preset=preset,
            custom_urls=custom,
        )

        from .scanning import ScanningScreen

        self.app.push_screen(ScanningScreen(request))

    @staticmethod
    def _build_custom_urls(urls: Iterable[str]) -> dict[str, str]:
        """Уникальные имена для CheckResult по хосту, с суффиксом при коллизии."""
        out: dict[str, str] = {}
        for u in urls:
            base = url_to_name(u)
            name = base
            counter = 2
            while name in out:
                name = f"{base}-{counter}"
                counter += 1
            out[name] = u
        return out


def _safe_preset(name: str):
    try:
        return by_name(name)
    except KeyError:
        return DEFAULT
