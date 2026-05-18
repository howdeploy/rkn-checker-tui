"""Стартовый экран с фоновой диагностикой сети.

Зачем: vpn_check.detect() делает две сетевые пробы — это секунды. Если бы
мы дергали его синхронно при старте, пользователь увидел бы черный экран.
Splash показывает спиннер и сообщение, а в фоне крутится воркер. Когда
ContextResult готов — переключаемся на main_menu.
"""
from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Header, LoadingIndicator, Static

from .. import vpn_check
from ..vpn_check import ContextResult


class SplashScreen(Screen):
    """Показывает «диагностируем сеть…» пока работает vpn_check.detect()."""

    BINDINGS = [("q", "app.quit", "Выход")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="splash-panel"):
            yield Static("rkn-checker-tui", id="splash-title")
            yield Static(
                "Делаем две быстрые пробы, чтобы понять, есть ли смысл сканировать.",
                id="splash-sub",
            )
            yield LoadingIndicator(id="splash-spinner")
            yield Static("Диагностируем сеть…", id="splash-hint")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self._run_detect()

    @work(thread=True, exclusive=True)
    def _run_detect(self) -> None:
        result = vpn_check.detect()
        self.app.call_from_thread(self._on_detect_done, result)

    def _on_detect_done(self, result: ContextResult) -> None:
        from .main_menu import MainMenuScreen

        config = getattr(self.app, "config", None)
        # context живет на уровне App, чтобы экраны результатов могли
        # положить его в метаданные снапшота без длинной цепочки прокидываний.
        self.app.context = result  # type: ignore[attr-defined]
        self.app.switch_screen(MainMenuScreen(context=result, config=config))
