"""Локальные снапшоты результатов сканирования.

Один JSON-файл на снапшот в `~/.config/rkn-tui/snapshots/`. Имя файла —
`{timestamp}-{slug}.json`. timestamp ISO-8601 без двоеточий (чтобы
дружелюбно к FS), slug — slugified label.

Принципы:
  - Атомарная запись через `.tmp` + os.replace (как в storage).
  - Все ошибки чтения отдельного файла приводят к его пропуску, не к
    падению `list_snapshots`. Лучше показать неполный список, чем экран
    «Ошибка».
  - Метаданные минимальны: дата, режим, пресет, label, контекст сети,
    self_info. Этого хватает для history-listing без чтения тяжелой
    части (results).
  - CheckResult сериализуется через `dataclasses.asdict`, верифицируется
    набором известных полей. При загрузке пропускаем кривые записи.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from rkn_checker.models import CheckResult, Confidence, Verdict

from . import engine
from .storage import config_dir

SNAPSHOT_DIR_NAME = "snapshots"


@dataclass
class SnapshotMeta:
    """Шапка снапшота — то, что нужно для списка в HistoryScreen."""

    path: Path
    timestamp: datetime
    label: str
    mode: str
    preset: str
    context_status: str
    total: int
    blocked: int

    @property
    def display_date(self) -> str:
        """Локальное время для UI: YYYY-MM-DD HH:MM."""
        return self.timestamp.astimezone().strftime("%Y-%m-%d %H:%M")


@dataclass
class Snapshot:
    """Полное содержимое снапшота: метаданные + результаты."""

    meta: SnapshotMeta
    self_info: dict
    results: list[CheckResult]
    diagnostics: dict = field(default_factory=dict)
    context_detail: str = ""
    context_headline: str = ""


def snapshots_dir() -> Path:
    return config_dir() / SNAPSHOT_DIR_NAME


def _slugify(label: str) -> str:
    """Сделать из произвольной строки кусок имени файла.

    Кириллица транслитерируется через NFKD (отбрасываются комбинированные
    знаки), всё неалфавитно-цифровое → дефис. Пустой результат → 'snap'.
    """
    if not label:
        return "snap"
    norm = unicodedata.normalize("NFKD", label)
    cleaned = re.sub(r"[^\w\-]+", "-", norm, flags=re.UNICODE).strip("-_")
    if not cleaned:
        return "snap"
    return cleaned[:40].lower()


def _timestamp_for_filename(dt: datetime) -> str:
    """ISO с заменой двоеточий на дефисы — FS-safe."""
    return dt.strftime("%Y%m%dT%H%M%S")


def save_snapshot(
    results: Iterable[CheckResult],
    *,
    label: str,
    mode: str,
    preset: str,
    self_info: Optional[dict] = None,
    context_status: str = "",
    context_headline: str = "",
    context_detail: str = "",
    diagnostics: Optional[dict] = None,
    directory: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Path:
    """Сохранить снапшот и вернуть путь к созданному JSON.

    `now` и `directory` параметризованы под тесты — в проде они дефолтные.
    """
    results_list = list(results)
    dt = now or datetime.now(timezone.utc)
    dir_ = directory or snapshots_dir()
    dir_.mkdir(parents=True, exist_ok=True)

    slug = _slugify(label)
    filename = f"{_timestamp_for_filename(dt)}-{slug}.json"
    path = _unique_snapshot_path(dir_, filename)

    payload = {
        "version": 1,
        "timestamp": dt.isoformat(),
        "label": label,
        "mode": mode,
        "preset": preset,
        "context_status": context_status,
        "context_headline": context_headline,
        "context_detail": context_detail,
        "self_info": self_info or {},
        "diagnostics": diagnostics or {},
        "summary": {
            "total": len(results_list),
            "blocked": sum(1 for r in results_list if engine.is_blocked(r)),
        },
        "results": [_serialize_result(r) for r in results_list],
    }

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _unique_snapshot_path(directory: Path, filename: str) -> Path:
    """Return a non-existing path, adding -2/-3 when timestamp+slug collides."""
    path = directory / filename
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = directory / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def list_snapshots(directory: Optional[Path] = None) -> list[SnapshotMeta]:
    """Вернуть метаданные снапшотов отсортированными от свежих к старым.

    Кривые JSON-файлы молча пропускаются. Если директории нет — пустой
    список.
    """
    dir_ = directory or snapshots_dir()
    if not dir_.exists():
        return []
    metas: list[SnapshotMeta] = []
    for path in sorted(dir_.glob("*.json")):
        meta = _read_meta(path)
        if meta is not None:
            metas.append(meta)
    metas.sort(key=lambda m: m.timestamp, reverse=True)
    return metas


def load_snapshot(path: Path) -> Optional[Snapshot]:
    """Прочитать полный снапшот. None — если файл сломан."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    meta = _meta_from_raw(path, raw)
    if meta is None:
        return None
    results = []
    for item in raw.get("results", []) or []:
        result = _deserialize_result(item)
        if result is not None:
            results.append(result)
    return Snapshot(
        meta=meta,
        self_info=raw.get("self_info") or {},
        results=results,
        diagnostics=raw.get("diagnostics") if isinstance(raw.get("diagnostics"), dict) else {},
        context_detail=str(raw.get("context_detail") or ""),
        context_headline=str(raw.get("context_headline") or ""),
    )


