"""Çevirilerde bul ve değiştir.

Yalnızca çeviri metni değişir (özgün metin ve anahtarlar değil). Değişiklik kontrol kodlarını bozacaksa
(ör. aranan metin `⟦1⟧`'in bir parçası) o satır değiştirilmez ve atlananlar sayılır.

Aranan metin düz metin olarak (varsayılan) veya düzenli ifade (regex) olarak yorumlanabilir. Düzenli
ifadede değiştirme metni Python kurallarıyla grup başvuruları içerebilir (`\\1`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate import placeholders


@dataclass
class ReplacePlan:
    changes: list[tuple[int, str]] = field(default_factory=list)  # (satır kimliği, yeni çeviri)
    matches: int = 0  # toplam eşleşme sayısı (değiştirilecek satırlarda)
    skipped: int = 0  # kontrol kodunu bozacağı için atlanan satır sayısı
    error: str = ""  # düzenli ifade geçersizse kullanıcıya gösterilecek metin


def find_pattern(
    text: str, *, case: bool = False, whole_word: bool = False, regex: bool = False
) -> re.Pattern[str] | None:
    """Aranan metnin kalıbı; boş metinde None.

    `regex` kapalıyken metin olduğu gibi aranır; açıkken düzenli ifade olarak derlenir ve geçersiz
    ifadede `re.error` yükselir.
    """
    if not text:
        return None
    body = text if regex else re.escape(text)
    if whole_word:
        body = rf"(?<!\w)(?:{body})(?!\w)"
    return re.compile(body, 0 if case else re.IGNORECASE)


def plan_replace(
    rows: Sequence[TranslationRow],
    find: str,
    replacement: str,
    *,
    case: bool = False,
    whole_word: bool = False,
    regex: bool = False,
) -> ReplacePlan:
    """Değiştirilecek satırları hesaplar (projeye yazmaz)."""
    plan = ReplacePlan()
    try:
        pattern = find_pattern(find, case=case, whole_word=whole_word, regex=regex)
    except re.error as exc:
        plan.error = f"Düzenli ifade geçersiz: {exc}"
        return plan
    if pattern is None:
        return plan
    # Düz metinde yerine yazılan metin olduğu gibi kalır; düzenli ifadede `\1` gibi grup başvuruları çalışır.
    repl: str | Callable[[re.Match[str]], str]
    repl = replacement if regex else (lambda _m, _r=replacement: _r)
    for r in rows:
        if not r.translation:
            continue
        new, count = pattern.subn(repl, r.translation)
        if not count or new == r.translation:
            continue
        if placeholders.problems(r.source, new) and not placeholders.problems(r.source, r.translation):
            plan.skipped += 1
            continue
        plan.changes.append((r.id, new))
        plan.matches += count
    return plan
