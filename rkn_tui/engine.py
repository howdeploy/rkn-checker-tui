"""Обертка над rkn_checker.core.

Все обращения к probe-движку идут через этот модуль — UI не знает про
rkn_checker напрямую. Это изолирует TUI от возможных breaking changes
в апстриме (если автор переименует функцию — чиним в одном месте).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator

from rkn_checker.core import iter_check_urls, get_self_info
from rkn_checker.models import BLOCKED_VERDICTS, CheckResult
from rkn_checker.targets import BLACK_URLS, WHITE_URLS

from .presets import DEFAULT, Preset


class ScanMode(str, Enum):
    BOTH = "both"
    WHITE = "white"
    BLACK = "black"
    AD_HOC = "ad_hoc"


@dataclass
class ScanRequest:
    mode: ScanMode
    preset: Preset = DEFAULT
    custom_urls: dict[str, str] = field(default_factory=dict)
    custom_white: dict[str, str] | None = None
    custom_black: dict[str, str] | None = None


def build_targets(req: ScanRequest) -> dict[str, str]:
    """Собрать словарь {name: url} под запрошенный режим сканирования.

    Для AD_HOC возвращает только переданные пользователем URL.
    Для остальных — встроенные списки rkn_checker.targets, опционально
    замененные пользовательскими.
    """
    if req.mode is ScanMode.AD_HOC:
        return dict(req.custom_urls)

    white = req.custom_white if req.custom_white is not None else dict(WHITE_URLS)
    black = req.custom_black if req.custom_black is not None else dict(BLACK_URLS)

    if req.mode is ScanMode.WHITE:
        return white
    if req.mode is ScanMode.BLACK:
        return black
    return {**white, **black}


def run_scan(req: ScanRequest) -> Iterator[CheckResult]:
    """Запустить пробу и выдавать CheckResult по мере готовности.

    Это синхронный генератор. Textual вызывает его из worker-треда через
    @work(thread=True), а через app.call_from_thread пушит результаты в UI.
    """
    targets = build_targets(req)
    if not targets:
        return
    yield from iter_check_urls(
        targets,
        max_workers=req.preset.workers,
        timeout=req.preset.timeout,
        identify=req.preset.identify,
    )


def fetch_self_info(timeout: float = 5.0) -> dict:
    """Тонкая обертка над get_self_info — отдельно чтобы можно было замокать."""
    return get_self_info(timeout=timeout)


def is_blocked(result: CheckResult) -> bool:
    """Считается ли вердикт «заблокировано».

    Семантика берется из апстрима. Важно: DOWN и UNKNOWN не считаются
    блокировкой, потому что это либо лежащий сайт, либо внутренняя ошибка.
    """
    return result.verdict in BLOCKED_VERDICTS


def summarize(results: list[CheckResult]) -> dict[str, int]:
    """Подсчитать количество результатов по каждому вердикту."""
    counts: dict[str, int] = {}
    for r in results:
        counts[r.verdict.value] = counts.get(r.verdict.value, 0) + 1
    return counts
