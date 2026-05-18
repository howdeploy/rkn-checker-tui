"""Тесты на history/diff: чистые функции форматирования и интеграция с FS.

run_test() для Textual здесь не используется — достаточно дернуть
функции и dataclass'ы напрямую.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rkn_checker.models import CheckResult, Confidence, Verdict

from rkn_tui import snapshots
from rkn_tui.snapshots import diff_snapshots, list_snapshots, load_snapshot, save_snapshot


def _r(name: str, verdict: Verdict = Verdict.OK) -> CheckResult:
    return CheckResult(
        name=name,
        url=f"https://{name}/",
        verdict=verdict,
        confidence=Confidence.HIGH,
    )


def test_full_roundtrip_via_xdg(monkeypatch, tmp_path: Path):
    """Сохранить через storage-конфиг, увидеть в list_snapshots, открыть."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_snapshot(
        [_r("ok"), _r("blk", Verdict.TLS_BLOCK)],
        label="первый",
        mode="both",
        preset="default",
    )
    metas = list_snapshots()
    assert len(metas) == 1
    assert metas[0].label == "первый"
    assert metas[0].blocked == 1
    snap = load_snapshot(metas[0].path)
    assert snap is not None
    assert {r.name for r in snap.results} == {"ok", "blk"}


def test_history_format_meta_line():
    from rkn_tui.screens.history import _format_meta_line
    from rkn_tui.snapshots import SnapshotMeta

    meta = SnapshotMeta(
        path=Path("/tmp/snap.json"),
        timestamp=datetime(2026, 5, 18, 12, 30, tzinfo=timezone.utc),
        label="до апдейта",
        mode="both",
        preset="default",
        context_status="filtered",
        total=12,
        blocked=3,
    )
    line = _format_meta_line(meta)
    assert "до апдейта" in line
    assert "12 проверок" in line
    assert "3 подозрительных" in line
    assert "filtered" not in line  # переведено в эмодзи
    assert "🟡" in line


def test_diff_direction_marker_regression_and_recovery():
    from rkn_tui.screens.diff import _direction_marker

    ok_then_blocked = _direction_marker(_r("x"), _r("x", Verdict.TLS_BLOCK))
    assert "заблокирован" in ok_then_blocked

    blocked_then_ok = _direction_marker(_r("x", Verdict.TLS_BLOCK), _r("x"))
    assert "починился" in blocked_then_ok

    blocked_to_blocked = _direction_marker(
        _r("x", Verdict.TLS_BLOCK), _r("x", Verdict.DNS_BLOCK)
    )
    assert "другой" in blocked_to_blocked


def test_diff_changed_classification(tmp_path: Path):
    old_path = save_snapshot(
        [_r("stays"), _r("flip", Verdict.OK), _r("gone")],
        label="o", mode="both", preset="default", directory=tmp_path,
        now=datetime(2026, 5, 17, tzinfo=timezone.utc),
    )
    new_path = save_snapshot(
        [_r("stays"), _r("flip", Verdict.TLS_BLOCK), _r("added")],
        label="n", mode="both", preset="default", directory=tmp_path,
        now=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )
    old = load_snapshot(old_path)
    new = load_snapshot(new_path)
    assert old is not None and new is not None
    d = diff_snapshots(old, new)
    assert [e.name for e in d.changed] == ["flip"]
    assert [e.name for e in d.only_old] == ["gone"]
    assert [e.name for e in d.only_new] == ["added"]
    assert [e.name for e in d.unchanged] == ["stays"]


def test_save_snapshot_default_dir_uses_config(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = save_snapshot([_r("x")], label="t", mode="both", preset="default")
    expected_dir = tmp_path / "rkn-tui" / "snapshots"
    assert path.parent == expected_dir
    assert snapshots.snapshots_dir() == expected_dir


def test_delete_snapshot_removes_file(tmp_path: Path):
    path = save_snapshot([_r("x")], label="kill-me", mode="both", preset="default", directory=tmp_path)
    assert path.exists()
    assert snapshots.delete_snapshot(path) is True
    assert not path.exists()
    assert snapshots.delete_snapshot(path) is False