def delete_snapshot(path: Path) -> bool:
    """Удалить снапшот. True если файл существовал."""
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def _read_meta(path: Path) -> Optional[SnapshotMeta]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return _meta_from_raw(path, raw)


def _meta_from_raw(path: Path, raw: dict) -> Optional[SnapshotMeta]:
    try:
        ts = datetime.fromisoformat(str(raw["timestamp"]))
    except (KeyError, ValueError, TypeError):
        return None
    summary = raw.get("summary") or {}
    return SnapshotMeta(
        path=path,
        timestamp=ts,
        label=str(raw.get("label") or ""),
        mode=str(raw.get("mode") or ""),
        preset=str(raw.get("preset") or ""),
        context_status=str(raw.get("context_status") or ""),
        total=_safe_int(summary.get("total")),
        blocked=_safe_int(summary.get("blocked")),
    )


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _serialize_result(r: CheckResult) -> dict:
    """asdict, но энумы → имена для стабильного парсинга."""
    data = asdict(r)
    data["verdict"] = r.verdict.name
    data["confidence"] = r.confidence.name
    return data


def _deserialize_result(item: object) -> Optional[CheckResult]:
    """Аккуратно собрать CheckResult из dict; на любой кривизне → None."""
    if not isinstance(item, dict):
        return None
    try:
        verdict = Verdict[item["verdict"]]
        confidence = Confidence[item["confidence"]]
    except (KeyError, TypeError):
        return None
    kwargs = {
        "name": str(item.get("name", "")),
        "url": str(item.get("url", "")),
        "verdict": verdict,
        "confidence": confidence,
    }
    optional_fields = (
        "notes", "sys_ip", "doh_ip", "sys_ips", "doh_ips",
        "dns_mismatch", "dns_error", "tcp_ok", "tcp_time_ms", "tcp_error",
        "tls_ok", "tls_time_ms", "tls_cert_cn", "tls_error",
        "status_code", "plt_ms", "http_error",
    )
    for f in optional_fields:
        if f in item:
            kwargs[f] = item[f]
    try:
        return CheckResult(**kwargs)
    except TypeError:
        return None


@dataclass(frozen=True)
class DiffEntry:
    """Одна строка в diff: имя сайта, было/стало."""

    name: str
    url: str
    old: Optional[CheckResult]
    new: Optional[CheckResult]


@dataclass
class SnapshotDiff:
    """Three-way разделение результатов двух снапшотов."""

    only_old: list[DiffEntry] = field(default_factory=list)
    changed: list[DiffEntry] = field(default_factory=list)
    only_new: list[DiffEntry] = field(default_factory=list)
    unchanged: list[DiffEntry] = field(default_factory=list)


def diff_snapshots(old: Snapshot, new: Snapshot) -> SnapshotDiff:
    """Сравнить два снапшота по name+url.

    Ключ — пара (name, url), потому что один и тот же сайт может попасть
    под разные имена в whitelist/blacklist. Сравниваем именно вердикт и
    confidence — это то, что меняется между сканами.
    """
    old_index = {(r.name, r.url): r for r in old.results}
    new_index = {(r.name, r.url): r for r in new.results}
    result = SnapshotDiff()

    for key, old_r in old_index.items():
        new_r = new_index.get(key)
        if new_r is None:
            result.only_old.append(DiffEntry(key[0], key[1], old_r, None))
        elif old_r.verdict != new_r.verdict:
            result.changed.append(DiffEntry(key[0], key[1], old_r, new_r))
        else:
            result.unchanged.append(DiffEntry(key[0], key[1], old_r, new_r))

    for key, new_r in new_index.items():
        if key not in old_index:
            result.only_new.append(DiffEntry(key[0], key[1], None, new_r))

    result.only_old.sort(key=lambda e: e.name)
    result.changed.sort(key=lambda e: e.name)
    result.only_new.sort(key=lambda e: e.name)
    return result
