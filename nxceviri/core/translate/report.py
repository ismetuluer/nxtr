"""Çeviri değişikliklerinin adlandırılması ve dışa aktarılması (CSV, renkli HTML)."""

from __future__ import annotations

import csv
import html
import io
import os
from collections.abc import Sequence
from pathlib import Path

from nxceviri.core.errors import NxError
from nxceviri.core.project import JOB_MANUAL, JOB_REVERT, JOB_UNAPPROVE, Change
from nxceviri.core.translate.diff import ADDED, REMOVED, word_diff

_JOB_LABELS = {
    "translate": "Otomatik çeviri",
    "retranslate": "Yeniden çeviri",
    "revise": "Redaksiyon",
    "autofix": "Otomatik düzeltme",
    "reflow": "Satırları yeniden bölme",
    "import": "Hazır çeviri aktarma",
    "replace": "Bul ve değiştir",
    "csv": "Dış redaksiyondan içe aktarma",
    "translation": "Dış çeviriden içe aktarma",
    JOB_MANUAL: "Elle düzenleme",
    JOB_REVERT: "Geri alma",
    JOB_UNAPPROVE: "Onay kaldırma",
}

#: Durum sütununda işaretlenen iş türleri ve kısa adları.
_MARK_LABELS = {
    "revise": "redaksiyon",
    "autofix": "otomatik düzeltme",
    "retranslate": "yeniden çeviri",
    "translation": "dış çeviri",
}


def _kind(job: str) -> str:
    return job if job in _JOB_LABELS else job.split("-", 1)[0]


def job_label(job: str) -> str:
    """İş kimliğinin ("revise-2026-10-25T09:30:12") okunur adı."""
    return _JOB_LABELS.get(_kind(job), job)


def mark_label(job: str) -> str:
    """Satırın son değişikliği bu işle yapıldıysa durum sütununda gösterilecek kısa ad; yoksa ""."""
    return _MARK_LABELS.get(_kind(job), "")


class ReportError(NxError):
    """Değişiklik raporu yazılamadı."""


def changes_csv(changes: Sequence[Change]) -> str:
    """Excel'in Türkçe ayarlarında doğrudan açılan CSV (noktalı virgül ayraçlı)."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Satır", "Orijinal", "Önceki çeviri", "Yeni çeviri", "İş", "Zaman"])
    for c in changes:
        writer.writerow([c.label, c.source, c.old_text, c.new_text, job_label(c.job), c.created_at])
    return out.getvalue()


def _render(parts: list[tuple[str, str]]) -> str:
    out = []
    for kind, text in parts:
        body = html.escape(text).replace("\n", "<br>")
        if kind == REMOVED:
            out.append(f"<del>{body}</del>")
        elif kind == ADDED:
            out.append(f"<ins>{body}</ins>")
        else:
            out.append(body)
    return "".join(out)


def changes_html(changes: Sequence[Change], title: str) -> str:
    """Tarayıcıda açılan, farkları renkli gösteren bağımsız sayfa."""
    rows = []
    for c in changes:
        old, new = word_diff(c.old_text, c.new_text)
        rows.append(
            "<tr>"
            f"<td>{html.escape(c.label)}</td><td>{html.escape(c.source).replace(chr(10), '<br>')}</td>"
            f"<td>{_render(old)}</td><td>{_render(new)}</td><td>{html.escape(job_label(c.job))}</td>"
            "</tr>"
        )
    return (
        "<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>"
        "body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1f2328}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #d0d7de;padding:6px 8px;"
        "vertical-align:top;text-align:left}th{background:#f6f8fa}"
        "del{background:#ffebe9;color:#b42318}ins{background:#dafbe1;color:#1a7f37;text-decoration:none;"
        "font-weight:600}"
        "</style></head><body>"
        f"<h1>{html.escape(title)}</h1><p>{len(changes)} değişiklik. Kırmızı ve üstü çizili: çıkarılan; "
        "yeşil: eklenen.</p>"
        "<table><tr><th>Satır</th><th>Orijinal</th><th>Önceki çeviri</th><th>Yeni çeviri</th><th>İş</th></tr>"
        + "".join(rows)
        + "</table></body></html>"
    )


def write_changes(path: Path, changes: Sequence[Change], title: str) -> None:
    """Değişiklikleri uzantıya göre CSV veya HTML olarak atomik yazar."""
    if path.suffix.lower() in (".html", ".htm"):
        data = changes_html(changes, title).encode("utf-8")
    else:
        data = "﻿".encode() + changes_csv(changes).encode("utf-8")  # BOM: Excel UTF-8'i tanısın
    tmp = path.with_name(path.name + ".yaziliyor")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise ReportError(
            f"Rapor kaydedilemedi: {path}", f"Klasöre yazma izniniz olduğundan emin olun. ({exc})"
        ) from None
