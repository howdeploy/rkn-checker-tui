"""Быстрая проверка контекста запуска.

Идея: пользователь запустил TUI под активным ВПН, рассчитывает увидеть
картину блокировок — но movемся через туннель, картина будет «всё OK».
До того как человек запустит долгий скан и удивится, делаем два маленьких
теста: один контрольный сайт и один заведомо заблокированный.

Логика:
  * оба OK            → 🟢 ВПН активен ИЛИ сеть без фильтрации (мы за рубежом, например)
  * контроль OK, блок не-OK → 🟡 типичная ТСПУ-сеть, диагностика осмысленна
  * контроль не-OK    → 🔴 что-то с сетью в принципе, скан мало что покажет

Это эвристика, не приговор. Цель — поставить честный бейдж на главном
экране, чтобы человек не недоумевал.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rkn_checker.core import check_url
from rkn_checker.models import Verdict

from . import engine

PROBE_CONTROL = ("control", "https://www.gosuslugi.ru/")
PROBE_BLOCKED = ("blocked", "https://www.linkedin.com/")


class NetworkContext(str, Enum):
    LIKELY_VPN_OR_CLEAN = "vpn_or_clean"
    """Заблокированный сайт ответил OK. Это либо ВПН, либо сеть без ТСПУ."""

    LIKELY_FILTERED = "filtered"
    """Контроль работает, блокируемый сломан. Похоже на типичную сеть с фильтрацией."""

    NETWORK_BROKEN = "broken"
    """Даже контрольный сайт не отвечает. Скан мало что покажет."""

    UNKNOWN = "unknown"


@dataclass
class ContextResult:
    status: NetworkContext
    headline: str
    detail: str
    self_info: dict
    control_verdict: Optional[Verdict] = None
    blocked_verdict: Optional[Verdict] = None


def detect(timeout: float = 4.0, skip_self_info: bool = False) -> ContextResult:
    """Сделать две быстрые пробы и вернуть классификацию.

    Используется при старте главного экрана. Должна укладываться в ~5 секунд.
    """
    control = check_url(PROBE_CONTROL[0], PROBE_CONTROL[1], timeout=timeout)
    blocked = check_url(PROBE_BLOCKED[0], PROBE_BLOCKED[1], timeout=timeout)

    self_info = {} if skip_self_info else engine.fetch_self_info(timeout=timeout)

    control_blocked = engine.is_blocked(control)
    target_blocked = engine.is_blocked(blocked)

    if control_blocked:
        status = NetworkContext.NETWORK_BROKEN
        headline = "🔴 Сеть нестабильна"
        detail = (
            f"Даже контрольный {PROBE_CONTROL[1]} не отвечает корректно "
            f"(verdict: {control.verdict.value}). Возможно, нет интернета "
            "или провайдер фильтрует слишком агрессивно. Результаты скана "
            "будут малоинформативны."
        )
    elif not target_blocked:
        status = NetworkContext.LIKELY_VPN_OR_CLEAN
        headline = "🟢 Сеть выглядит чистой"
        detail = (
            f"Заблокированный {PROBE_BLOCKED[1]} ответил без проблем. "
            "Это значит ты либо под активным ВПН, либо вне зоны фильтрации. "
            "Скан под ВПН покажет 'всё OK' — это правильное поведение тулзы, "
            "но не отражает реальной картины блокировок."
        )
    else:
        status = NetworkContext.LIKELY_FILTERED
        headline = "🟡 Сеть с фильтрацией"
        detail = (
            f"Контроль работает, а {PROBE_BLOCKED[1]} оборвался "
            f"({blocked.verdict.value}). Похоже на типичную сеть под ТСПУ — "
            "полный скан имеет смысл."
        )

    return ContextResult(
        status=status,
        headline=headline,
        detail=detail,
        self_info=self_info,
        control_verdict=control.verdict,
        blocked_verdict=blocked.verdict,
    )
