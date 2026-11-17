"""Kontrol Et'te "yok sayılan" bulgular: hata olmayan bir bulguyu kullanıcı listeden çıkarır.

Yok sayma kalıcıdır ve proje ayarında saklanır: her kayıt (satır kimliği, tür, çevirinin özeti). Çeviri değişirse
özet tutmaz ve bulgu yeniden görünür; yani yok sayma yalnızca o an gördüğünüz metin içindir. Hata (oyunu bozabilecek)
bulgular yok sayılamaz. Yok sayılan bulgu dışa aktarmayı engellemez: uyarılar zaten engellemez.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Collection, Iterable, Mapping

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import SEVERITY_ERROR, QaIssue

log = logging.getLogger(__name__)

#: Proje ayarındaki anahtar (JSON: [[satır kimliği, tür, özet], …]).
IGNORED_KEY = "qa/ignored_issues"

Entry = tuple[int, str, str]


def digest(translation: str) -> str:
    """Çevirinin kısa özeti: metin değişince yok sayma geçersiz olur."""
    return hashlib.sha1(translation.encode("utf-8")).hexdigest()[:12]


def load(raw: str) -> set[Entry]:
    """Ayardan kayıtları okur; bozuk ayar yok sayılır (günlüğe uyarı) ve hiçbir bulgu gizlenmez."""
    if not raw:
        return set()
    try:
        data = json.loads(raw)
        return {(int(a), str(b), str(c)) for a, b, c in data}
    except (ValueError, TypeError) as exc:
        log.warning("Yok sayılan bulgular okunamadı (%s): %s", IGNORED_KEY, exc)
        return set()


def dump(entries: Iterable[Entry]) -> str:
    return json.dumps(sorted(entries), ensure_ascii=False)


def split(
    issues: Iterable[QaIssue], rows: Mapping[int, TranslationRow], entries: Collection[Entry]
) -> tuple[list[QaIssue], list[QaIssue]]:
    """Bulguları (gösterilecekler, yok sayılanlar) diye ayırır; hata bulguları asla yok sayılmaz."""
    shown: list[QaIssue] = []
    hidden: list[QaIssue] = []
    if not entries:
        return list(issues), hidden
    for issue in issues:
        row = rows.get(issue.row_id)
        if (
            issue.severity != SEVERITY_ERROR
            and row is not None
            and (issue.row_id, issue.kind, digest(row.translation)) in entries
        ):
            hidden.append(issue)
        else:
            shown.append(issue)
    return shown, hidden


def add(entries: set[Entry], pairs: Iterable[tuple[int, str]], rows: Mapping[int, TranslationRow]) -> set[Entry]:
    """Kayıtlara (satır, tür) çiftlerini ekler; çevirisi değişmiş ya da silinmiş satırların eski kayıtları atılır."""
    kept = {e for e in entries if e[0] in rows and digest(rows[e[0]].translation) == e[2]}
    kept.update((row_id, kind, digest(rows[row_id].translation)) for row_id, kind in pairs if row_id in rows)
    return kept


def remove(entries: set[Entry], pairs: Collection[tuple[int, str]]) -> set[Entry]:
    """Kayıtlardan (satır, tür) çiftlerini çıkarır (yok saymayı kaldırır)."""
    return {e for e in entries if (e[0], e[1]) not in pairs}
