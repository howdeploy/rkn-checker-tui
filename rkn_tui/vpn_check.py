"""Быстрая проверка контекста запуска.

Идея: пользователь запустил TUI под активным ВПН, рассчитывает увидеть
картину блокировок — но movемся через туннель, картина будет «всё OK».
До того как человек запустит долгий скан и удивится, делаем несколько
маленьких тестов: один контрольный сайт и три заведомо «политических».

Что важно: один LinkedIn — плохой индикатор. На VPS он может быть
недоступен и без ТСПУ (гео-блок LinkedIn для российских IP, rate-limit,
проблемы CDN), и мы получим ложное «🟡 фильтрация» под ВПН. Поэтому:

  1. Берем 3 разных blocked-сайта.
  2. Отличаем «явная цензура» (DNS_BLOCK / TCP_RESET / TLS_BLOCK /
     HTTP_STUB — это сигнатуры middlebox) от «двусмысленно» (DOWN /
     TIMEOUT — может быть и блокировка, и просто проблема сервера).
  3. Учитываем страну из self_info. IP не российского провайдера +
     отсутствие явной цензуры = почти наверняка ВПН/VPS.

Это эвристика, не приговор. Цель — поставить честный бейдж на главном
экране, чтобы человек не недоумевал.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rkn_checker.core import check_url
from rkn_checker.models import CheckResult, Verdict

from . import engine

PROBE_CONTROL = ("control", "https://www.gosuslugi.ru/")
PROBE_BLOCKED: list[tuple[str, str]] = [
    ("linkedin", "https://www.linkedin.com/"),
    ("rutracker", "https://rutracker.org/"),
    ("grani", "https://graniru.org/"),
]

# Verdicts, которые означают «вижу middlebox / DPI».
CENSORSHIP_VERDICTS = frozenset(
    {Verdict.DNS_BLOCK, Verdict.TCP_RESET, Verdict.TLS_BLOCK, Verdict.HTTP_STUB}
)
# Verdicts, которые двусмысленны — сами по себе не доказывают ТСПУ.
AMBIGUOUS_VERDICTS = frozenset({Verdict.DOWN, Verdict.TIMEOUT})


class NetworkContext(str, Enum):
    LIKELY_VPN_OR_CLEAN = "vpn_or_clean"
    """Большинство «политических» сайтов открыты ИЛИ IP не российский.
    Либо ВПН, либо сеть без ТСПУ."""

    LIKELY_FILTERED = "filtered"
    """Хотя бы один сайт показал явную сигнатуру цензуры (DNS/TLS/TCP/HTTP-заглушка).
    Это классическая ТСПУ-сеть, скан имеет смысл."""

    NETWORK_BROKEN = "broken"
    """Даже контрольный сайт не отвечает. Скан мало что покажет."""

    INDETERMINATE = "indeterminate"
    """Контроль ок, но blocked-сайты дали только DOWN/TIMEOUT — нельзя
    различить блокировку и сетевые проблемы."""

    UNKNOWN = "unknown"


@dataclass
class ContextResult:
    status: NetworkContext
    headline: str
    detail: str
    self_info: dict
    control_verdict: Optional[Verdict] = None
    blocked_verdicts: dict[str, Verdict] = field(default_factory=dict)


def _country_code(self_info: dict) -> str:
    """Достать ISO-код страны из self_info, как бы он там ни назывался."""
    raw = (
        self_info.get("country")
        or self_info.get("country_code")
        or self_info.get("countryCode")
        or ""
    )
    return str(raw).strip().upper()


def _is_russian_ip(self_info: dict) -> bool:
    """Эвристика «мы выходим из российского IP» по self_info.

    Если country не определилась — считаем как «возможно RU» (нейтрально).
    Это нужно чтобы при недоступном ip-api пробы оставались главным сигналом.
    """
    code = _country_code(self_info)
    if not code:
        return True
    return code in {"RU", "RUSSIA"}


def detect(timeout: float = 4.0, skip_self_info: bool = False) -> ContextResult:
    """Сделать несколько быстрых проб и вернуть классификацию.

    Используется при старте главного экрана. Должна укладываться в ~5-7 секунд.
    """
    workers = 1 + len(PROBE_BLOCKED) + (0 if skip_self_info else 1)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        control_future = pool.submit(_safe_check_url, PROBE_CONTROL[0], PROBE_CONTROL[1], timeout)
        blocked_futures = [
            pool.submit(_safe_check_url, name, url, timeout)
            for name, url in PROBE_BLOCKED
        ]
        self_info_future = None
        if not skip_self_info:
            self_info_future = pool.submit(_safe_self_info, timeout)

        control = control_future.result()
        blocked_results = [future.result() for future in blocked_futures]
        self_info = {} if self_info_future is None else self_info_future.result()

    blocked_map = {r.name: r.verdict for r in blocked_results}

    if control.verdict is not Verdict.OK:
        return ContextResult(
            status=NetworkContext.NETWORK_BROKEN,
            headline="🔴 Сеть нестабильна",
            detail=(
                f"Даже контрольный {PROBE_CONTROL[1]} не отвечает корректно "
                f"(verdict: {control.verdict.value}). Возможно, нет интернета "
                "или провайдер фильтрует слишком агрессивно. Результаты скана "
                "будут малоинформативны."
            ),
            self_info=self_info,
            control_verdict=control.verdict,
            blocked_verdicts=blocked_map,
        )

    censored = [r for r in blocked_results if r.verdict in CENSORSHIP_VERDICTS]
    accessible = [r for r in blocked_results if r.verdict == Verdict.OK]
    ambiguous = [r for r in blocked_results if r.verdict in AMBIGUOUS_VERDICTS]

    non_russian = not _is_russian_ip(self_info)
    country = _country_code(self_info)
    isp = self_info.get("org") or self_info.get("isp") or ""

    # Сценарий 1: зарубежный выход. Даже если один сайт выглядит как TLS/DNS/TCP
    # блок, это не типичная российская ТСПУ-сеть: чаще это VPN/VPS routing,
    # серверный denylist или нестабильный маршрут до конкретного сайта.
    if non_russian:
        ip = self_info.get("ip", "—")
        provider = isp or "провайдер не определен"
        if censored:
            names = ", ".join(f"{r.name} ({r.verdict.value})" for r in censored)
            return ContextResult(
                status=NetworkContext.INDETERMINATE,
                headline="⚪ Зарубежный выход с аномалиями",
                detail=(
                    f"IP {ip} зарегистрирован в {country} ({provider}), поэтому это "
                    "не похоже на типичную российскую ТСПУ-сеть. Но часть тестовых "
                    f"сайтов дала censorship-like сигнал: {names}. Вероятнее всего "
                    "это особенность VPN/VPS-маршрута, блокировка со стороны сайта "
                    "или нестабильность канала. Полный скан можно читать как отчет "
                    "по текущему VPN-выходу, а не как картину блокировок у провайдера."
                ),
                self_info=self_info,
                control_verdict=control.verdict,
                blocked_verdicts=blocked_map,
            )
        if accessible:
            names = ", ".join(r.name for r in accessible)
            amb_part = ""
            if ambiguous:
                amb_part = (
                    f" Остальные ({', '.join(r.name for r in ambiguous)}) "
                    "не ответили, но без сигнатур цензуры — скорее всего "
                    "локальные проблемы серверов или гео-блок."
                )
            return ContextResult(
                status=NetworkContext.LIKELY_VPN_OR_CLEAN,
                headline="🟢 Сеть выглядит чистой",
                detail=(
                    f"IP {ip} зарегистрирован в {country} ({provider}), то есть "
                    "выход идет не из российской сети. Тестовые сайты "
                    f"({names}) открылись без сигнатур цензуры."
                    + amb_part
                    + " Скан под ВПН покажет состояние именно VPN-выхода, "
                    "а не реальную картину блокировок у домашнего провайдера."
                ),
                self_info=self_info,
                control_verdict=control.verdict,
                blocked_verdicts=blocked_map,
            )
        return ContextResult(
            status=NetworkContext.LIKELY_VPN_OR_CLEAN,
            headline="🟢 Сеть выглядит чистой",
            detail=(
                f"IP {ip} зарегистрирован в {country} ({provider}). Это не "
                "российская сеть, значит ты под ВПН или используешь зарубежный "
                "VPS. Тестовые сайты не ответили, но без явных сигнатур цензуры — "
                "скорее всего гео-блок или проблемы маршрута."
            ),
            self_info=self_info,
            control_verdict=control.verdict,
            blocked_verdicts=blocked_map,
        )

    # Сценарий 2: явная цензура хотя бы на одном сайте на RU/неизвестном IP → ТСПУ.
    if censored:
        names = ", ".join(f"{r.name} ({r.verdict.value})" for r in censored)
        return ContextResult(
            status=NetworkContext.LIKELY_FILTERED,
            headline="🟡 Сеть с фильтрацией",
            detail=(
                f"Сигнатура цензуры на {len(censored)} из {len(blocked_results)} "
                f"проб: {names}. Похоже на типичную сеть под ТСПУ — полный скан "
                "имеет смысл."
            ),
            self_info=self_info,
            control_verdict=control.verdict,
            blocked_verdicts=blocked_map,
        )

    # Сценарий 3: хоть один blocked сайт ответил OK, и нет явной цензуры → VPN/чистая.
    if accessible:
        names = ", ".join(r.name for r in accessible)
        amb_part = ""
        if ambiguous:
            amb_part = (
                f" Остальные ({', '.join(r.name for r in ambiguous)}) "
                "не ответили, но без сигнатур цензуры — скорее всего "
                "локальные проблемы серверов или гео-блок."
            )
        return ContextResult(
            status=NetworkContext.LIKELY_VPN_OR_CLEAN,
            headline="🟢 Сеть выглядит чистой",
            detail=(
                f"Тестовые сайты ({names}) открылись без сигнатур цензуры — "
                "значит ты либо под активным ВПН, либо вне зоны фильтрации."
                + amb_part
                + " Скан под ВПН покажет «всё OK» — это правильное поведение "
                "тулзы, но не отражает реальной картины блокировок."
            ),
            self_info=self_info,
            control_verdict=control.verdict,
            blocked_verdicts=blocked_map,
        )

    # Сценарий 4: RU IP, все blocked двусмысленные. Не можем уверенно сказать.
    return ContextResult(
        status=NetworkContext.INDETERMINATE,
        headline="⚪ Не удалось определить",
        detail=(
            "Контрольный сайт открылся, но все тестовые сайты не ответили "
            "без явных сигнатур цензуры (только DOWN/TIMEOUT). Это может "
            "быть и ТСПУ с агрессивным фильтром, и просто плохой канал. "
            "Полный скан подскажет точнее — обращай внимание на конкретные "
            "вердикты в таблице."
        ),
        self_info=self_info,
        control_verdict=control.verdict,
        blocked_verdicts=blocked_map,
    )


def _safe_check_url(name: str, url: str, timeout: float) -> CheckResult:
    """Run one probe without letting startup diagnostics crash the TUI."""
    try:
        return check_url(name, url, timeout=timeout)
    except Exception as exc:
        return CheckResult(
            name=name,
            url=url,
            verdict=Verdict.UNKNOWN,
            notes=[f"{type(exc).__name__}: {exc}"],
        )


def _safe_self_info(timeout: float) -> dict:
    try:
        return engine.fetch_self_info(timeout=timeout)
    except Exception:
        return {}
