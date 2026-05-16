"""Готовые наборы настроек probe-движка.

Вместо того чтобы заставлять пользователя выбирать workers и timeout — даем
три осмысленных пресета под три типичных сценария.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    name: str
    label: str
    description: str
    workers: int
    timeout: float
    identify: bool
    no_self_info: bool


QUICK = Preset(
    name="quick",
    label="Быстрая",
    description=(
        "Большой параллелизм, короткие таймауты. "
        "Хороша для частых ре-чеков «как сейчас сеть»."
    ),
    workers=20,
    timeout=3.0,
    identify=False,
    no_self_info=True,
)

DEFAULT = Preset(
    name="default",
    label="Стандартная",
    description=(
        "Сбалансированные настройки автора оригинала. "
        "Подходит для разовой диагностики и сохранения снапшота."
    ),
    workers=10,
    timeout=5.0,
    identify=False,
    no_self_info=False,
)

THOROUGH = Preset(
    name="thorough",
    label="Тщательная",
    description=(
        "Низкий параллелизм, длинные таймауты, self-identify UA. "
        "Для отчета и диагностики нестабильной сети."
    ),
    workers=5,
    timeout=10.0,
    identify=True,
    no_self_info=False,
)


ALL: list[Preset] = [QUICK, DEFAULT, THOROUGH]


def by_name(name: str) -> Preset:
    for p in ALL:
        if p.name == name:
            return p
    raise KeyError(f"Unknown preset: {name!r}")
