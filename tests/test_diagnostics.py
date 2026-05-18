from __future__ import annotations

import json
from pathlib import Path

from rkn_checker.models import CheckResult, Verdict

from rkn_tui import diagnostics


def test_redact_url_credentials():
    text = "https://user:secret@example.com/path socks5://u:p@127.0.0.1:1080"
    redacted = diagnostics._redact(text)
    assert "secret" not in redacted
    assert "://<user>:<redacted>@" in redacted


def test_redact_key_value_secrets():
    text = "TOKEN=abc password=hunter2 --private-key /tmp/key"
    redacted = diagnostics._redact(text)
    assert "abc" not in redacted
    assert "hunter2" not in redacted
    assert "/tmp/key" not in redacted


def test_filter_lines_keeps_only_matching_terms():
    text = "plain process\nzapret service\nwireguard tunnel"
    filtered = diagnostics._filter_lines(text, ("zapret", "wireguard"))
    assert "plain" not in filtered
    assert "zapret service" in filtered
    assert "wireguard tunnel" in filtered


def test_zapret2_summary_correlates_scan_targets_without_dumping_hostlists(tmp_path: Path):
    ipset = tmp_path / "ipset"
    ipset.mkdir()
    (tmp_path / "config").write_text(
        "\n".join(
            [
                "FWTYPE=nftables",
                "NFQWS2_ENABLE=1",
                "NFQWS2_PORTS_TCP=80,443",
                "MODE_FILTER=autohostlist",
                "GETLIST=get_antizapret_domains.sh",
            ]
        ),
        encoding="utf-8",
    )
    (ipset / "zapret-hosts-user.txt").write_text(
        "private-vpn-endpoint.example\n*.facebook.com\n",
        encoding="utf-8",
    )
    (ipset / "zapret-hosts-auto.txt").write_text(
        "gateway.discord.gg\n",
        encoding="utf-8",
    )
    (ipset / "zapret-hosts-user-exclude.txt").write_text("", encoding="utf-8")

    summary = diagnostics._zapret2_summary(
        [
            CheckResult(name="discord", url="https://discord.com/", verdict=Verdict.TLS_BLOCK),
            CheckResult(name="facebook", url="https://www.facebook.com/", verdict=Verdict.OK),
        ],
        root=tmp_path,
    )

    assert summary["config"]["values"]["MODE_FILTER"] == "autohostlist"
    coverage = {item["host"]: item for item in summary["scan_target_coverage"]}
    assert coverage["discord.com"]["matched_hostlists"] == []
    assert coverage["www.facebook.com"]["matched_hostlists"] == ["user"]
    assert "private-vpn-endpoint.example" not in json.dumps(summary)
