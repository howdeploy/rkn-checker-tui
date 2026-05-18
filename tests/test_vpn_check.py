from unittest.mock import patch

from rkn_checker.models import CheckResult, Verdict

from rkn_tui.vpn_check import (
    PROBE_BLOCKED,
    NetworkContext,
    detect,
)


def _r(verdict: Verdict, name: str = "x") -> CheckResult:
    return CheckResult(name=name, url=f"https://{name}.test", verdict=verdict)


def _side_effect(control: Verdict, *blocked: Verdict):
    """Готовый side_effect по имени target — устойчив к параллельному detect()."""
    results = {"control": _r(control, "control")}
    for i, name_url in enumerate(PROBE_BLOCKED):
        v = blocked[i] if i < len(blocked) else Verdict.DOWN
        results[name_url[0]] = _r(v, name_url[0])

    def fake_check(name: str, url: str, timeout: float = 4.0) -> CheckResult:
        return results[name]

    return fake_check


def test_detect_vpn_when_all_blocked_sites_work():
    """Все «политические» открылись и сигнатур цензуры нет → ВПН/чистая сеть."""
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value={}),
    ):
        mock_check.side_effect = _side_effect(
            Verdict.OK, Verdict.OK, Verdict.OK, Verdict.OK
        )
        result = detect(skip_self_info=True)
    assert result.status is NetworkContext.LIKELY_VPN_OR_CLEAN


def test_detect_filtered_when_any_explicit_censorship_signature():
    """Достаточно одного TLS_BLOCK / DNS_BLOCK / TCP_RESET / HTTP_STUB → ТСПУ."""
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value={}),
    ):
        mock_check.side_effect = _side_effect(
            Verdict.OK, Verdict.OK, Verdict.TLS_BLOCK, Verdict.OK
        )
        result = detect(skip_self_info=True)
    assert result.status is NetworkContext.LIKELY_FILTERED


def test_detect_broken_when_control_fails():
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value={}),
    ):
        mock_check.side_effect = _side_effect(
            Verdict.DOWN, Verdict.TLS_BLOCK, Verdict.OK, Verdict.OK
        )
        result = detect(skip_self_info=True)
    assert result.status is NetworkContext.NETWORK_BROKEN


def test_detect_vpn_when_partial_ok_and_no_censorship():
    """Раньше был баг: linkedin упал под ВПН (DOWN), нас флагало 🟡.

    Сейчас: хоть один blocked-сайт ответил OK + нет сигнатур цензуры → 🟢.
    """
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value={}),
    ):
        mock_check.side_effect = _side_effect(
            Verdict.OK, Verdict.DOWN, Verdict.OK, Verdict.TIMEOUT
        )
        result = detect(skip_self_info=True)
    assert result.status is NetworkContext.LIKELY_VPN_OR_CLEAN


def test_detect_vpn_when_non_russian_ip_even_if_all_blocked_down():
    """На иностранном IP с упавшими linkedin/rutracker — это VPS, не ТСПУ."""
    fake_info = {"ip": "203.0.113.10", "country": "DE", "org": "Example VPS"}
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value=fake_info),
    ):
        mock_check.side_effect = _side_effect(
            Verdict.OK, Verdict.DOWN, Verdict.DOWN, Verdict.TIMEOUT
        )
        result = detect(skip_self_info=False)
    assert result.status is NetworkContext.LIKELY_VPN_OR_CLEAN
    assert "Example VPS" in result.detail
    assert "DE" in result.detail


def test_detect_non_russian_ip_with_single_tls_block_is_not_tspu():
    """Зарубежный VPN/VPS + один TLS_BLOCK — аномалия маршрута, не типичная ТСПУ-сеть."""
    fake_info = {"ip": "203.0.113.20", "country": "DE", "org": "Example VPS"}
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value=fake_info),
    ):
        mock_check.side_effect = _side_effect(
            Verdict.OK, Verdict.DOWN, Verdict.DOWN, Verdict.TLS_BLOCK
        )
        result = detect(skip_self_info=False)
    assert result.status is NetworkContext.INDETERMINATE
    assert "не похоже на типичную российскую ТСПУ-сеть" in result.detail
    assert "grani" in result.detail


def test_detect_indeterminate_when_ru_ip_and_all_blocked_ambiguous():
    """RU IP + только DOWN/TIMEOUT на blocked сайтах — нельзя уверенно сказать."""
    fake_info = {"ip": "94.45.10.10", "country": "RU", "org": "Beeline"}
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value=fake_info),
    ):
        mock_check.side_effect = _side_effect(
            Verdict.OK, Verdict.DOWN, Verdict.TIMEOUT, Verdict.DOWN
        )
        result = detect(skip_self_info=False)
    assert result.status is NetworkContext.INDETERMINATE


def test_detect_includes_self_info_when_requested():
    fake_info = {"ip": "1.2.3.4", "city": "Moscow"}
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value=fake_info),
    ):
        mock_check.side_effect = _side_effect(
            Verdict.OK, Verdict.OK, Verdict.OK, Verdict.OK
        )
        result = detect(skip_self_info=False)
    assert result.self_info == fake_info


def test_detect_skips_self_info_when_requested():
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info") as mock_self,
    ):
        mock_check.side_effect = _side_effect(
            Verdict.OK, Verdict.OK, Verdict.OK, Verdict.OK
        )
        detect(skip_self_info=True)
        mock_self.assert_not_called()


def test_headline_uses_traffic_light_emoji():
    """Эмодзи в headline — часть UX-контракта, бейдж рисуется по ним."""
    with (
        patch("rkn_tui.vpn_check.check_url") as mock_check,
        patch("rkn_tui.vpn_check.engine.fetch_self_info", return_value={}),
    ):
        mock_check.side_effect = _side_effect(Verdict.OK, Verdict.OK, Verdict.OK, Verdict.OK)
        r1 = detect(skip_self_info=True)
        mock_check.side_effect = _side_effect(Verdict.OK, Verdict.OK, Verdict.TLS_BLOCK, Verdict.OK)
        r2 = detect(skip_self_info=True)
        mock_check.side_effect = _side_effect(Verdict.DOWN, Verdict.OK, Verdict.OK, Verdict.OK)
        r3 = detect(skip_self_info=True)
        mock_check.side_effect = _side_effect(Verdict.OK, Verdict.DOWN, Verdict.TIMEOUT, Verdict.DOWN)
        r4 = detect(skip_self_info=True)
    assert "🟢" in r1.headline
    assert "🟡" in r2.headline
    assert "🔴" in r3.headline
    assert "⚪" in r4.headline


def test_country_code_normalisation_handles_lowercase():
    """country может прийти как 'ru' / 'RU' / 'Russia' — все эти варианты считаем за RU."""
    from rkn_tui.vpn_check import _country_code, _is_russian_ip

    assert _country_code({"country": "ru"}) == "RU"
    assert _is_russian_ip({"country": "ru"})
    assert _is_russian_ip({"country": "Russia"})
    assert not _is_russian_ip({"country": "DE"})
    # Если страна не определена — нейтрально, считаем как RU (чтобы пробы решали)
    assert _is_russian_ip({})
