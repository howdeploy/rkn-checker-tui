"""Хранилище пользовательской конфигурации.

Один JSON-файл `~/.config/rkn-tui/config.json`. Структура плоская:

  default_preset:  имя пресета — quick / default / thorough
  custom_white:    {name: url} или null (использовать встроенный whitelist)
  custom_black:    {name: url} или null (использовать встроенный blacklist)
  recent_adhoc:    последние URL для ad-hoc проверки, до RECENT_LIMIT штук

Принцип: corrupt-resilient. Если файл сломан, отсутствует, или в нем
левые типы — возвращаем дефолты и НЕ падаем. Сохранение — атомарное
(пишем в .tmp, потом os.replace), чтобы прерванная запись не оставила
куцый JSON.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .url_utils import is_http_url

DEFAULT_PRESET = "default"
RECENT_LIMIT = 10
VALID_PRESETS = {"quick", "default", "thorough"}


@dataclass
class Config:
    default_preset: str = DEFAULT_PRESET
    custom_white: Optional[dict[str, str]] = None
    custom_black: Optional[dict[str, str]] = None
    recent_adhoc: list[str] = field(default_factory=list)


def config_dir() -> Path:
    """Где хранить конфиг. XDG_CONFIG_HOME с фолбэком на ~/.config."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "rkn-tui"


def config_path() -> Path:
    return config_dir() / "config.json"


def load(path: Optional[Path] = None) -> Config:
    """Прочитать конфиг или вернуть дефолты при любой ошибке.

    Любое исключение — мусорный файл, кривые типы, права на чтение —
    приводит к возврату дефолтного Config. Это сознательно: UI должен
    стартовать всегда, даже с ломаной конфигурацией.
    """
    p = path or config_path()
    if not p.exists():
        return Config()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return Config()
        return _from_dict(raw)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return Config()


def save(config: Config, path: Optional[Path] = None) -> None:
    """Атомарная запись конфига.

    Создает директорию если её нет. Пишет в `.tmp` и делает `os.replace`,
    чтобы прерванная запись не разрушила существующий конфиг.
    """
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    data = json.dumps(asdict(config), indent=2, ensure_ascii=False)
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, p)


def remember_adhoc(config: Config, url: str) -> Config:
    """Добавить URL в начало recent_adhoc, обрезать до RECENT_LIMIT.

    Возвращает новый Config — конфиг dataclass, но recent_adhoc мутируем
    напрямую (это допустимо для нашего сценария).
    """
    recent = [url] + [u for u in config.recent_adhoc if u != url]
    config.recent_adhoc = recent[:RECENT_LIMIT]
    return config


def _from_dict(raw: dict) -> Config:
    """Строгая валидация словаря в Config. Кривые поля заменяются дефолтами."""
    cfg = Config()

    preset = raw.get("default_preset")
    if isinstance(preset, str) and preset in VALID_PRESETS:
        cfg.default_preset = preset

    cfg.custom_white = _coerce_url_map(raw.get("custom_white"))
    cfg.custom_black = _coerce_url_map(raw.get("custom_black"))

    recent = raw.get("recent_adhoc")
    if isinstance(recent, list):
        cfg.recent_adhoc = [
            u.strip() for u in recent if isinstance(u, str) and is_http_url(u)
        ][:RECENT_LIMIT]

    return cfg


def _coerce_url_map(value: object) -> Optional[dict[str, str]]:
    """Принимаем {str: str} с http/https URL, иначе None.

    None семантически значит «использовать встроенный список». Пустой словарь
    значит «у пользователя пусто, но он что-то редактировал» — оставляем как есть.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    cleaned: dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        name = k.strip()
        url = v.strip()
        if name and is_http_url(url):
            cleaned[name] = url
    return cleaned
