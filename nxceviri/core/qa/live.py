"""Anlık denetim: Çevir tablosunda görünen satırlar için satır başı denetimler ve artımlı tutarlılık denetimi.

`LiveChecker` bir satırı yalnızca görüntülenirken denetler; sonuç satır nesnesi ve bağlam değişene kadar önbellekte
kalır. "Tutarsız çeviri" kaynak metne göre dizinlenir: bir satır değişince yalnızca aynı kaynaklı satırlar yenilenir.
Hangi türlerin çalışacağı `LiveContext.kinds` ile seçilir.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import (
    KIND_LABELS,
    QaIssue,
    check_row,
    consistency_issues,
    glossary_patterns,
    spell_extra_words,
)
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.providers.base import GlossaryTerm

log = logging.getLogger(__name__)

#: Ayarlar'da seçilebilen türler; sıra gösterim sırasıdır (hatalar, uyarılar, bilgi).
LIVE_KINDS: tuple[str, ...] = (
    "placeholder",
    "markup",
    "max_length",
    "code_position",
    "missing_markup",
    "protected",
    "glyph",
    "overflow",
    "newlines",
    "line_too_long",
    "page_too_tall",
    "bad_break",
    "spaces",
    "double_space",
    "repeated_word",
    "extra_dots",
    "end_punctuation",
    "glossary",
    "identifier",
    "suspicious",
    "inconsistent",
    "spelling",
)
DEFAULT_LIVE_KINDS: frozenset[str] = frozenset(LIVE_KINDS)

#: Ayarlar sayfasında her türün altında görünen tek cümlelik ipucu.
KIND_HINTS: dict[str, str] = {
    "placeholder": "Kontrol kodu eksik, fazla ya da yer değiştirmiş.",
    "markup": "Çeviride orijinalde olmayan bir etiket var.",
    "max_length": "Çeviri biçimin koyduğu uzunluk sınırını aşıyor.",
    "code_position": "Satır sonu kodu cümlenin sonuna yığılmış.",
    "missing_markup": "Orijinaldeki ham etiket çeviride yok.",
    "protected": "Çevrilmemesi gereken kod adı çeviride yok.",
    "glyph": "Çeviride fontta olmayabilecek harf var.",
    "overflow": "Çeviri orijinalden belirgin biçimde uzun.",
    "newlines": "Satır sonu sayısı orijinalden farklı.",
    "line_too_long": "Bir satır sığdırma kuralındaki karakter sınırını aşıyor.",
    "page_too_tall": "Bir sayfada izin verilenden çok satır var.",
    "bad_break": "Satır gereksiz kısa kesilmiş.",
    "spaces": "Baştaki ya da sondaki boşluk orijinalle aynı değil.",
    "double_space": "Metnin içinde çift boşluk var.",
    "repeated_word": "Aynı sözcük art arda yazılmış.",
    "extra_dots": "Fazla nokta var.",
    "end_punctuation": "Sona orijinalde olmayan bir noktalama eklenmiş.",
    "glossary": "Terminolojideki terimin karşılığı çeviride yok.",
    "identifier": "Kod adına benzeyen bir metin çevrilmiş.",
    "suspicious": "Çeviri uydurma gibi görünüyor (İngilizce kalmış, tekrar vb.).",
    "inconsistent": "Aynı metin farklı biçimlerde çevrilmiş.",
    "spelling": "Yazım sözlüğünde olmayan sözcük var.",
}

SETTING_KEY = "qa/live_kinds"


def parse_live_kinds(value: object) -> frozenset[str]:
    """Kayıtlı değeri (virgüllü) türlere çevirir. Boş metin "hiçbiri"dir; yok ya da bozuk değer varsayılandır."""
    if value is None:
        return DEFAULT_LIVE_KINDS
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    unknown = [p for p in parts if p not in LIVE_KINDS]
    if unknown:
        log.warning("Bozuk anlık denetim ayarı (%s): varsayılan kullanılıyor.", ", ".join(unknown))
        return DEFAULT_LIVE_KINDS
    return frozenset(parts)


def format_live_kinds(kinds: Collection[str]) -> str:
    """Türleri gösterim sırasıyla virgüllü metne çevirir."""
    return ",".join(k for k in LIVE_KINDS if k in kinds)


@dataclass(frozen=True)
class LiveContext:
    """Satır denetimlerinin bağlamı; değişince önbellek boşalır."""

    missing_letters: str = ""
    transliterated: str = ""
    glossary: tuple[GlossaryTerm, ...] = ()
    fit: FitConfig | None = None
    spell: SpellChecker | None = None
    kinds: frozenset[str] = DEFAULT_LIVE_KINDS
    #: Projede yazım bulgusu üretmeyecek sözcükler (Yazım Denetimi penceresinde "Yoksay").
    spell_ignored: frozenset[str] = frozenset()


class LiveChecker:
    def __init__(self) -> None:
        self._context = LiveContext()
        self._patterns = glossary_patterns([])
        self._extra: frozenset[str] = frozenset()
        self._cache: dict[int, tuple[TranslationRow, list[QaIssue]]] = {}
        self._groups: dict[str, dict[int, TranslationRow]] = {}
        self._group_issues: dict[str, dict[int, QaIssue]] = {}

    def set_context(self, context: LiveContext) -> None:
        self._context = context
        glossary = list(context.glossary)
        self._patterns = glossary_patterns(glossary)
        self._extra = spell_extra_words(glossary, context.spell_ignored) if context.spell is not None else frozenset()
        self._cache.clear()

    def set_rows(self, rows: Sequence[TranslationRow]) -> None:
        self._cache.clear()
        self._group_issues.clear()
        self._groups = {}
        for row in rows:
            if row.source.strip():
                self._groups.setdefault(row.source, {})[row.id] = row

    def update_row(self, row: TranslationRow) -> set[int]:
        """Satırı dizinde günceller; sonucu değişebilecek ÖTEKİ satırların kimliklerini döndürür."""
        if not row.source.strip():
            return set()
        group = self._groups.setdefault(row.source, {})
        group[row.id] = row
        self._group_issues.pop(row.source, None)
        if "inconsistent" not in self._context.kinds:
            return set()
        return {i for i in group if i != row.id}

    def update_rows(self, rows: Sequence[TranslationRow]) -> set[int]:
        """Birçok satırı dizinde günceller; sonucu değişebilecek ÖTEKİ satırların kimliklerini tek seferde döndürür.

        Aynı kaynaklı büyük gruplar ("???", "…") satır satır güncellenirse karesel iş çıkar; burada her grup bir kez
        taranır.
        """
        sources: dict[str, None] = {}
        for row in rows:
            if not row.source.strip():
                continue
            self._groups.setdefault(row.source, {})[row.id] = row
            self._group_issues.pop(row.source, None)
            sources[row.source] = None
        if "inconsistent" not in self._context.kinds:
            return set()
        peers: set[int] = set()
        for source in sources:
            peers.update(self._groups[source])
        return peers - {row.id for row in rows}

    def _inconsistency(self, row: TranslationRow) -> list[QaIssue]:
        group = self._groups.get(row.source)
        if group is None or len(group) < 2 or not row.translation:
            return []
        memo = self._group_issues.get(row.source)
        if memo is None:
            memo = {i.row_id: i for i in consistency_issues(list(group.values()))}
            self._group_issues[row.source] = memo
        found = memo.get(row.id)
        return [] if found is None else [found]

    def check(self, row: TranslationRow) -> list[QaIssue]:
        kinds = self._context.kinds
        cached = self._cache.get(row.id)
        if cached is not None and cached[0] is row:
            base = cached[1]
        else:
            ctx = self._context
            base = [
                i
                for i in check_row(
                    row,
                    ctx.missing_letters,
                    ctx.transliterated,
                    self._patterns,
                    ctx.fit,
                    spell=ctx.spell,
                    spell_extra=self._extra,
                )
                if i.kind in kinds and i.kind in KIND_LABELS and i.kind != "untranslated"
            ]
            self._cache[row.id] = (row, base)
        if "inconsistent" not in kinds:
            return base
        extra = self._inconsistency(row)
        return base + extra if extra else base
