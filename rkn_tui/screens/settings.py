"""Экран настроек.

Что можно настроить:
  1. Дефолтный пресет — quick / default / thorough. Применяется к пункту
     «Быстрая проверка» в главном меню и к ad-hoc сканам.
  2. Кастомные списки whitelist / blacklist — заменяют встроенные при
     «Только whitelist» / «Только blacklist» сканах. Формат — по одной
     строке `name=url`, пустые и `#`-комментарии игнорируются.

Сохранение — кнопкой «Сохранить» в storage.config_path(). «Сбросить»
возвращает дефолты (custom_* становятся None — встроенные списки).
«Закрыть» — без сохранения.

Принцип: если в редакторе кастомного списка ничего нет — это значит
«использовать встроенный». Пустой непустой список (имя без url или
кривой url) показывает ошибку, не сохраняет.
"""
from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    RadioButton,
    RadioSet,
    Static,
    TextArea,
)

from .. import presets, storage
from ..storage import Config
from ..url_utils import is_http_url


def parse_url_map(raw: str) -> tuple[Optional[dict[str, str]], list[str]]:
    """Распарсить многострочный текст в {name: url} или вернуть ошибки.

    Возвращает (mapping, errors). Если text пустой/только пробелы — mapping=None
    (значит «использовать встроенный список»). Если есть строки с ошибками,
    они в errors; mapping в этом случае всё равно собирается из валидных
    строк (для предпросмотра).
    """
    errors: list[str] = []
    out: dict[str, str] = {}
    lines = [ln.strip() for ln in raw.splitlines()]
    non_empty = [ln for ln in lines if ln and not ln.startswith("#")]
    if not non_empty:
        return None, errors
    for ln in non_empty:
        if "=" not in ln:
            errors.append(f"«{ln}» — нет «=» между именем и URL")
            continue
        name, url = ln.split("=", 1)
        name = name.strip()
        url = url.strip()
        if not name:
            errors.append(f"«{ln}» — пустое имя слева от «=»")
            continue
        if not is_http_url(url):
            errors.append(f"«{name}»: URL должен быть корректным http:// или https:// адресом")
            continue
        if name in out:
            errors.append(f"«{name}» — имя повторяется")
            continue
        out[name] = url
    return out, errors


def format_url_map(mapping: Optional[dict[str, str]]) -> str:
    """{name: url} → текст для TextArea. None становится пустой строкой."""
    if not mapping:
        return ""
    return "\n".join(f"{name}={url}" for name, url in mapping.items())


class SettingsScreen(Screen):
    """RadioSet для пресета + два TextArea для кастомных списков."""

    BINDINGS = [
        Binding("escape", "back", "Назад"),
        Binding("ctrl+s", "save", "Сохранить"),
    ]

    PRESETS_ORDER = ("quick", "default", "thorough")

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="settings-root"):
            yield Static("Настройки", id="settings-title")

            yield Label("Дефолтный пресет", classes="settings-section")
            with RadioSet(id="settings-preset"):
                for name in self.PRESETS_ORDER:
                    p = presets.by_name(name)
                    yield RadioButton(
                        f"{p.label} — {p.description}",
                        value=(name == self.config.default_preset),
                        id=f"preset-{name}",
                    )

            yield Label(
                "Кастомный whitelist (по одной строке name=url, пусто — встроенный)",
                classes="settings-section",
            )
            yield TextArea(
                format_url_map(self.config.custom_white),
                id="settings-white",
                show_line_numbers=True,
            )

            yield Label(
                "Кастомный blacklist (по одной строке name=url, пусто — встроенный)",
                classes="settings-section",
            )
            yield TextArea(
                format_url_map(self.config.custom_black),
                id="settings-black",
                show_line_numbers=True,
            )

            yield Static("", id="settings-error", classes="muted")

            with Horizontal(id="settings-actions"):
                yield Button("Сохранить (Ctrl+S)", id="settings-save", variant="primary")
                yield Button("Сбросить", id="settings-reset", variant="default")
                yield Button("Закрыть (Esc)", id="settings-back", variant="default")
        yield Footer(show_command_palette=False)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_save(self) -> None:
        self._save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-save":
            self._save()
        elif event.button.id == "settings-reset":
            self._reset()
        elif event.button.id == "settings-back":
            self.action_back()

    def _selected_preset(self) -> str:
        rs = self.query_one("#settings-preset", RadioSet)
        if rs.pressed_button is None:
            return self.config.default_preset
        # pressed_button.id == "preset-<name>"
        bid = rs.pressed_button.id or ""
        return bid.removeprefix("preset-") or self.config.default_preset

    def _save(self) -> None:
        white_text = self.query_one("#settings-white", TextArea).text
        black_text = self.query_one("#settings-black", TextArea).text
        white_map, white_errors = parse_url_map(white_text)
        black_map, black_errors = parse_url_map(black_text)
        err = self.query_one("#settings-error", Static)

        if white_errors or black_errors:
            errors = []
            if white_errors:
                errors.append("Whitelist:")
                errors.extend(f"  · {e}" for e in white_errors)
            if black_errors:
                errors.append("Blacklist:")
                errors.extend(f"  · {e}" for e in black_errors)
            err.update("\n".join(errors))
            return

        self.config.default_preset = self._selected_preset()
        self.config.custom_white = white_map
        self.config.custom_black = black_map

        try:
            storage.save(self.config)
        except OSError as e:
            err.update(f"Не удалось сохранить: {e}")
            return

        err.update("")
        self.notify("Настройки сохранены.", title="Готово")
        self.app.pop_screen()

    def _reset(self) -> None:
        self.config.default_preset = storage.DEFAULT_PRESET
        self.config.custom_white = None
        self.config.custom_black = None
        # Перерисовать виджеты — проще пересоздать экран.
        self.app.pop_screen()
        self.app.push_screen(SettingsScreen(self.config))
