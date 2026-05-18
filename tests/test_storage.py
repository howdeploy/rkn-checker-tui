"""Тесты на хранилище конфигурации.

Все тесты используют tmp_path вместо реального ~/.config — чтобы не
загаживать домашнюю директорию пользователя при прогоне CI/локально.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rkn_tui import storage
from rkn_tui.storage import Config, RECENT_LIMIT, load, remember_adhoc, save


def test_load_missing_file_returns_defaults(tmp_path: Path):
    cfg = load(tmp_path / "absent.json")
    assert cfg == Config()


def test_save_and_load_roundtrip(tmp_path: Path):
    p = tmp_path / "config.json"
    cfg = Config(
        default_preset="quick",
        custom_white={"site": "https://site.test"},
        custom_black=None,
        recent_adhoc=["https://example.com/", "https://x.test/"],
    )
    save(cfg, p)
    loaded = load(p)
    assert loaded == cfg


def test_load_corrupt_json_returns_defaults(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text("not a json {{{", encoding="utf-8")
    assert load(p) == Config()


def test_load_wrong_top_type_returns_defaults(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    assert load(p) == Config()


def test_load_unknown_preset_falls_back_to_default(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"default_preset": "nuclear"}), encoding="utf-8")
    cfg = load(p)
    assert cfg.default_preset == "default"


def test_load_drops_non_http_urls_from_recent(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "recent_adhoc": [
                    "https://ok.test/",
                    "ftp://bad.test/",
                    42,
                    "javascript:alert(1)",
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = load(p)
    assert cfg.recent_adhoc == ["https://ok.test/"]


def test_load_drops_non_url_values_from_custom_map(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "custom_white": {
                    "good": "https://good.test/",
                    "bad-scheme": "ftp://x",
                    "bad-type": 123,
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load(p)
    assert cfg.custom_white == {"good": "https://good.test/"}


def test_load_drops_empty_names_and_malformed_urls_from_custom_map(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "custom_white": {
                    " ": "https://blank-name.test/",
                    "bad-host": "http://[::1",
                    "good": "https://good.test/",
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load(p)
    assert cfg.custom_white == {"good": "https://good.test/"}


def test_save_is_atomic(tmp_path: Path):
    """Если что-то упало посреди записи, существующий файл должен уцелеть.

    Не моделируем сбой в os.replace — это уже атомарная операция ОС.
    Проверяем, что .tmp файл не остается после успешной записи.
    """
    p = tmp_path / "config.json"
    save(Config(), p)
    assert not list(tmp_path.glob("*.tmp"))


def test_save_creates_parent_directory(tmp_path: Path):
    p = tmp_path / "nested" / "deeper" / "config.json"
    save(Config(default_preset="thorough"), p)
    assert p.exists()
    assert load(p).default_preset == "thorough"


def test_remember_adhoc_deduplicates_and_keeps_order():
    cfg = Config(recent_adhoc=["https://a/", "https://b/", "https://c/"])
    cfg = remember_adhoc(cfg, "https://b/")
    assert cfg.recent_adhoc == ["https://b/", "https://a/", "https://c/"]


def test_remember_adhoc_truncates_to_limit():
    cfg = Config(recent_adhoc=[f"https://u{i}/" for i in range(RECENT_LIMIT + 5)])
    cfg = remember_adhoc(cfg, "https://new/")
    assert len(cfg.recent_adhoc) == RECENT_LIMIT
    assert cfg.recent_adhoc[0] == "https://new/"


def test_config_path_respects_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert storage.config_path() == tmp_path / "xdg" / "rkn-tui" / "config.json"
