from unittest.mock import patch

from rkn_checker.models import CheckResult, Verdict

from rkn_tui import vpn_check
from rkn_tui.vpn_check import NetworkContext, detect


def _make_result(verdict: Verdict) -> CheckResult:
    return CheckResult(name="x", url="https://x.test", verdict=verdict)


def test_detect_vpn_when_blocked_site_works():
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value={}),
    ):
        mock_check.side_effect = [
            _make_result(Verdict.OK),  # control
            _make_result(Verdict.OK),  # "blocked" site — но OK значит мы под ВПН
        ]
        result = detect(skip_self_info=True)
    assert result.status is NetworkContext.LIKELY_VPN_OR_CLEAN


def test_detect_filtered_when_blocked_site_blocked():
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value={}),
    ):
        mock_check.side_effect = [
            _make_result(Verdict.OK),  # control работает
            _make_result(Verdict.TLS_BLOCK),  # blocked заблокирован
        ]
        result = detect(skip_self_info=True)
    assert result.status is NetworkContext.LIKELY_FILTERED
    assert result.blocked_verdict is Verdict.TLS_BLOCK


def test_detect_broken_when_control_fails():
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value={}),
    ):
        mock_check.side_effect = [
            _make_result(Verdict.DOWN),  # даже контроль сломан
            _make_result(Verdict.TLS_BLOCK),
        ]
        result = detect(skip_self_info=True)
    assert result.status is NetworkContext.NETWORK_BROKEN


def test_detect_includes_self_info_when_requested():
    fake_info = {"ip": "1.2.3.4", "city": "Moscow"}
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value=fake_info),
    ):
        mock_check.side_effect = [_make_result(Verdict.OK), _make_result(Verdict.OK)]
        result = detect(skip_self_info=False)
    assert result.self_info == fake_info


def test_detect_skips_self_info_when_requested():
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info") as mock_self,
    ):
        mock_check.side_effect = [_make_result(Verdict.OK), _make_result(Verdict.OK)]
        detect(skip_self_info=True)
        mock_self.assert_not_called()


def test_headline_uses_traffic_light_emoji():
    """Не критично для логики, но эмодзи в headline это часть UX-контракта."""
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value={}),
    ):
        mock_check.side_effect = [_make_result(Verdict.OK), _make_result(Verdict.OK)]
        r1 = detect(skip_self_info=True)
        mock_check.side_effect = [_make_result(Verdict.OK), _make_result(Verdict.TLS_BLOCK)]
        r2 = detect(skip_self_info=True)
        mock_check.side_effect = [_make_result(Verdict.DOWN), _make_result(Verdict.OK)]
        r3 = detect(skip_self_info=True)
    assert "🟢" in r1.headline
    assert "🟡" in r2.headline
    assert "🔴" in r3.headline
