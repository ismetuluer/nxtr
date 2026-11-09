"""Çeviri kalite denetimleri (QA).

Denetimler satır başınadır ve yalnızca bulguları döndürür; satırları değiştirmez.

| Tür | Önem | Ne zaman |
|---|---|---|
| placeholder | hata | Kontrol kodları bozuk (satır "Hatalı"; dışa aktarılmaz) |
| max_length | hata | Biçimin koyduğu uzunluk sınırı aşılmış |
| glyph | uyarı | Çeviride fontta olmayan ve dönüştürülmeyecek harf var |
| overflow | uyarı | Çeviri orijinalden belirgin biçimde uzun (kutuya sığmayabilir) |
| newlines | uyarı | Satır sonu sayısı orijinalden farklı |
| line_too_long | uyarı | Bir satır, sığdırma kuralındaki karakter sınırını aşıyor |
| page_too_tall | uyarı | Bir sayfada sığdırma kuralındaki satır sayısından fazla satır var |
| bad_break | uyarı | Satır gereksiz kısa kesilmiş; sonraki sözcük sığardı |
| spaces | uyarı | Baştaki/sondaki boşluklar orijinalle aynı değil |
| glossary | uyarı | Sözlükteki terim kaynakta geçiyor ama Türkçe karşılığı çeviride yok |
| identifier | uyarı | Kaynak bir kod adına benziyor (Ad_Soyad_1) ve çevrilmiş; oyun bu adı arayabilir |
| suspicious | uyarı | Uydurma belirtisi: İngilizce kalmış, yabancı alfabe, tekrar döngüsü, orijinalden çok uzun/kısa |
| end_punctuation | uyarı | Çevirinin sonuna orijinalde olmayan noktalama eklenmiş (otomatik düzeltmede atılır) |
| spelling | bilgi | Çeviride Türkçe yazım sözlüğünde olmayan sözcük var (süzgeçle görülür; sözlüğe eklenebilir) |
| missing_markup | uyarı | Orijinaldeki ham etiket (`<i>`, `[color=..]`, `{ad}`) çeviride eksik |
| protected | uyarı | Orijinal cümlenin içindeki kod adı (`Barrel_Cannon`) çeviride aynen yok |
| double_space | uyarı | Metnin içinde çift/çoklu boşluk (otomatik düzeltilir) |
| repeated_word | uyarı | Art arda aynı sözcük, "ve ve" (otomatik düzeltilir) |
| extra_dots | uyarı | 4+ nokta veya orijinalde olmayan ".." (otomatik düzeltilir) |
| inconsistent | uyarı | Aynı kaynak metin projede farklı biçimlerde çevrilmiş (hepsi onaylı değilse) |
| term | uyarı | Kaynakta geçen terimin (özel ad) kanonik çevirisi çeviride yok; projede farklı çevrilmiş |
| untranslated | bilgi | Çevrilmemiş satır (oyunda orijinal metin kalır) |
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Collection
from dataclasses import dataclass

from nxceviri.core.project import TranslationRow
from nxceviri.core.spell.checker import SpellChecker, turkish_lower, words_of
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.cleanup import (
    added_end_punctuation,
    collapse_inner_spaces,
    drop_repeated_words,
    fix_extra_dots,
    foreign_markup,
    misplaced_breaks,
    missing_markup,
    missing_protected,
)
from nxceviri.core.translate.fit import PROBLEM_BREAK, PROBLEM_LINE, PROBLEM_PAGE, find_problems
from nxceviri.core.translate.fitconfig import FitConfig, FitOptions
from nxceviri.core.translate.guards import translation_problems
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import Status

log = logging.getLogger(__name__)

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

SEVERITY_LABELS = {SEVERITY_ERROR: "Hata", SEVERITY_WARNING: "Uyarı", SEVERITY_INFO: "Bilgi"}

KIND_LABELS = {
    "placeholder": "Kontrol kodu",
    "max_length": "Uzunluk sınırı",
    "glyph": "Eksik harf",
    "overflow": "Olası taşma",
    "newlines": "Satır sonu",
    "markup": "Fazla etiket",
    "code_position": "Kod yeri",
    "spaces": "Boşluk",
    "glossary": "Sözlük",
    "identifier": "Kod adı",
    "untranslated": "Çevrilmedi",
    "line_too_long": "Satır uzun",
    "page_too_tall": "Sayfa uzun",
    "bad_break": "Kötü bölünme",
    "suspicious": "Şüpheli çeviri",
    "spelling": "Yazım",
    "end_punctuation": "Sondaki noktalama",
    "inconsistent": "Tutarsız çeviri",
    "missing_markup": "Eksik etiket",
    "protected": "Korunan ifade",
    "double_space": "Çift boşluk",
    "repeated_word": "Tekrarlı sözcük",
    "extra_dots": "Fazla nokta",
    "term": "Terim tutarsızlığı",
}

#: Çeviri orijinalin bu katından uzunsa (ve yeterince uzunsa) taşma uyarısı verilir.
OVERFLOW_RATIO = 1.6
OVERFLOW_MIN_CHARS = 25


@dataclass(frozen=True)
class QaIssue:
    row_id: int
    key: str
    kind: str
    severity: str
    message: str
    #: Yazım bulgusunda sözlükte olmayan sözcükler ("Sözlüğe ekle" bunları kullanır).
    words: tuple[str, ...] = ()


#: "Motel_Interior_TopFloor", "Misc_Church_Medallion" gibi, boşluksuz ve alt çizgili kod adları.
_IDENTIFIER = re.compile(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+")


def _visible(text: str) -> str:
    return placeholders.TOKEN_RE.sub("", text)


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)


def check_row(
    row: TranslationRow,
    missing_letters: str,
    transliterated: str,
    glossary: list[tuple[GlossaryTerm, re.Pattern[str]]] | None = None,
    fit: FitConfig | None = None,
    *,
    spell: SpellChecker | None = None,
    spell_extra: frozenset[str] = frozenset(),
) -> list[QaIssue]:
    """Tek bir satırı denetler. `transliterated`: dışa aktarırken dönüştürülecek harfler.

    `spell` verilirse çevirideki sözlükte olmayan sözcükler de bildirilir; `spell_extra` ek kabul edilen sözcüklerdir
    (ör. oyun sözlüğündeki terimler).
    """
    issues: list[QaIssue] = []

    def add(kind: str, severity: str, message: str, words: tuple[str, ...] = ()) -> None:
        issues.append(QaIssue(row.id, row.context or row.key, kind, severity, message, words))

    if not row.source.strip():
        return issues
    if not row.translation:
        add("untranslated", SEVERITY_INFO, "Çevrilmedi; oyunda orijinal metin görünür.")
        return issues
    problems = placeholders.problems(row.source, row.translation)
    if problems or row.status == Status.ERROR:
        add("placeholder", SEVERITY_ERROR, row.note or " ".join(problems))
    extra = foreign_markup(row.source, row.translation)
    if extra:
        add(
            "markup",
            SEVERITY_ERROR,
            f"Orijinalde olmayan etiket: {' '.join(extra[:4])}. Oyunda yazı olarak görünebilir.",
        )
    if not problems and misplaced_breaks(row.source, row.translation, row.code_labels):
        add(
            "code_position",
            SEVERITY_WARNING,
            "Satır sonu kodu en sona konmuş; orijinaldeki gibi cümlenin ortasına konmalı.",
        )
    shown = _visible(row.translation)
    if row.max_length is not None and len(shown) > row.max_length:
        add("max_length", SEVERITY_ERROR, f"{len(shown)} karakter; sınır {row.max_length}.")
    unhandled = sorted({c for c in shown if c in missing_letters and c not in transliterated})
    if unhandled:
        add(
            "glyph",
            SEVERITY_WARNING,
            f"Fontta olmayabilecek harf: {' '.join(unhandled)}. Dışa aktarırken harf dönüştürmeyi seçebilirsiniz.",
        )
    src_len = len(_visible(row.source))
    if src_len >= OVERFLOW_MIN_CHARS and len(shown) > src_len * OVERFLOW_RATIO:
        add("overflow", SEVERITY_WARNING, f"Çeviri orijinalden %{round(len(shown) * 100 / src_len) - 100} uzun.")
    rules = fit.rules_for_row(row) if fit is not None else None
    if fit is not None and rules is not None:
        for p in find_problems(row.translation, fit.kind_of_row(row), rules, row.source):
            if p.kind == PROBLEM_LINE:
                msg = f"{p.page}. sayfa, {p.line}. satır {p.measured} karakter; sınır {rules.width}."
            elif p.kind == PROBLEM_PAGE:
                msg = f"{p.page}. sayfada {p.measured} satır var; sınır {rules.max_lines}."
            elif p.kind == PROBLEM_BREAK:
                msg = f"{p.page}. sayfa, {p.line}. satır gereksiz kısa kesilmiş; sonraki sözcük sığardı."
            else:
                continue
            add(p.kind, SEVERITY_WARNING, msg)
    elif row.source.count("\n") != row.translation.count("\n"):
        add(
            "newlines",
            SEVERITY_WARNING,
            f"Orijinalde {row.source.count(chr(10))}, çeviride {row.translation.count(chr(10))} satır sonu var.",
        )
    for term, pattern in glossary or ():
        if pattern.search(row.source) and term.translation.casefold() not in row.translation.casefold():
            add("glossary", SEVERITY_WARNING, f"Sözlükte “{term.term}” → “{term.translation}” var; çeviride yok.")
    if _IDENTIFIER.fullmatch(row.source.strip()) and row.translation.strip() != row.source.strip():
        add(
            "identifier",
            SEVERITY_WARNING,
            "Kaynak bir kod adına benziyor; oyun bu adı arıyorsa çeviri sorun çıkarabilir. "
            "Emin değilseniz çeviri ekranındaki sağ tık → “Orijinali çeviri olarak yaz” ile geri alın.",
        )
    lost = missing_markup(row.source, row.translation)
    if lost:
        add("missing_markup", SEVERITY_WARNING, f"Orijinaldeki etiket çeviride eksik: {' '.join(lost[:4])}.")
    kept = missing_protected(row.source, row.translation)
    if kept:
        add(
            "protected",
            SEVERITY_WARNING,
            f"Çevrilmemesi gereken ifade çeviride yok: {', '.join(kept[:4])}. Oyun bu adı arayabilir.",
        )
    options = fit.options if fit is not None else FitOptions()
    if options.spaces and collapse_inner_spaces(row.source, row.translation) != row.translation:
        add("double_space", SEVERITY_WARNING, "Metnin içinde çift boşluk var.")
    if drop_repeated_words(row.source, row.translation) != row.translation:
        add("repeated_word", SEVERITY_WARNING, "Aynı sözcük art arda iki kez yazılmış.")
    if options.repeated_punct and fix_extra_dots(row.source, row.translation) != row.translation:
        add("extra_dots", SEVERITY_WARNING, "Fazla nokta var (üç nokta olmalı).")
    end = added_end_punctuation(row.source, row.translation)
    if end:
        add("end_punctuation", SEVERITY_WARNING, f"Sonda orijinalde olmayan noktalama var: “{end}”")
    if spell is not None and row.translation.strip() != row.source.strip():
        unknown = spell.unknown_words(row.translation, row.source, spell_extra)
        if unknown:
            add("spelling", SEVERITY_INFO, f"Sözlükte olmayan sözcükler: {', '.join(unknown)}", tuple(unknown))
    if not problems and row.translation.strip() != row.source.strip():
        doubts = translation_problems(row.source, row.translation, "tr")
        if doubts:
            add("suspicious", SEVERITY_WARNING, " ".join(doubts))
    if (row.source[:1].isspace(), row.source[-1:].isspace()) != (
        row.translation[:1].isspace(),
        row.translation[-1:].isspace(),
    ):
        add("spaces", SEVERITY_WARNING, "Baştaki veya sondaki boşluk orijinalle aynı değil.")
    return issues


def glossary_patterns(glossary: list[GlossaryTerm] | None) -> list[tuple[GlossaryTerm, re.Pattern[str]]]:
    """Sözlük denetimi için terim kalıpları (boş terimler atlanır)."""
    return [(t, _term_pattern(t.term)) for t in glossary or () if t.term.strip() and t.translation.strip()]


def glossary_words(glossary: list[GlossaryTerm] | None) -> frozenset[str]:
    """Oyun sözlüğündeki terim ve karşılıklarının sözcükleri: yazım denetiminde doğru kabul edilir."""
    out: set[str] = set()
    for t in glossary or ():
        for text in (t.term, t.translation):
            out.update(turkish_lower(w) for w, _ in words_of(text))
    return frozenset(out)


def parse_word_list(raw: str, key: str) -> list[str]:
    """Proje ayarındaki JSON metin listesini (yoksayılan sözcükler / terimler) okur; yok ya da bozuksa boş liste.

    Bozuk değer sessizce yutulmaz: `key` adıyla günlüğe uyarı yazılır.
    """
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if not isinstance(data, list) or not all(isinstance(i, str) for i in data):
        log.warning("Proje ayarı %s bozuk: boş liste kullanılıyor.", key)
        return []
    return list(dict.fromkeys(data))


def spell_extra_words(glossary: list[GlossaryTerm] | None, ignored: Collection[str] = ()) -> frozenset[str]:
    """Yazım denetiminde doğru kabul edilen ek sözcükler: oyun sözlüğü ve projede yoksayılanlar."""
    return glossary_words(glossary) | frozenset(turkish_lower(w) for w in ignored)


def run_checks(
    rows: list[TranslationRow],
    missing_letters: str,
    transliterated: str,
    glossary: list[GlossaryTerm] | None = None,
    fit: FitConfig | None = None,
    *,
    spell: SpellChecker | None = None,
    ignored_terms: Collection[str] = (),
    spell_ignored: Collection[str] = (),
) -> list[QaIssue]:
    from nxceviri.core.qa.terms import canonical_terms, term_issues  # noqa: PLC0415 - terms bu modülden QaIssue alır (döngüsel içe aktarma)

    patterns = glossary_patterns(glossary)
    extra = spell_extra_words(glossary, spell_ignored) if spell is not None else frozenset()
    out: list[QaIssue] = []
    for row in rows:
        out.extend(check_row(row, missing_letters, transliterated, patterns, fit, spell=spell, spell_extra=extra))
    out.extend(consistency_issues(rows))
    # Sözlük terimlerini "glossary" denetimi zaten bildirir; burada yalnızca satırlardan çıkan terimler aranır.
    listed = {turkish_lower(" ".join(t.term.split())) for t in glossary or ()}
    canon = canonical_terms(rows, glossary or (), ignored_terms)
    out.extend(term_issues(rows, {k: v for k, v in canon.items() if turkish_lower(" ".join(k.split())) not in listed}))
    return out


#: Tutarsızlık iletisinde bir çevirinin gösterilen en çok karakter sayısı.
_QUOTE_CHARS = 40


def _quote(text: str) -> str:
    text = " ".join(text.split())
    return f"“{text[:_QUOTE_CHARS]}…”" if len(text) > _QUOTE_CHARS else f"“{text}”"


def consistency_issues(rows: list[TranslationRow]) -> list[QaIssue]:
    """Aynı kaynak metnin farklı çevirileri. Farklı biçimlerin hepsi onaylıysa kullanıcı bilerek seçmiştir."""
    groups: dict[str, list[TranslationRow]] = {}
    for row in rows:
        if row.source.strip() and row.translation:
            groups.setdefault(row.source, []).append(row)
    out: list[QaIssue] = []
    for group in groups.values():
        counts: dict[str, int] = {}
        for row in group:
            counts[row.translation] = counts.get(row.translation, 0) + 1
        if len(counts) < 2 or all(row.status == Status.APPROVED for row in group):
            continue
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])  # eşitlikte ilk görülen önce (sıralama kararlı)
        variants = ", ".join(f"{_quote(t)} ({n} satır)" for t, n in ranked[:3])
        more = f" ve {len(ranked) - 3} biçim daha" if len(ranked) > 3 else ""
        message = f"Aynı metin {len(ranked)} farklı biçimde çevrilmiş: {variants}{more}."
        out.extend(QaIssue(r.id, r.context or r.key, "inconsistent", SEVERITY_WARNING, message) for r in group)
    return out


#: Çeviri tablosunda metni renklendiren sorun türleri, önem sırasıyla (bir satırda birden çok varsa ilki).
ROW_FLAG_KINDS = ("placeholder", "markup", "max_length", "code_position", "newlines", "overflow")


def row_flag(row: TranslationRow) -> QaIssue | None:
    """Satırın tabloda gösterilecek en önemli sorunu (font ve sözlükten bağımsız, hızlı); yoksa None."""
    if not row.translation:
        return None
    found = {i.kind: i for i in check_row(row, "", "")}
    return next((found[k] for k in ROW_FLAG_KINDS if k in found), None)
