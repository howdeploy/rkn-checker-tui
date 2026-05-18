"""Главное меню.

Сверху — статус-бейдж от vpn_check (🟢/🟡/🔴 + IP/ISP),
ниже — ListView из 8 пунктов. Каждый пункт умеет породить ScanRequest
или открыть отдельный экран (история, настройки, помощь).

Принцип навигации: меню всегда в стеке как корневой экран. Сканирование,
результаты, история — push поверх. Закрытие верхнего экрана возвращает
сюда. Это позволяет дергать «ещё проверка» без перезапуска приложения.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from ..engine import ScanMode, ScanRequest
from ..presets import DEFAULT, Preset, by_name
from ..storage import Config
from ..vpn_check import ContextResult, NetworkContext


@dataclass(frozen=True)
class _MenuEntry:
    key: str
    label: str
    hint: str
    action: Callable[["MainMenuScreen"], None]


class MainMenuScreen(Screen):
    """Корневой экран. Открывает сканер, историю и настройки."""

    BINDINGS = [
        ("q", "app.quit", "Выход"),
        ("r", "rescan_context", "Пере-диагностика"),
        Binding("up", "menu_move(-1)", "Вверх", priority=True, show=False),
        Binding("down", "menu_move(1)", "Вниз", priority=True, show=False),
        Binding("enter", "menu_activate", "Открыть", priority=True, show=False),
    ]

    def __init__(self, context: ContextResult, config: Config | None = None) -> None:
        super().__init__()
        self.context = context
        # Если config не передан — пробуем достать из App (для тестов
        # допускаем None и создаем пустой Config).
        self.config = config or Config()
        self._entries: list[_MenuEntry] = [
            _MenuEntry(
                "quick",
                "Проверка подключения",
                "Whitelist + blacklist под пресетом из настроек",
                lambda s: s._start_scan(s._build_request(ScanMode.BOTH)),
            ),
            _MenuEntry(
                "black",
                "Только blacklist",
                "Сайты, которые обычно блокируются под ТСПУ",
                lambda s: s._start_scan(s._build_request(ScanMode.BLACK)),
            ),
            _MenuEntry(
                "white",
                "Только whitelist",
                "Контрольная группа — должны открываться",
                lambda s: s._start_scan(s._build_request(ScanMode.WHITE)),
            ),
            _MenuEntry(
                "adhoc",
                "Ad-hoc URL",
                "Проверить конкретный сайт или несколько сразу",
                lambda s: s._open_adhoc(),
            ),
            _MenuEntry(
                "history",
                "История",
                "Снапшоты прошлых сканов, открыть и сравнить",
                lambda s: s._open_history(),
            ),
            _MenuEntry(
                "settings",
                "Настройки",
                "Дефолтный пресет, кастомные whitelist/blacklist",
                lambda s: s._open_settings(),
            ),
            _MenuEntry(
                "help",
                "Помощь",
                "Что значат вердикты, как читать таблицу",
                lambda s: s._not_yet("Помощь"),
            ),
            _MenuEntry(
                "quit",
                "Выход",
                "Закрыть rkn-tui",
                lambda s: s.app.exit(),
            ),
        ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="menu-root"):
            with Container(id="status-card", classes=self._status_class()):
                yield Static(self.context.headline, id="status-headline")
                yield Static(self._self_info_line(), id="status-self")
                yield Static(self.context.detail, id="status-detail")
            with Horizontal(id="menu-row"):
                yield ListView(
                    *(
                        ListItem(Label(e.label), id=f"item-{e.key}")
                        for e in self._entries
                    ),
                    id="menu-list",
                )
                yield Static(
                    self._entries[0].hint,
                    id="menu-hint",
                )
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        menu = self.query_one("#menu-list", ListView)
        if menu.index is None:
            menu.index = 0
        menu.focus()

    def _self_info_line(self) -> str:
        info = self.context.self_info or {}
        ip = info.get("ip", "—")
        isp = info.get("org") or info.get("isp") or "—"
        country = info.get("country") or info.get("country_name") or ""
        country_part = f", {country}" if country else ""
        return f"IP {ip} · ISP {isp}{country_part}"

    def _status_class(self) -> str:
        return {
            NetworkContext.LIKELY_VPN_OR_CLEAN: "status-green",
            NetworkContext.LIKELY_FILTERED: "status-yellow",
            NetworkContext.NETWORK_BROKEN: "status-red",
            NetworkContext.INDETERMINATE: "status-neutral",
        }.get(self.context.status, "status-neutral")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        index = event.list_view.index or 0
        self._update_hint(index)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index or 0
        self._activate_index(index)

    @staticmethod
    def _menu_index_after_move(index: int, direction: int, size: int) -> int:
        if size <= 0:
            return 0
        return max(0, min(size - 1, index + direction))

    def _update_hint(self, index: int) -> None:
        if not self._entries:
            return
        entry = self._entries[self._menu_index_after_move(index, 0, len(self._entries))]
        self.query_one("#menu-hint", Static).update(entry.hint)

    def _activate_index(self, index: int) -> None:
        if not self._entries:
            return
        entry = self._entries[self._menu_index_after_move(index, 0, len(self._entries))]
        entry.action(self)

    def action_menu_move(self, direction: int) -> None:
        menu = self.query_one("#menu-list", ListView)
        current = menu.index or 0
        index = self._menu_index_after_move(current, direction, len(self._entries))
        menu.index = index
        menu.focus()
        self._update_hint(index)

    def action_menu_activate(self) -> None:
        menu = self.query_one("#menu-list", ListView)
        menu.focus()
        self._activate_index(menu.index or 0)

    def _build_request(self, mode: ScanMode, preset: Preset | None = None) -> ScanRequest:
        """Собрать ScanRequest из текущего конфига.

        Пресет берется из default_preset — это единая точка управления
        скоростью скана. Пункт меню задает только режим (что сканируем),
        настройки задают как.
        """
        if preset is None:
            try:
                preset = by_name(self.config.default_preset)
            except KeyError:
                preset = DEFAULT
        return ScanRequest(
            mode=mode,
            preset=preset,
            custom_white=self.config.custom_white,
            custom_black=self.config.custom_black,
        )

    def _start_scan(self, request: ScanRequest) -> None:
        from .scanning import ScanningScreen

        self.app.push_screen(ScanningScreen(request))

    def _open_adhoc(self) -> None:
        from .adhoc import AdhocScreen

        self.app.push_screen(AdhocScreen(self.config))

    def _open_settings(self) -> None:
        from .settings import SettingsScreen

        self.app.push_screen(SettingsScreen(self.config))

    def _open_history(self) -> None:
        from .history import HistoryScreen

        self.app.push_screen(HistoryScreen())

    def _not_yet(self, name: str) -> None:
        self.notify(
            f"{name} появится на следующих этапах.",
            title="Ещё не готово",
            severity="warning",
        )

    def action_rescan_context(self) -> None:
        from .splash import SplashScreen

        self.app.switch_screen(SplashScreen())
