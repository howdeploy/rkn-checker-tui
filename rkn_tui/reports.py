"""Human-readable reports in the upstream rkn-block-checker style."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

from rkn_checker.models import BLOCKED_VERDICTS, CheckResult, Confidence, Verdict
from rkn_checker.targets import BLACK_URLS, WHITE_URLS

from .engine import ScanMode, ScanRequest

WIDTH = 70


@dataclass(frozen=True)
class ReportSections:
    white: list[CheckResult]
    black: list[CheckResult]
    ad_hoc: list[CheckResult]


def render_report(
    results: Iterable[CheckResult],
    *,
    self_info: Optional[dict] = None,
    mode: str = "both",
    request: Optional[ScanRequest] = None,
    context_headline: str = "",
    context_detail: str = "",
    diagnostics: Optional[dict] = None,
    mask_ip: bool = True,
) -> str:
    """Render a shareable plain-text report.

    The layout intentionally mirrors upstream rkn-block-checker's CLI report,
    while appending our TUI-only network/zapret diagnostics.
    """
    results_list = list(results)
    sections = split_results(results_list, request=request, mode=mode)

    lines: list[str] = []
    _append_header(lines, self_info or {}, context_headline, mask_ip)

    if sections.white:
        _append_section(lines, "Whitelist (should always work)", sections.white)
    if sections.black:
        _append_section(lines, "Blacklist (RKN-restricted)", sections.black)
    if sections.ad_hoc:
        _append_section(lines, f"Ad-hoc URLs ({len(sections.ad_hoc)})", sections.ad_hoc)

    if sections.white or sections.black:
        _append_summary(lines, sections.white, sections.black)
    else:
        _append_ad_hoc_summary(lines, sections.ad_hoc)

    _append_context(lines, context_headline, context_detail, diagnostics or {}, sections)
    return "\n".join(lines).rstrip() + "\n"


def split_results(
    results: Iterable[CheckResult],
    *,
    request: Optional[ScanRequest] = None,
    mode: str = "both",
) -> ReportSections:
    results_list = list(results)
    if request is not None:
        mode = request.mode.value
        if request.mode is ScanMode.AD_HOC:
            return ReportSections([], [], results_list)
        white_targets = request.custom_white if request.custom_white is not None else WHITE_URLS
        black_targets = request.custom_black if request.custom_black is not None else BLACK_URLS
    else:
        white_targets = WHITE_URLS
        black_targets = BLACK_URLS

    if mode == ScanMode.WHITE.value:
        return ReportSections(results_list, [], [])
    if mode == ScanMode.BLACK.value:
        return ReportSections([], results_list, [])
    if mode == ScanMode.AD_HOC.value:
        return ReportSections([], [], results_list)

    white_keys = _target_keys(white_targets)
    black_keys = _target_keys(black_targets)
    white: list[CheckResult] = []
    black: list[CheckResult] = []
    ad_hoc: list[CheckResult] = []
    for result in results_list:
        keys = {(result.name, result.url), ("", result.url), (result.name, "")}
        if keys & white_keys:
            white.append(result)
        elif keys & black_keys:
            black.append(result)
        else:
            ad_hoc.append(result)
    return ReportSections(white, black, ad_hoc)


def _target_keys(targets: dict[str, str]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for name, url in targets.items():
        keys.add((name, url))
        keys.add((name, ""))
        keys.add(("", url))
    return keys


def _append_header(lines: list[str], info: dict, context_headline: str, mask_ip: bool) -> None:
    lines.append("=" * WIDTH)
    lines.append("  RKN Block Checker")
    lines.append("=" * WIDTH)
    if info:
        lines.append(f"  IP:       {_mask_ip(str(info.get('ip', '?')), mask_ip)}")
        lines.append(f"  ISP:      {info.get('org') or info.get('isp') or '?'}")
        loc = f"{info.get('city', '?')}, {info.get('region', '?')}, {info.get('country', '?')}"
        lines.append(f"  Location: {loc}")
    else:
        lines.append("  IP:       not collected")
    if context_headline:
        lines.append(f"  Context:  {context_headline}")
    lines.append("-" * WIDTH)


def _append_section(lines: list[str], title: str, results: list[CheckResult]) -> None:
    lines.append("")
    lines.append(title)
    lines.append(f"  {'name':<14}{'verdict':<22}{'TCP':>8}{'TLS':>8}{'PLT':>8}  {'status':<6}")
    lines.append(f"  {'-' * 68}")
    for result in results:
        lines.extend(_format_result(result))


def _format_result(result: CheckResult) -> list[str]:
    label = _label_for(result.verdict, result.confidence)
    status = str(result.status_code) if result.status_code is not None else "-"
    tcp = _fmt_ms(result.tcp_time_ms)
    tls = _fmt_ms(result.tls_time_ms)
    plt = _fmt_ms(result.plt_ms)
    name_col = result.name[:14].ljust(14)
    label_col = label[:22].ljust(22)
    lines = [
        f"  {name_col}{label_col}{tcp:>8}{tls:>8}{plt:>8}  {status:<6}"
    ]
    for note in result.notes:
        lines.append(f"    └ {note}")
    return lines


def _append_summary(lines: list[str], white: list[CheckResult], black: list[CheckResult]) -> None:
    white_ok = sum(1 for result in white if result.verdict is Verdict.OK)
    black_ok = sum(1 for result in black if result.verdict is Verdict.OK)
    black_blocked = sum(
        1 for result in black
        if result.verdict in BLOCKED_VERDICTS and result.verdict is not Verdict.TIMEOUT
    )
    black_timeout = sum(1 for result in black if result.verdict is Verdict.TIMEOUT)
    black_high_conf = sum(
        1 for result in black
        if result.verdict in BLOCKED_VERDICTS and result.confidence is Confidence.HIGH
    )

    lines.append("")
    lines.append("=" * WIDTH)
    lines.append("  Summary")
    lines.append("-" * WIDTH)
    lines.append(f"  Whitelist: {white_ok}/{len(white)} working")
    timeout_part = f", {black_timeout} timed out" if black_timeout else ""
    lines.append(
        f"  Blacklist: {black_ok}/{len(black)} open, "
        f"{black_blocked}/{len(black)} blocked{timeout_part}"
    )

    verdict, note = _summary_verdict(
        white_ok,
        len(white),
        black_ok,
        black_blocked,
        len(black),
        black_high_conf,
        black_timeout,
    )
    lines.append("")
    lines.append(f"  → {verdict}")
    if note:
        lines.append(f"    {note}")

    types = Counter(result.verdict for result in black if result.verdict in BLOCKED_VERDICTS)
    if types:
        lines.append("")
        lines.append("  Block types in the blacklist:")
        for verdict_type, count in types.most_common():
            lines.append(f"    {_label_for(verdict_type, Confidence.HIGH)}: {count}")
    lines.append("=" * WIDTH)


def _append_ad_hoc_summary(lines: list[str], results: list[CheckResult]) -> None:
    ok = sum(1 for result in results if result.verdict is Verdict.OK)
    blocked = sum(1 for result in results if result.verdict in BLOCKED_VERDICTS)
    lines.append("")
    lines.append("=" * WIDTH)
    lines.append("  Summary")
    lines.append("-" * WIDTH)
    lines.append(f"  Ad-hoc: {ok}/{len(results)} open, {blocked}/{len(results)} suspicious")
    types = Counter(result.verdict for result in results if result.verdict in BLOCKED_VERDICTS)
    if types:
        lines.append("")
        lines.append("  Block types:")
        for verdict_type, count in types.most_common():
            lines.append(f"    {_label_for(verdict_type, Confidence.HIGH)}: {count}")
    lines.append("=" * WIDTH)


def _append_context(
    lines: list[str],
    context_headline: str,
    context_detail: str,
    diagnostics: dict,
    sections: ReportSections,
) -> None:
    context_lines: list[str] = []
    if context_headline:
        context_lines.append(context_headline)
    if context_detail:
        context_lines.append(context_detail)

    network = diagnostics.get("network") if isinstance(diagnostics.get("network"), dict) else {}
    default_route = _first_nonempty_line(_cmd_stdout(network.get("ip_route_v4")))
    if default_route:
        context_lines.append(f"Default route: {default_route}")
    dns = _dns_summary(network)
    if dns:
        context_lines.append(f"DNS: {dns}")

    vpn = diagnostics.get("vpn_and_zapret") if isinstance(diagnostics.get("vpn_and_zapret"), dict) else {}
    units = _compact_units(_cmd_stdout(vpn.get("systemd_units")))
    if units:
        context_lines.append(f"Active VPN/zapret units: {units}")

    zapret2 = vpn.get("zapret2") if isinstance(vpn.get("zapret2"), dict) else {}
    zapret_line = _zapret2_line(zapret2)
    if zapret_line:
        context_lines.append(zapret_line)
    coverage_line = _zapret_coverage_line(zapret2, sections)
    if coverage_line:
        context_lines.append(coverage_line)

    if not context_lines:
        return

    lines.append("")
    lines.append("=" * WIDTH)
    lines.append("  Diagnostic context")
    lines.append("-" * WIDTH)
    for line in context_lines:
        lines.extend(f"  {part}" for part in _wrap(line, 66))
    lines.append("=" * WIDTH)


def _summary_verdict(
    white_ok: int,
    white_total: int,
    black_ok: int,
    black_blocked: int,
    black_total: int,
    black_high_conf: int = 0,
    black_timeout: int = 0,
) -> tuple[str, str]:
    effective_total = black_total - black_timeout

    if white_total > 0 and white_ok < white_total / 2:
        return (
            "Inconclusive - control whitelist is also failing.",
            "Can't separate censorship from a broken uplink without a working baseline.",
        )
    if effective_total <= 0:
        return (
            "Inconclusive - all blacklist probes timed out.",
            "Cannot determine blocking status when every probe times out.",
        )
    if black_blocked == 0 and black_ok == effective_total:
        return (
            "Likely NOT in an RKN-blocked zone (or VPN is masking it).",
            "All blacklisted sites loaded; VPN/proxy or a clean network may be masking blocks.",
        )
    if black_blocked >= effective_total * 0.7:
        if effective_total > 0 and black_high_conf >= effective_total * 0.5:
            return (
                "Likely in an RKN-blocked zone (high confidence).",
                f"{black_high_conf}/{effective_total} blacklist failures match high-confidence patterns.",
            )
        return (
            "Likely in an RKN-blocked zone (medium confidence).",
            "Most blacklist failures match censorship patterns, but a control vantage point would confirm.",
        )
    return (
        "Partial blocks - some blacklisted sites still load.",
        "Mixed signals: selective filtering, server issues, CDN flake, or partial circumvention.",
    )


def _label_for(verdict: Verdict, confidence: Confidence) -> str:
    if verdict is Verdict.OK:
        return "✓ OK"
    if verdict is Verdict.DOWN:
        return "· DOWN"
    if verdict is Verdict.UNKNOWN:
        return "? UNKNOWN"

    base = {
        Verdict.DNS_BLOCK: "DNS",
        Verdict.TCP_RESET: "TCP RESET",
        Verdict.TLS_BLOCK: "TLS DPI",
        Verdict.HTTP_STUB: "HTTP STUB",
        Verdict.TIMEOUT: "TIMEOUT",
    }.get(verdict, verdict.value)

    if confidence is Confidence.HIGH:
        return f"✗ {base}"
    if confidence is Confidence.MEDIUM:
        return f"~ LIKELY {base}"
    return f"? {base}?"


def _fmt_ms(value: float | None) -> str:
    return f"{value:.0f}ms" if value is not None else "-"


def _mask_ip(ip: str, mask: bool) -> str:
    if not mask or not ip or ip == "?":
        return ip
    parts = ip.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        return f"{parts[0]}.{parts[1]}.xxx.xxx"
    if ":" in ip:
        chunks = ip.split(":")
        return ":".join(chunks[:2] + ["xxxx", "xxxx"])
    return ip


def _cmd_stdout(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("stdout") or value.get("content") or "")
    return ""


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _dns_summary(network: dict) -> str:
    resolv = network.get("resolv_conf")
    text = ""
    if isinstance(resolv, dict):
        text = str(resolv.get("content") or "")
    nameservers = [
        line.split(None, 1)[1]
        for line in text.splitlines()
        if line.strip().startswith("nameserver ") and len(line.split(None, 1)) == 2
    ]
    if nameservers:
        return ", ".join(nameservers[:3])
    status = _cmd_stdout(network.get("resolvectl_status"))
    for line in status.splitlines():
        stripped = line.strip()
        if stripped.startswith("Current DNS Server:"):
            return stripped.removeprefix("Current DNS Server:").strip()
    return ""


def _compact_units(text: str) -> str:
    names: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if parts:
            names.append(parts[0])
    return ", ".join(names[:8])


def _zapret2_line(zapret2: dict) -> str:
    if not zapret2:
        return ""
    config = zapret2.get("config") if isinstance(zapret2.get("config"), dict) else {}
    values = config.get("values") if isinstance(config.get("values"), dict) else {}
    mode = values.get("MODE_FILTER")
    tcp = values.get("NFQWS2_PORTS_TCP")
    udp = values.get("NFQWS2_PORTS_UDP")
    fw = values.get("FWTYPE")
    parts = []
    if mode:
        parts.append(f"mode={mode}")
    if fw:
        parts.append(f"fw={fw}")
    if tcp:
        parts.append(f"tcp={tcp}")
    if udp:
        parts.append(f"udp={udp}")
    if not parts:
        return ""
    return "zapret2: " + ", ".join(parts)


def _zapret_coverage_line(zapret2: dict, sections: ReportSections) -> str:
    coverage = zapret2.get("scan_target_coverage") if isinstance(zapret2.get("scan_target_coverage"), list) else []
    if not coverage:
        return ""
    blocked_names = {
        result.name
        for result in [*sections.black, *sections.ad_hoc]
        if result.verdict in BLOCKED_VERDICTS
    }
    relevant = [
        item for item in coverage
        if isinstance(item, dict) and str(item.get("name")) in blocked_names
    ]
    if not relevant:
        return ""
    matched = [item for item in relevant if item.get("matched_hostlists")]
    misses = [str(item.get("name")) for item in relevant if not item.get("matched_hostlists")]
    line = f"zapret2 target coverage: {len(matched)}/{len(relevant)} blocked/suspicious targets matched hostlists"
    if misses:
        line += f"; unmatched: {', '.join(misses[:8])}"
    return line


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
