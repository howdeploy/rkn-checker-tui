"""Тесты на чистые функции AdhocScreen."""
from __future__ import annotations

from rkn_tui.screens.adhoc import AdhocScreen, normalize_url, url_to_name


def test_normalize_passes_through_https():
    assert normalize_url("https://example.com") == "https://example.com"


def test_normalize_passes_through_http():
    assert normalize_url("http://example.com") == "http://example.com"


def test_normalize_adds_https_when_missing():
    assert normalize_url("example.com") == "https://example.com"


def test_normalize_strips_whitespace():
    assert normalize_url("  example.com  ") == "https://example.com"


def test_normalize_rejects_empty():
    assert normalize_url("") is None
    assert normalize_url("   ") is None


def test_normalize_rejects_no_netloc():
    """https:// без хоста — не URL."""
    assert normalize_url("https://") is None


def test_normalize_rejects_malformed_ipv6():
    assert normalize_url("http://[::1") is None


def test_normalize_rejects_whitespace_inside_url():
    assert normalize_url("https://exa mple.com") is None


def test_url_to_name_returns_host():
    assert url_to_name("https://example.com/path") == "example.com"
    assert url_to_name("https://ya.ru:443/") == "ya.ru:443"


def test_build_custom_urls_dedupes_names_with_suffix():
    urls = [
        "https://example.com/a",
        "https://example.com/b",  # тот же хост — должен получить суффикс
        "https://other.com/",
    ]
    result = AdhocScreen._build_custom_urls(urls)
    assert "example.com" in result
    assert "example.com-2" in result
    assert "other.com" in result
    # Все URL сохранены
    assert set(result.values()) == set(urls)
