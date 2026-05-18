"""Модальный экран с разбором одного вердикта.

Открывается из ResultsScreen по Enter на строке. Показывает:
  * человеческое описание из verdicts.info (what / why)
  * confidence + подсказку откуда уверенность
  * raw-поля CheckResult (DNS, TCP, TLS, HTTP) — для тех кто умеет читать

Закрывается по Esc или Enter.
"""
from __future__ import annotations

from rkn_checker.models import CheckResult
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .. import verdicts


class VerdictDetailScreen(ModalScreen):
    """Модалка поверх результатов с подробным разбором одной строки."""

    BINDINGS = [
        ("escape", "close", "Закрыть"),
        ("enter", "close", "Закрыть"),
    ]

    def __init__(self, result: CheckResult) -> None:
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        info = verdicts.info(self.result.verdict)
        with Container(id="detail-dialog"):
            with VerticalScroll(id="detail-body"):
                yield Static(self.result.name, id="detail-title")
                yield Static(self.result.url, id="detail-url")
                yield Static(f"Вердикт: {info.short}", id="detail-verdict")
                yield Static(info.what, id="detail-what")
                yield Static(info.why, id="detail-why", classes="muted")
                yield Static(
                    f"Уверенность: {verdicts.confidence_label(self.result.confidence)}",
                    id="detail-conf",
                )
                yield Static(
                    verdicts.confidence_hint(self.result.confidence),
                    id="detail-conf-hint",
                    classes="muted",
                )
                yield Static("Сырые данные пробы", id="detail-raw-title")
                yield Static(self._raw_block(), id="detail-raw")
            yield Button("Закрыть (Esc / Enter)", id="detail-close", variant="primary")

    def _raw_block(self) -> str:
        r = self.result
        lines: list[str] = []

        if r.sys_ips or r.doh_ips:
            sys_ips = ", ".join(r.sys_ips) if r.sys_ips else "—"
            doh_ips = ", ".join(r.doh_ips) if r.doh_ips else "—"
            mismatch = "да" if r.dns_mismatch else "нет"
            lines.append(f"DNS · sys: {sys_ips} · DoH: {doh_ips} · подмена: {mismatch}")
        if r.dns_error:
            lines.append(f"DNS error: {r.dns_error}")

        tcp_parts: list[str] = []
        if r.tcp_ok is not None:
            tcp_parts.append("ok" if r.tcp_ok else "fail")
        if r.tcp_time_ms is not None:
            tcp_parts.append(f"{r.tcp_time_ms:.0f}ms")
        if r.tcp_error:
            tcp_parts.append(r.tcp_error)
        if tcp_parts:
            lines.append("TCP · " + " · ".join(tcp_parts))

        tls_parts: list[str] = []
        if r.tls_ok is not None:
            tls_parts.append("ok" if r.tls_ok else "fail")
        if r.tls_time_ms is not None:
            tls_parts.append(f"{r.tls_time_ms:.0f}ms")
        if r.tls_cert_cn:
            tls_parts.append(f"cert CN={r.tls_cert_cn}")
        if r.tls_error:
            tls_parts.append(r.tls_error)
        if tls_parts:
            lines.append("TLS · " + " · ".join(tls_parts))

        http_parts: list[str] = []
        if r.status_code is not None:
            http_parts.append(f"status {r.status_code}")
        if r.plt_ms is not None:
            http_parts.append(f"plt {r.plt_ms:.0f}ms")
        if r.http_error:
            http_parts.append(r.http_error)
        if http_parts:
            lines.append("HTTP · " + " · ".join(http_parts))

        if r.notes:
            lines.append("Заметки: " + "; ".join(r.notes))

        return "\n".join(lines) if lines else "Нет дополнительных данных."

    def action_close(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "detail-close":
            self.action_close()
