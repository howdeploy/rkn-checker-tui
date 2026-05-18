"""Тесты на парсер кастомных списков из SettingsScreen.

Парсер — чистая функция, легко тестируется отдельно.
"""
from __future__ import annotations

from rkn_tui.screens.settings import format_url_map, parse_url_map


def test_empty_text_returns_none():
    """Пустая строка значит «использовать встроенный список», не пустой dict."""
    mapping, errors = parse_url_map("")
    assert mapping is None
    assert errors == []


def test_whitespace_and_comments_only_returns_none():
    mapping, errors = parse_url_map("   \n# комментарий\n\n  # ещё\n")
    assert mapping is None
    assert errors == []


def test_parses_valid_lines():
    text = "google=https://google.com\nya=https://ya.ru"
    mapping, errors = parse_url_map(text)
    assert mapping == {"google": "https://google.com", "ya": "https://ya.ru"}
    assert errors == []


def test_skips_comment_lines():
    text = "# это для теста\ngoogle=https://google.com\n# тут тоже\n"
    mapping, errors = parse_url_map(text)
    assert mapping == {"google": "https://google.com"}
    assert errors == []


def test_reports_missing_separator():
    text = "google https://google.com"
    _, errors = parse_url_map(text)
    assert len(errors) == 1
    assert "=" in errors[0]


def test_reports_bad_url_scheme():
    text = "bad=ftp://example.com"
    _, errors = parse_url_map(text)
    assert len(errors) == 1


def test_reports_malformed_url():
    text = "bad=http://[::1"
    _, errors = parse_url_map(text)
    assert len(errors) == 1


def test_reports_duplicate_name():
    text = "a=https://a.com\na=https://b.com"
    _, errors = parse_url_map(text)
    assert any("повтор" in e for e in errors)


def test_reports_empty_name():
    text = "=https://example.com"
    _, errors = parse_url_map(text)
    assert len(errors) == 1


def test_format_url_map_roundtrip():
    mapping = {"a": "https://a.com", "b": "http://b.com"}
    text = format_url_map(mapping)
    parsed, errors = parse_url_map(text)
    assert parsed == mapping
    assert errors == []


def test_format_url_map_none_returns_empty():
    assert format_url_map(None) == ""
    assert format_url_map({}) == ""
