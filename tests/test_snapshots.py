"""Тесты на снапшоты результатов.

Все пишут в tmp_path. Юзаем явный `directory=` параметр у save/list/load,
чтобы не трогать реальный ~/.config.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rkn_checker.models import CheckResult, Confidence, Verdict

from rkn_tui import snapshots
from rkn_tui.snapshots import (
    diff_snapshots,
    list_snapshots,
    load_snapshot,
    save_snapshot,
)


def _ok(name: str = "example") -> CheckResult:
    return CheckResult(
        name=name,
        url=f"https://{name}.test/",
        verdict=Verdict.OK,
        confidence=Confidence.HIGH,
        tls_ok=True,
        status_code=200,
    )


def _blocked(name: str = "rutracker", verdict: Verdict = Verdict.TLS_BLOCK) -> CheckResult:
    return CheckResult(
        name=name,
        url=f"https://{name}.test/",
        verdict=verdict,
        confidence=Confidence.HIGH,
        tls_ok=False,
        tls_error="handshake failed",
    )


def test_save_and_load_roundtrip(tmp_path: Path):
    path = save_snapshot(
        [_ok("good"), _blocked("rt")],
        label="После апдейта ТСПУ",
        mode="both",
        preset="default",
        self_info={"ip": "1.2.3.4", "country": "RU"},
        context_status="filtered",
        directory=tmp_path,
    )
    assert path.exists()
    snap = load_snapshot(path)
    assert snap is not None
    assert snap.meta.label == "После апдейта ТСПУ"
    assert snap.meta.mode == "both"
    assert snap.meta.preset == "default"
    assert snap.meta.context_status == "filtered"
    assert snap.meta.total == 2
    assert snap.meta.blocked == 1
    assert snap.self_info["ip"] == "1.2.3.4"
    names = sorted(r.name for r in snap.results)
    assert names == ["good", "rt"]


def test_save_and_load_diagnostics_roundtrip(tmp_path: Path):
    path = save_snapshot(
        [_ok()],
        label="diag",
        mode="both",
        preset="default",
        diagnostics={"version": 1, "network": {"ip_route_v4": {"stdout": "default via 1.1.1.1"}}},
        directory=tmp_path,
    )
    snap = load_snapshot(path)
    assert snap is not None
    assert snap.diagnostics["version"] == 1
    assert "network" in snap.diagnostics


def test_save_writes_filename_with_timestamp_and_slug(tmp_path: Path):
    dt = datetime(2026, 5, 18, 12, 30, 45, tzinfo=timezone.utc)
    path = save_snapshot(
        [_ok()],
        label="Утренний скан!",
        mode="quick",
        preset="quick",
        directory=tmp_path,
        now=dt,
    )
    assert path.name.startswith("20260518T123045-")
    assert path.name.endswith(".json")


def test_save_handles_empty_label(tmp_path: Path):
    path = save_snapshot(
        [_ok()],
        label="",
        mode="both",
        preset="default",
        directory=tmp_path,
    )
    assert path.exists()
    assert "snap" in path.name


def test_save_does_not_overwrite_same_second_same_label(tmp_path: Path):
    dt = datetime(2026, 5, 18, 12, 30, 45, tzinfo=timezone.utc)
    p1 = save_snapshot(
        [_ok("a")],
        label="same",
        mode="both",
        preset="default",
        directory=tmp_path,
        now=dt,
    )
    p2 = save_snapshot(
        [_ok("b")],
        label="same",
        mode="both",
        preset="default",
        directory=tmp_path,
        now=dt,
    )

    assert p1 != p2
    assert p1.exists()
    assert p2.exists()
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_list_snapshots_sorted_newest_first(tmp_path: Path):
    save_snapshot(
        [_ok()], label="old", mode="both", preset="default",
        directory=tmp_path,
        now=datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc),
    )
    save_snapshot(
        [_ok()], label="new", mode="both", preset="default",
        directory=tmp_path,
        now=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
    )
    metas = list_snapshots(tmp_path)
    assert [m.label for m in metas] == ["new", "old"]


def test_list_snapshots_returns_empty_when_no_dir(tmp_path: Path):
    assert list_snapshots(tmp_path / "absent") == []


def test_list_skips_corrupt_files(tmp_path: Path):
    (tmp_path / "broken.json").write_text("{{{not json", encoding="utf-8")
    save_snapshot([_ok()], label="ok", mode="both", preset="default", directory=tmp_path)
    metas = list_snapshots(tmp_path)
    assert [m.label for m in metas] == ["ok"]


def test_load_corrupt_returns_none(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    assert load_snapshot(p) is None


def test_load_missing_timestamp_returns_none(tmp_path: Path):
    p = tmp_path / "no-ts.json"
    p.write_text(json.dumps({"label": "x", "results": []}), encoding="utf-8")
    assert load_snapshot(p) is None


def test_load_skips_corrupt_result_entries(tmp_path: Path):
    p = tmp_path / "snap.json"
    payload = {
        "timestamp": "2026-05-18T10:00:00+00:00",
        "label": "x",
        "mode": "both",
        "preset": "default",
        "summary": {"total": 2, "blocked": 0},
        "results": [
            {"name": "good", "url": "https://g/", "verdict": "OK", "confidence": "HIGH"},
            {"name": "broken", "verdict": "NOTAVERDICT", "confidence": "HIGH"},
            "garbage",
        ],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    snap = load_snapshot(p)
    assert snap is not None
    assert [r.name for r in snap.results] == ["good"]


def test_save_does_not_leave_tmp(tmp_path: Path):
    save_snapshot([_ok()], label="x", mode="both", preset="default", directory=tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


def test_diff_classifies_changed_only_old_only_new(tmp_path: Path):
    old_path = save_snapshot(
        [_ok("shared"), _ok("removed"), _blocked("flip", Verdict.OK)],
        label="old", mode="both", preset="default", directory=tmp_path,
        now=datetime(2026, 5, 17, tzinfo=timezone.utc),
    )
    # Перезаписываем 'flip' так, чтобы в старом он был OK.
    # _blocked() выше с Verdict.OK даст OK-результат.
    new_path = save_snapshot(
        [_ok("shared"), _ok("added"), _blocked("flip", Verdict.TLS_BLOCK)],
        label="new", mode="both", preset="default", directory=tmp_path,
        now=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )
    old = load_snapshot(old_path)
    new = load_snapshot(new_path)
    assert old is not None and new is not None
    diff = diff_snapshots(old, new)
    assert [e.name for e in diff.only_old] == ["removed"]
    assert [e.name for e in diff.only_new] == ["added"]
    assert [e.name for e in diff.changed] == ["flip"]
    assert [e.name for e in diff.unchanged] == ["shared"]


def test_snapshots_dir_uses_config_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert snapshots.snapshots_dir() == tmp_path / "xdg" / "rkn-tui" / "snapshots"
