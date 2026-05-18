"""Best-effort system diagnostics for AI handoff bundles.

The core scan results still come from rkn-block-checker. This module adds
local context that the upstream probe engine deliberately does not know about:
routes, DNS, proxy environment, and visible VPN/zapret-related processes.
Everything is optional and timeout-bound so saving a snapshot cannot depend on
any particular Linux tool being installed.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import gzip
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

DIAGNOSTICS_VERSION = 1
MAX_OUTPUT_CHARS = 12_000
HOSTLIST_SCAN_MAX_LINES = 250_000
HOSTLIST_SCAN_MAX_BYTES = 8_000_000

VPN_PROCESS_HINTS = (
    "zapret",
    "nfqws",
    "tpws",
    "amnezia",
    "wireguard",
    "wg-quick",
    "openvpn",
    "tailscale",
    "v2ray",
    "xray",
    "sing-box",
    "hysteria",
    "clash",
    "mihomo",
    "nekoray",
    "tun2socks",
    "openconnect",
    "protonvpn",
)

PROXY_ENV_KEYS = (
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)

ZAPRET_CONFIG_KEYS = (
    "FWTYPE",
    "NFQWS2_ENABLE",
    "NFQWS2_PORTS_TCP",
    "NFQWS2_PORTS_UDP",
    "MODE_FILTER",
    "GETLIST",
    "FILTER_MARK",
    "IFACE_WAN",
    "IFACE_WAN6",
    "INIT_APPLY_FW",
    "DISABLE_IPV4",
    "DISABLE_IPV6",
)

ZAPRET_HOSTLISTS = (
    ("user", Path("ipset/zapret-hosts-user.txt")),
    ("auto", Path("ipset/zapret-hosts-auto.txt")),
    ("exclude", Path("ipset/zapret-hosts-user-exclude.txt")),
    ("registry", Path("ipset/zapret-hosts.txt.gz")),
)


def collect_diagnostics(timeout: float = 1.0, results: Iterable[object] | None = None) -> dict:
    """Collect a compact, redacted diagnostic bundle.

    This is intentionally best-effort: every command may be absent or fail, and
    the snapshot should still save. The returned object is JSON-serializable.
    """
    results_list = list(results or [])
    return {
        "version": DIAGNOSTICS_VERSION,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "platform": _platform_info(),
        "proxy_env": _proxy_env(),
        "network": {
            "ip_br_addr": _run_if_available(["ip", "-br", "addr"], timeout),
            "ip_route_v4": _run_if_available(["ip", "-4", "route"], timeout),
            "ip_route_v6": _run_if_available(["ip", "-6", "route"], timeout),
            "ip_rule_v4": _run_if_available(["ip", "-4", "rule"], timeout),
            "ip_rule_v6": _run_if_available(["ip", "-6", "rule"], timeout),
            "ip_route_v4_all": _run_if_available(["ip", "-4", "route", "show", "table", "all"], timeout),
            "ip_route_v6_all": _run_if_available(["ip", "-6", "route", "show", "table", "all"], timeout),
            "resolvectl_status": _run_if_available(["resolvectl", "status"], timeout),
            "resolv_conf": _read_text_file(Path("/etc/resolv.conf")),
            "nmcli_active": _run_if_available(["nmcli", "connection", "show", "--active"], timeout),
            "wg_show": _run_if_available(["wg", "show"], timeout),
        },
        "vpn_and_zapret": {
            "processes": _vpn_processes(timeout),
            "systemd_units": _run_if_available(
                [
                    "systemctl",
                    "list-units",
                    "--type=service",
                    "--state=running",
                    "--no-pager",
                ],
                timeout,
                filter_terms=VPN_PROCESS_HINTS,
            ),
            "zapret_paths": _path_summary(
                [
                    Path("/opt/zapret2"),
                    Path("/opt/zapret"),
                    Path("/etc/zapret"),
                    Path("/etc/systemd/system/zapret.service"),
                    Path("/etc/systemd/system/zapret2.service"),
                ]
            ),
            "zapret2": _zapret2_summary(results_list),
            "nft_tables": _run_if_available(["nft", "list", "tables"], timeout),
        },
    }


def _platform_info() -> dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
    }


def _proxy_env() -> dict[str, str]:
    return {
        key: _redact(value)
        for key in PROXY_ENV_KEYS
        if (value := os.environ.get(key))
    }


def _run_if_available(
    argv: list[str],
    timeout: float,
    *,
    filter_terms: Iterable[str] = (),
) -> dict:
    executable = shutil.which(argv[0])
    if executable is None:
        return {"available": False, "argv": argv, "stdout": "", "stderr": ""}

    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _filter_lines(exc.stdout or "", filter_terms)
        stderr = _filter_lines(exc.stderr or "", filter_terms)
        return {
            "available": True,
            "argv": argv,
            "returncode": None,
            "timed_out": True,
            "stdout": _truncate(_redact(stdout)),
            "stderr": _truncate(_redact(stderr)),
        }
    except OSError as exc:
        return {
            "available": True,
            "argv": argv,
            "returncode": None,
            "timed_out": False,
            "stdout": "",
            "stderr": _truncate(_redact(f"{type(exc).__name__}: {exc}")),
        }

    stdout = _filter_lines(completed.stdout, filter_terms)
    stderr = _filter_lines(completed.stderr, filter_terms)
    return {
        "available": True,
        "argv": argv,
        "returncode": completed.returncode,
        "timed_out": False,
        "stdout": _truncate(_redact(stdout)),
        "stderr": _truncate(_redact(stderr)),
    }


def _vpn_processes(timeout: float) -> dict:
    result = _run_if_available(["ps", "-eo", "pid,ppid,comm,args"], timeout)
    if not result.get("available") or result.get("timed_out"):
        return result
    result["stdout"] = _truncate(_redact(_filter_lines(result.get("stdout", ""), VPN_PROCESS_HINTS)))
    return result


def _filter_lines(text: str, terms: Iterable[str]) -> str:
    terms_tuple = tuple(t.lower() for t in terms)
    if not terms_tuple:
        return text
    return "\n".join(
        line for line in text.splitlines()
        if any(term in line.lower() for term in terms_tuple)
    )


def _read_text_file(path: Path, max_chars: int = 4_000) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "available": False,
            "path": str(path),
            "content": "",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "available": True,
        "path": str(path),
        "content": _truncate(_redact(text), max_chars),
    }


def _path_summary(paths: Iterable[Path]) -> list[dict]:
    out: list[dict] = []
    for path in paths:
        item = {
            "path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir(),
            "children": [],
        }
        if path.is_dir():
            try:
                item["children"] = [
                    child.name for child in sorted(path.iterdir(), key=lambda p: p.name)[:50]
                ]
            except OSError:
                item["children"] = []
        out.append(item)
    return out


def _zapret2_summary(results: Iterable[object], root: Path = Path("/opt/zapret2")) -> dict:
    """Summarize zapret2 state without dumping private hostlists.

    A running zapret2/nfqws process only proves that DPI-bypass tooling is
    present. It does not prove the scan targets are covered by the user's
    hostlists or by policy routing. This summary captures that distinction for
    AI handoff snapshots.
    """
    targets = _scan_targets(results)
    hostlists = [
        _hostlist_summary(root / relative, label, [t["host"] for t in targets])
        for label, relative in ZAPRET_HOSTLISTS
    ]
    matches_by_host: dict[str, list[str]] = {}
    for item in hostlists:
        for host in item.get("matched_hosts", []):
            matches_by_host.setdefault(str(host), []).append(str(item["label"]))

    return {
        "root": str(root),
        "exists": root.exists(),
        "config": _zapret_config_summary(root / "config"),
        "hostlists": hostlists,
        "scan_target_coverage": [
            {
                "name": target["name"],
                "url": target["url"],
                "host": target["host"],
                "verdict": target["verdict"],
                "matched_hostlists": sorted(matches_by_host.get(target["host"], [])),
            }
            for target in targets
        ],
        "interpretation_hints": [
            "zapret2/nfqws active means DPI-bypass tooling is present, not that every blocked site is covered.",
            "A RU public IP plus TLS_BLOCK results can still happen with targeted zapret2 rules or hostlist gaps.",
            "Compare matched_hostlists with blocked scan targets before concluding that zapret2 failed globally.",
        ],
    }


def _zapret_config_summary(path: Path) -> dict:
    if not path.exists():
        return {"available": False, "path": str(path), "values": {}}

    values: dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parsed = _parse_shell_assignment(raw_line)
            if parsed is None:
                continue
            key, value = parsed
            if key in ZAPRET_CONFIG_KEYS:
                values[key] = _redact(value)
    except OSError as exc:
        return {
            "available": False,
            "path": str(path),
            "values": {},
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {"available": True, "path": str(path), "values": values}


def _parse_shell_assignment(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return None
    return key, _strip_shell_quotes(value.strip())


def _strip_shell_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _scan_targets(results: Iterable[object]) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in results:
        url = str(getattr(result, "url", "") or "")
        host = _host_from_url(url)
        if not host or host in seen:
            continue
        seen.add(host)
        verdict = getattr(getattr(result, "verdict", ""), "name", "")
        targets.append(
            {
                "name": str(getattr(result, "name", "") or ""),
                "url": url,
                "host": host,
                "verdict": str(verdict or getattr(result, "verdict", "") or ""),
            }
        )
    return targets


def _host_from_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.hostname or ""
    return host.rstrip(".").lower()


def _hostlist_summary(path: Path, label: str, target_hosts: list[str]) -> dict:
    item: dict = {
        "label": label,
        "path": str(path),
        "exists": path.exists(),
        "line_count": 0,
        "matched_hosts": [],
        "truncated": False,
    }
    if not path.exists():
        return item

    try:
        size = path.stat().st_size
    except OSError as exc:
        item["error"] = f"{type(exc).__name__}: {exc}"
        return item
    item["size_bytes"] = size
    if size > HOSTLIST_SCAN_MAX_BYTES:
        item["truncated"] = True
        item["error"] = "file too large for safe snapshot scan"
        return item

    matched: set[str] = set()
    try:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
            for index, line in enumerate(fh):
                if index >= HOSTLIST_SCAN_MAX_LINES:
                    item["truncated"] = True
                    break
                entry = _normalize_hostlist_entry(line)
                if not entry:
                    continue
                item["line_count"] += 1
                for host in target_hosts:
                    if _host_matches_entry(host, entry):
                        matched.add(host)
    except (OSError, gzip.BadGzipFile) as exc:
        item["error"] = f"{type(exc).__name__}: {exc}"

    item["matched_hosts"] = sorted(matched)
    return item


def _normalize_hostlist_entry(line: str) -> str:
    value = line.split("#", 1)[0].strip().lower()
    if not value:
        return ""
    value = value.removeprefix("http://").removeprefix("https://")
    value = value.split("/", 1)[0].strip().rstrip(".")
    if value.startswith("*."):
        value = value[2:]
    return value


def _host_matches_entry(host: str, entry: str) -> bool:
    if not host or not entry:
        return False
    entry = entry.lstrip(".")
    return host == entry or host.endswith(f".{entry}")


def _redact(text: str) -> str:
    """Remove obvious credentials from env vars and process arguments."""
    redacted = re.sub(
        r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@",
        r"\1<user>:<redacted>@",
        text,
    )
    redacted = re.sub(
        r"(?i)\b(password|passwd|pwd|token|secret|private[_-]?key|ssh[_-]?key)=\S+",
        r"\1=<redacted>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(--(?:password|passwd|token|secret|private-key|ssh-key)\s+)\S+",
        r"\1<redacted>",
        redacted,
    )
    return redacted


def _truncate(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"
