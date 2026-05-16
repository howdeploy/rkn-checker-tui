"""Тесты словаря вердиктов.

Главная задача — гарантировать что для каждого Verdict из апстрима у нас
есть описание. Если автор добавит новый verdict, тест упадет и напомнит
обновить словарь.
"""
from rkn_checker.models import Confidence, Verdict

from rkn_tui.verdicts import (
    _CONFIDENCE,
    _CONFIDENCE_HINT,
    _VERDICTS,
    confidence_hint,
    confidence_label,
    info,
)


def test_every_verdict_has_an_entry():
    missing = set(Verdict) - set(_VERDICTS.keys())
    assert not missing, f"Без описания остались вердикты: {missing}"


def test_every_confidence_has_an_entry():
    missing = set(Confidence) - set(_CONFIDENCE.keys())
    assert not missing
    missing_hint = set(Confidence) - set(_CONFIDENCE_HINT.keys())
    assert not missing_hint


def test_info_returns_expected_shape():
    i = info(Verdict.TLS_BLOCK)
    assert i.short == "DPI по SNI"
    assert "TCP" in i.what
    assert i.color.startswith("$")


def test_ok_verdict_uses_green():
    assert info(Verdict.OK).color == "$green"


def test_blocked_verdicts_use_red():
    for v in (Verdict.DNS_BLOCK, Verdict.TCP_RESET, Verdict.TLS_BLOCK, Verdict.HTTP_STUB):
        assert info(v).color == "$red", f"{v} должен быть красным"


def test_confidence_labels_are_russian():
    assert confidence_label(Confidence.HIGH) == "Высокая"
    assert confidence_label(Confidence.MEDIUM) == "Средняя"
    assert confidence_label(Confidence.LOW) == "Низкая"


def test_confidence_hints_have_substance():
    for c in Confidence:
        h = confidence_hint(c)
        assert len(h) > 30  # не пустышка
