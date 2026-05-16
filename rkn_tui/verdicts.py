"""Человеческие описания вердиктов и confidence для UI.

Probe-движок выдает машинные коды (TLS_BLOCK, DNS_BLOCK, ...). Для человека
это шум. Здесь — таблица перевода в три уровня:
  short  — короткая русская плашка (для бейджа в таблице)
  what   — что физически произошло (одно предложение)
  why    — почему это значит «заблокировано» (откуда уверенность)
  color  — Catppuccin-цвет под Textual CSS

Каждое описание написано так, чтобы человек не-сетевик мог его прочесть
и понять, что с этим сайтом происходит.
"""
from __future__ import annotations

from dataclasses import dataclass

from rkn_checker.models import Confidence, Verdict


@dataclass(frozen=True)
class VerdictInfo:
    short: str
    what: str
    why: str
    color: str  # ключ цвета из styles.tcss


_VERDICTS: dict[Verdict, VerdictInfo] = {
    Verdict.OK: VerdictInfo(
        short="OK",
        what="Сайт открылся без помех.",
        why=(
            "DNS отдал тот же набор IP что и DoH, TCP-соединение прошло, "
            "TLS-рукопожатие удалось, HTTP вернул нормальный ответ. "
            "Сайт для тебя доступен."
        ),
        color="$green",
    ),
    Verdict.DNS_BLOCK: VerdictInfo(
        short="Подмена DNS",
        what="Системный резолвер вернул не те IP, что отдает DoH-резолвер.",
        why=(
            "Провайдер или ТСПУ подменяет ответы DNS на запросы об этом сайте: "
            "вместо реального IP отдается «заглушка» или пусто. Классический "
            "способ блокировки. Обход — DoH/DoT (например, Cloudflare 1.1.1.1) "
            "либо ВПН."
        ),
        color="$red",
    ),
    Verdict.TCP_RESET: VerdictInfo(
        short="Сброс TCP",
        what="TCP-соединение на порт 443 оборвалось RST-пакетом.",
        why=(
            "На пути к серверу middlebox (обычно ТСПУ) отправляет TCP RST, "
            "разрывая соединение еще до начала шифрования. Может быть и "
            "перегруженный сервер, но если других сайтов это не касается — "
            "почти наверняка фильтрация по IP."
        ),
        color="$red",
    ),
    Verdict.TLS_BLOCK: VerdictInfo(
        short="DPI по SNI",
        what="TCP прошел, но HTTPS-рукопожатие прервалось.",
        why=(
            "Когда твой клиент сообщает имя сайта в TLS-приветствии (SNI), "
            "DPI-оборудование это видит и обрывает соединение. Это самая "
            "характерная подпись ТСПУ. Обход — маскировка SNI (Encrypted "
            "Client Hello, fake SNI) либо ВПН с обфускацией."
        ),
        color="$red",
    ),
    Verdict.HTTP_STUB: VerdictInfo(
        short="Заглушка",
        what="Сервер вернул HTTP-страницу с маркерами блокировки.",
        why=(
            "Либо HTTP 451 (Unavailable For Legal Reasons), либо в теле "
            "ответа найдены известные русскоязычные маркеры заглушек "
            "провайдеров. Признак самого «явного» способа блокировки — "
            "когда провайдер не прячется."
        ),
        color="$red",
    ),
    Verdict.TIMEOUT: VerdictInfo(
        short="Таймаут",
        what="Соединение зависло до конца таймаута.",
        why=(
            "Пакеты молча отбрасываются. Может быть и блокировкой по IP, "
            "и просто плохим каналом. Уверенности низкая — повтори через "
            "пару минут, и если паттерн повторяется только на «опасных» "
            "сайтах — скорее всего фильтрация."
        ),
        color="$yellow",
    ),
    Verdict.DOWN: VerdictInfo(
        short="Не отвечает",
        what="Сайт не отзывается ни по одному из протоколов.",
        why=(
            "Домен не резолвится нигде, либо TCP-ошибка не похожа на блок "
            "(connection refused вместо reset). Чаще всего сервер просто "
            "лежит. Если на других сайтах всё OK — это не про РКН."
        ),
        color="$overlay",
    ),
    Verdict.UNKNOWN: VerdictInfo(
        short="?",
        what="Произошла внутренняя ошибка при пробе.",
        why="Это баг тулзы или странная ошибка в стандартной библиотеке.",
        color="$overlay",
    ),
}


_CONFIDENCE: dict[Confidence, str] = {
    Confidence.HIGH: "Высокая",
    Confidence.MEDIUM: "Средняя",
    Confidence.LOW: "Низкая",
}

_CONFIDENCE_HINT: dict[Confidence, str] = {
    Confidence.HIGH: (
        "Два независимых сигнала подтверждают диагноз. "
        "Это с большой вероятностью именно блокировка."
    ),
    Confidence.MEDIUM: (
        "Паттерн совпадает с известным способом блокировки, но единственный "
        "сигнал нельзя считать доказательством — повтори через какое-то время."
    ),
    Confidence.LOW: (
        "Симптом неоднозначный (таймаут или общая ошибка) — может быть и "
        "блокировкой, и плохим каналом, и проблемой сервера."
    ),
}


def info(verdict: Verdict) -> VerdictInfo:
    """Получить human-readable описание для вердикта."""
    return _VERDICTS[verdict]


def confidence_label(confidence: Confidence) -> str:
    return _CONFIDENCE[confidence]


def confidence_hint(confidence: Confidence) -> str:
    return _CONFIDENCE_HINT[confidence]
