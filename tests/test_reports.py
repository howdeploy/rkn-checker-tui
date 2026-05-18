from __future__ import annotations

from rkn_checker.models import CheckResult, Confidence, Verdict
from rkn_checker.targets import BLACK_URLS, WHITE_URLS

from rkn_tui.reports import render_report, split_results


def _r(
    name: str,
    url: str,
    verdict: Verdict = Verdict.OK,
    confidence: Confidence = Confidence.HIGH,
    **kwargs,
) -> CheckResult:
    return CheckResult(
        name=name,
        url=url,
        verdict=verdict,
        confidence=confidence,
        **kwargs,
    )


def test_render_report_matches_upstream_shape_and_masks_ip():
    results = [
        _r("gosuslugi", WHITE_URLS["gosuslugi"], tcp_time_ms=18, tls_time_ms=42, plt_ms=380, status_code=200),
        _r(
            "instagram",
            BLACK_URLS["instagram"],
            Verdict.TLS_BLOCK,
            Confidence.MEDIUM,
            tcp_time_ms=22,
            notes=["TLS reset right after ClientHello - consistent with SNI-based DPI"],
        ),
    ]

    report = render_report(
        results,
        self_info={
            "ip": "203.0.113.20",
            "org": "AS12389 Rostelecom",
            "city": "Moscow",
            "region": "Moscow",
            "country": "RU",
        },
        context_headline="🟡 Сеть с фильтрацией",
    )

    assert "RKN Block Checker" in report
    assert "IP:       203.0.xxx.xxx" in report
    assert "Whitelist (should always work)" in report
    assert "Blacklist (RKN-restricted)" in report
    assert "gosuslugi     ✓ OK" in report
    assert "instagram     ~ LIKELY TLS DPI" in report
    assert "└ TLS reset right after ClientHello" in report
    assert "Whitelist: 1/1 working" in report
    assert "Blacklist: 0/1 open, 1/1 blocked" in report
    assert "Block types in the blacklist:" in report


def test_render_report_adds_diagnostic_context_and_zapret_coverage():
    results = [
        _r("discord", BLACK_URLS["discord"], Verdict.TLS_BLOCK, Confidence.MEDIUM),
        _r("facebook", BLACK_URLS["facebook"], Verdict.TLS_BLOCK, Confidence.MEDIUM),
    ]
    diagnostics = {
        "network": {
            "ip_route_v4": {"stdout": "default via 192.168.0.1 dev wlan0\n"},
            "resolv_conf": {"content": "nameserver 100.100.100.100\n"},
        },
        "vpn_and_zapret": {
            "systemd_units": {
                "stdout": "  zapret2.service loaded active running zapret2.service\n"
            },
            "zapret2": {
                "config": {
                    "values": {
                        "MODE_FILTER": "autohostlist",
                        "FWTYPE": "nftables",
                        "NFQWS2_PORTS_TCP": "80,443",
                    }
                },
                "scan_target_coverage": [
                    {"name": "discord", "matched_hostlists": []},
                    {"name": "facebook", "matched_hostlists": ["registry"]},
                ],
            },
        },
    }

    report = render_report(
        results,
        mode="black",
        context_detail="Сигнатура цензуры на Discord.",
        diagnostics=diagnostics,
    )

    assert "Diagnostic context" in report
    assert "Default route: default via 192.168.0.1 dev wlan0" in report
    assert "DNS: 100.100.100.100" in report
    assert "Active VPN/zapret units: zapret2.service" in report
    assert "zapret2: mode=autohostlist, fw=nftables, tcp=80,443" in report
    assert "zapret2 target coverage: 1/2" in report
    assert "unmatched: discord" in report


def test_split_results_keeps_ad_hoc_separate():
    result = _r("example-com", "https://example.com/")
    sections = split_results([result], mode="ad_hoc")
    assert sections.white == []
    assert sections.black == []
    assert sections.ad_hoc == [result]
