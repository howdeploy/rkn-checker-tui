from unittest.mock import patch

import pytest

from rkn_checker.models import CheckResult, Verdict
from rkn_tui.engine import (
    ScanMode,
    ScanRequest,
    build_targets,
    is_blocked,
    run_scan,
    summarize,
)
from rkn_tui.presets import DEFAULT, QUICK


def test_build_targets_both_combines_white_and_black():
    req = ScanRequest(mode=ScanMode.BOTH, preset=DEFAULT)
    targets = build_targets(req)
    assert len(targets) >= 30  # 21 white + 15 black встроенных


def test_build_targets_white_only():
    """Whitelist у автора — российские сайты которые не должны блокироваться (контроль)."""
    req = ScanRequest(mode=ScanMode.WHITE, preset=DEFAULT)
    targets = build_targets(req)
    assert len(targets) >= 15
    # достаточно убедиться что это словарь имя→url с реальными хостами
    for name, url in targets.items():
        assert url.startswith("http")


def test_build_targets_black_only():
    req = ScanRequest(mode=ScanMode.BLACK, preset=DEFAULT)
    targets = build_targets(req)
    assert len(targets) >= 10


def test_build_targets_ad_hoc_uses_only_custom():
    req = ScanRequest(
        mode=ScanMode.AD_HOC,
        preset=DEFAULT,
        custom_urls={"example": "https://example.com"},
    )
    targets = build_targets(req)
    assert targets == {"example": "https://example.com"}


def test_build_targets_custom_white_overrides():
    req = ScanRequest(
        mode=ScanMode.WHITE,
        preset=DEFAULT,
        custom_white={"only": "https://only.test"},
    )
    targets = build_targets(req)
    assert targets == {"only": "https://only.test"}


def test_run_scan_empty_ad_hoc_yields_nothing():
    req = ScanRequest(mode=ScanMode.AD_HOC, preset=DEFAULT, custom_urls={})
    assert list(run_scan(req)) == []


def test_run_scan_mocked_passes_through():
    fake = CheckResult(name="x", url="https://x.test", verdict=Verdict.OK)
    with patch("rkn_tui.engine.iter_check_urls", return_value=iter([fake])):
        req = ScanRequest(
            mode=ScanMode.AD_HOC,
            preset=QUICK,
            custom_urls={"x": "https://x.test"},
        )
        results = list(run_scan(req))
    assert len(results) == 1
    assert results[0].name == "x"
    assert results[0].verdict is Verdict.OK


def test_run_scan_propagates_preset_settings():
    captured: dict = {}

    def fake_iter(targets, max_workers, timeout, identify):
        captured["max_workers"] = max_workers
        captured["timeout"] = timeout
        captured["identify"] = identify
        return iter([])

    with patch("rkn_tui.engine.iter_check_urls", side_effect=fake_iter):
        req = ScanRequest(
            mode=ScanMode.AD_HOC,
            preset=QUICK,
            custom_urls={"x": "https://x.test"},
        )
        list(run_scan(req))

    assert captured["max_workers"] == QUICK.workers
    assert captured["timeout"] == QUICK.timeout
    assert captured["identify"] == QUICK.identify


def test_is_blocked_for_ok():
    r = CheckResult(name="x", url="x", verdict=Verdict.OK)
    assert is_blocked(r) is False


def test_is_blocked_for_tls_block():
    r = CheckResult(name="x", url="x", verdict=Verdict.TLS_BLOCK)
    assert is_blocked(r) is True


def test_is_blocked_ignores_unknown():
    """UNKNOWN — служебный verdict, не считаем за блокировку."""
    r = CheckResult(name="x", url="x", verdict=Verdict.UNKNOWN)
    assert is_blocked(r) is False


def test_summarize_groups_by_verdict():
    results = [
        CheckResult(name="a", url="a", verdict=Verdict.OK),
        CheckResult(name="b", url="b", verdict=Verdict.OK),
        CheckResult(name="c", url="c", verdict=Verdict.TLS_BLOCK),
    ]
    counts = summarize(results)
    assert counts["OK"] == 2
    assert counts["TLS_BLOCK"] == 1
