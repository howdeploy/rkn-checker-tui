"""Юнит-тесты на чистую логику экранов (без запуска самого Textual).

Не пытаемся гонять run_test() — это медленнее и требует event-loop.
Проверяем приватные методы, которые легко изолировать: маппинг статуса
сети в CSS-класс, форматирование строки self_info, человеческие
лейблы для TLS/HTTP-колонок таблицы сканирования.
"""
from __future__ import annotations

from rkn_checker.models import CheckResult, Verdict

from rkn_tui.screens.main_menu import MainMenuScreen
from rkn_tui.screens.scanning import ScanningScreen
from rkn_tui.engine import ScanMode, ScanRequest
from rkn_tui.vpn_check import ContextResult, NetworkContext


def _ctx(status: NetworkContext, info: dict | None = None) -> ContextResult:
    return ContextResult(
        status=status,
        headline="x",
        detail="y",
        self_info=info or {},
    )


def test_status_class_maps_to_traffic_light():
    assert MainMenuScreen(_ctx(NetworkContext.LIKELY_VPN_OR_CLEAN))._status_class() == "status-green"
    assert MainMenuScreen(_ctx(NetworkContext.LIKELY_FILTERED))._status_class() == "status-yellow"
    assert MainMenuScreen(_ctx(NetworkContext.NETWORK_BROKEN))._status_class() == "status-red"


def test_self_info_line_with_full_info():
    screen = MainMenuScreen(
        _ctx(NetworkContext.LIKELY_FILTERED, {"ip": "1.2.3.4", "org": "Beeline", "country": "RU"})
    )
    line = screen._self_info_line()
    assert "1.2.3.4" in line
    assert "Beeline" in line
    assert "RU" in line


def test_self_info_line_with_missing_info():
    screen = MainMenuScreen(_ctx(NetworkContext.LIKELY_FILTERED))
    line = screen._self_info_line()
    assert "—" in line


def test_self_info_line_prefers_org_over_isp():
    screen = MainMenuScreen(
        _ctx(NetworkContext.LIKELY_FILTERED, {"ip": "1.1.1.1", "org": "X-Org", "isp": "Y-ISP"})
    )
    line = screen._self_info_line()
    assert "X-Org" in line
    assert "Y-ISP" not in line


def test_menu_has_eight_entries_with_required_keys():
    screen = MainMenuScreen(_ctx(NetworkContext.LIKELY_FILTERED))
    keys = [e.key for e in screen._entries]
    assert keys == ["quick", "black", "white", "adhoc", "history", "settings", "help", "quit"]


def test_menu_index_after_move_clamps_to_edges():
    assert MainMenuScreen._menu_index_after_move(0, -1, 8) == 0
    assert MainMenuScreen._menu_index_after_move(0, 1, 8) == 1
    assert MainMenuScreen._menu_index_after_move(7, 1, 8) == 7


def _result(**kwargs) -> CheckResult:
    base = {"name": "x", "url": "https://x", "verdict": Verdict.OK}
    base.update(kwargs)
    return CheckResult(**base)


def test_tls_label_ok():
    assert ScanningScreen._tls_label(_result(tls_ok=True)) == "✓"


def test_tls_label_error_truncated():
    long_err = "SSLError: HANDSHAKE_FAILURE_ALERT_FROM_MIDDLEBOX_VERY_LONG"
    label = ScanningScreen._tls_label(_result(tls_error=long_err))
    assert len(label) <= 24
    assert label in long_err


def test_tls_label_fallback_dash_when_tcp_failed():
    assert ScanningScreen._tls_label(_result(tcp_ok=False)) == "—"


def test_http_label_status_code():
    assert ScanningScreen._http_label(_result(status_code=200)) == "200"


def test_http_label_status_451():
    assert ScanningScreen._http_label(_result(status_code=451)) == "451"


def test_http_label_error_truncated():
    long_err = "ConnectionResetError: very long descriptive thing"
    label = ScanningScreen._http_label(_result(http_error=long_err))
    assert len(label) <= 24


def test_scanning_screen_headline_mentions_mode_and_preset():
    from rkn_tui.presets import QUICK

    screen = ScanningScreen(ScanRequest(mode=ScanMode.BOTH, preset=QUICK))
    headline = screen._headline()
    assert "both" in headline
    assert QUICK.label in headline


# --- Results filtering ---


def _mixed_results() -> list[CheckResult]:
    return [
        _result(name="ok1", verdict=Verdict.OK),
        _result(name="ok2", verdict=Verdict.OK),
        _result(name="dns", verdict=Verdict.DNS_BLOCK),
        _result(name="tls", verdict=Verdict.TLS_BLOCK),
        _result(name="down", verdict=Verdict.DOWN),
        _result(name="unknown", verdict=Verdict.UNKNOWN),
    ]


def test_filter_all_returns_everything():
    from rkn_tui.screens.results import ResultFilter, filter_results

    results = _mixed_results()
    assert len(filter_results(results, ResultFilter.ALL)) == len(results)


def test_filter_ok_returns_only_ok():
    from rkn_tui.screens.results import ResultFilter, filter_results

    filtered = filter_results(_mixed_results(), ResultFilter.OK)
    assert {r.name for r in filtered} == {"ok1", "ok2"}


def test_filter_blocked_skips_ok_unknown_and_down():
    """UNKNOWN и DOWN не считаются блокировкой (см. engine.is_blocked)."""
    from rkn_tui.screens.results import ResultFilter, filter_results

    filtered = filter_results(_mixed_results(), ResultFilter.BLOCKED)
    names = {r.name for r in filtered}
    assert "ok1" not in names
    assert "ok2" not in names
    assert "unknown" not in names
    assert "down" not in names
    assert "dns" in names
    assert "tls" in names


def test_filter_does_not_mutate_input():
    from rkn_tui.screens.results import ResultFilter, filter_results

    original = _mixed_results()
    original_names = [r.name for r in original]
    filter_results(original, ResultFilter.OK)
    assert [r.name for r in original] == original_names


def test_cycle_filter_forward_and_backward():
    """Стрелочки циклят между ALL → OK → BLOCKED → ALL."""
    from rkn_tui.screens.results import ResultFilter, ResultsScreen

    screen = ResultsScreen(_mixed_results())
    # начальное — ALL
    assert screen._filter is ResultFilter.ALL
    screen._filter = ResultFilter.ALL
    order = list(screen._FILTER_ORDER)
    # forward
    idx = (order.index(screen._filter) + 1) % len(order)
    assert order[idx] is ResultFilter.OK
    idx = (idx + 1) % len(order)
    assert order[idx] is ResultFilter.BLOCKED
    idx = (idx + 1) % len(order)
    assert order[idx] is ResultFilter.ALL
    # backward от ALL
    idx = (order.index(ResultFilter.ALL) - 1) % len(order)
    assert order[idx] is ResultFilter.BLOCKED


def test_main_menu_both_uses_default_preset_from_settings():
    from rkn_tui.presets import THOROUGH
    from rkn_tui.storage import Config

    screen = MainMenuScreen(
        _ctx(NetworkContext.LIKELY_FILTERED),
        config=Config(default_preset=THOROUGH.name),
    )
    req = screen._build_request(ScanMode.BOTH)
    assert req.preset is THOROUGH
