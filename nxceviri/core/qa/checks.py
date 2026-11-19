"""Çeviri kalite denetimleri (QA).

Denetimler satır başınadır ve yalnızca bulguları döndürür; satırları değiştirmez.

| Tür | Önem | Ne zaman |
|---|---|---|
| placeholder | hata | Kontrol kodları bozuk (satır "Hatalı"; dışa aktarılmaz) |
| code_order | uyarı | Yalnızca serbest kodların (değişken, simge) yeri değişmiş; satır dışa aktarılır |
| max_length | hata | Biçimin koyduğu uzunluk sınırı aşılmış |
| glyph | uyarı | Çeviride fontta olmayan ve dönüştürülmeyecek harf var |
| overflow | uyarı | Çeviri orijinalden belirgin biçimde uzun (kutuya sığmayabilir) |
| newlines | uyarı | Satır sonu sayısı orijinalden farklı (biçim yasaklıyorsa hata; dışa aktarılmaz) |
| line_too_long | uyarı | Bir satır, sığdırma kuralındaki karakter sınırını aşıyor |
| page_too_tall | uyarı | Bir sayfada sığdırma kuralındaki satır sayısından fazla satır var |
| bad_break | uyarı | Satır gereksiz kısa kesilmiş; sonraki sözcük sığardı |
| too_wide | uyarı | Fontla ölçülen genişlik orijinal kutuyu toleranstan fazla aşıyor (kapsamda açıksa) |
| spaces | uyarı | Baştaki/sondaki boşluklar orijinalle aynı değil |
| glossary | uyarı | Terminolojideki terim kaynakta geçiyor ama Türkçe karşılığı çeviride yok |
| identifier | uyarı | Kaynak bir kod adına benziyor (Ad_Soyad_1) ve çevrilmiş; oyun bu adı arayabilir |
| suspicious | uyarı | Uydurma belirtisi: İngilizce kalmış, yabancı alfabe, tekrar döngüsü, orijinalden çok uzun/kısa |
| end_punctuation | uyarı | Çevirinin sonuna orijinalde olmayan noktalama eklenmiş (otomatik düzeltmede atılır) |
| ascii_turkish | uyarı | ASCII'ye çevrilmiş Türkçe harf (tesekkur → teşekkür); sözlükle onarılır |
| profanity | uyarı | Çeviride Türkçe küfür ya da argo var (proje ayarıyla açılır; çocuk oyunları için) |
| spelling | bilgi | Çeviride Türkçe yazım sözlüğünde olmayan sözcük var (süzgeçle görülür; sözlüğe eklenebilir) |
| missing_markup | uyarı | Orijinaldeki ham etiket (`<i>`, `[color=..]`, `{ad}`) çeviride eksik |
| protected | uyarı | Orijinal cümlenin içindeki kod adı (`Fire_Cannon`) çeviride aynen yok |
| double_space | uyarı | Metnin içinde çift/çoklu boşluk (otomatik düzeltilir) |
| repeated_word | uyarı | Art arda aynı sözcük, "ve ve" (otomatik düzeltilir) |
| extra_dots | uyarı | 4+ nokta, orijinalde olmayan "..", "!!!!", ",," (otomatik düzeltilir) |
| space_before_punct | uyarı | "Merhaba !" gibi noktalamadan önce boşluk (otomatik düzeltilir) |
| inconsistent | uyarı | Aynı kaynak metin projede farklı biçimlerde çevrilmiş (hepsi onaylı değilse) |
| term | uyarı | Kaynakta geçen terimin (özel ad) kanonik çevirisi çeviride yok; projede farklı çevrilmiş |
| untranslated | bilgi | Çevrilmemiş satır (oyunda orijinal metin kalır) |
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from nxceviri.core.progress import ProgressCallback
from nxceviri.core.project import TranslationRow
from nxceviri.core.qa import codefix
from nxceviri.core.qa.asciitr import AsciiRepair, repair_ascii_turkish
from nxceviri.core.qa.profanity import ProfanityConfig, describe, english_rude, find_profanity
from nxceviri.core.spell.checker import SpellChecker, turkish_lower, words_of
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.cleanup import (
    added_end_punctuation,
    collapse_inner_spaces,
    collapse_repeated_punct,
    drop_repeated_words,
    drop_space_before_punct,
    fix_extra_dots,
    foreign_markup,
    misplaced_breaks,
    missing_markup,
    missing_protected,
)
from nxceviri.core.translate.fit import PROBLEM_BREAK, PROBLEM_LINE, PROBLEM_PAGE, find_problems
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.fitwidth import KIND_TOO_WIDE, WidthMeasure, width_message
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
    "code_order": "Kod sırası",
    "spaces": "Boşluk",
    "glossary": "Terminoloji",
    "identifier": "Kod adı",
    "untranslated": "Çevrilmedi",
    "line_too_long": "Satır uzun",
    "page_too_tall": "Sayfa uzun",
    "bad_break": "Kötü bölünme",
    KIND_TOO_WIDE: "Geniş satır",
    "suspicious": "Şüpheli çeviri",
    "spelling": "Yazım",
    "ascii_turkish": "Türkçe harf eksik",
    "end_punctuation": "Sondaki noktalama",
    "inconsistent": "Tutarsız çeviri",
    "missing_markup": "Eksik etiket",
    "protected": "Korunan ifade",
    "double_space": "Çift boşluk",
    "repeated_word": "Tekrarlı sözcük",
    "extra_dots": "Tekrarlı noktalama",
    "space_before_punct": "Noktalama öncesi boşluk",
    "term": "Terim tutarsızlığı",
    "profanity": "Küfür / argo",
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
    #: Türkçe harf bulgusunda dokunulmayan belirsiz sözcükler ve adayları: (anahtar, adaylar); sağ tık seçeneği.
    choices: tuple[tuple[str, tuple[str, ...]], ...] = ()


#: "Motel_Interior_TopFloor", "Misc_Church_Medallion" gibi, boşluksuz ve alt çizgili kod adları.
_IDENTIFIER = re.compile(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+")


def _visible(text: str) -> str:
    return placeholders.TOKEN_RE.sub("", text)


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)


def _placeholder_message(row: TranslationRow, problems: list[str]) -> str:
    """Kontrol kodu bulgusunun iletisi; eksik kod varsa Düzeltmeler'in onarıp onaramayacağı başa yazılır."""
    message = row.note or " ".join(problems)
    have = set(placeholders.tokens_in(row.translation))
    if all(n in have for n in placeholders.tokens_in(row.source)):
        return message
    if codefix.repair_codes(row.source, row.translation, row.code_labels) is not None:
        return f"Düzeltmeler ile onarılabilir: {message}"
    if codefix.loses_partial_format(row.source, row.translation, row.code_labels):
        return f"Elle düzeltilmeli: renk/biçim yalnızca metnin bir bölümünü kaplıyor. {message}"
    return f"Elle düzeltilmeli: {message}"


#: Türkçe harf bulgusu iletisinde gösterilen en çok değişiklik / belirsiz sözcük sayısı.
_ASCII_SHOWN = 3


def _ascii_message(repaired: AsciiRepair) -> str:
    shown = ", ".join(f"{old} → {new}" for old, new in repaired.changes[:_ASCII_SHOWN])
    if len(repaired.changes) > _ASCII_SHOWN:
        shown += f" (+{len(repaired.changes) - _ASCII_SHOWN})"
    review = ", ".join(repaired.ambiguous[:_ASCII_SHOWN])
    if not repaired.changes:
        return f"Türkçe harf eksik olabilir. İnceleme gerekli: {review}."
    message = f"Türkçe harf eksik: {shown}."
    return f"{message} İnceleme gerekli: {review}." if review else message


def check_row(
    row: TranslationRow,
    missing_letters: str,
    transliterated: str,
    glossary: list[tuple[GlossaryTerm, re.Pattern[str]]] | None = None,
    fit: FitConfig | None = None,
    *,
    spell: SpellChecker | None = None,
    spell_extra: frozenset[str] = frozenset(),
    widths: WidthMeasure | None = None,
    profanity: ProfanityConfig | None = None,
) -> list[QaIssue]:
    """Tek bir satırı denetler. `transliterated`: dışa aktarırken dönüştürülecek harfler.

    `profanity`: küfür / argo denetiminin ayarı; verilmezse ya da kapalıysa denetlenmez.

    `widths`: fontla genişlik ölçümü (kutular tüm projeden bir kez hesaplanır, `fitwidth.build_measure`); verilmezse
    genişlik denetlenmez.

    `spell` verilirse çevirideki sözlükte olmayan sözcükler de bildirilir; `spell_extra` ek kabul edilen sözcüklerdir
    (ör. oyun sözlüğündeki terimler).
    """
    issues: list[QaIssue] = []

    def add(
        kind: str,
        severity: str,
        message: str,
        words: tuple[str, ...] = (),
        choices: tuple[tuple[str, tuple[str, ...]], ...] = (),
    ) -> None:
        issues.append(QaIssue(row.id, row.context or row.key, kind, severity, message, words, choices))

    if not row.source.strip():
        return issues
    if not row.translation:
        add("untranslated", SEVERITY_INFO, "Çevrilmedi; oyunda orijinal metin görünür.")
        return issues
    found = placeholders.check(row.source, row.translation, row.free_codes)
    problems = list(found.errors)
    if problems or row.status == Status.ERROR:
        add("placeholder", SEVERITY_ERROR, _placeholder_message(row, problems))
    elif found.warnings:
        add("code_order", SEVERITY_WARNING, " ".join(found.warnings))
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
    forbidden_break = row.newline_forbidden and ("\n" in row.translation or "\r" in row.translation)
    if forbidden_break:
        add(
            "newlines",
            SEVERITY_ERROR,
            "Bu dosya biçimi çeviride satır sonu kabul etmiyor; satır dışa aktarılmaz (oyunda orijinali kalır). "
            "Satırı tek satıra indirin; satır sonu gerekiyorsa orijinaldeki satır sonu kodunu kullanın.",
        )
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
    elif not forbidden_break and row.source.count("\n") != row.translation.count("\n"):
        add(
            "newlines",
            SEVERITY_WARNING,
            f"Orijinalde {row.source.count(chr(10))}, çeviride {row.translation.count(chr(10))} satır sonu var.",
        )
    wide = widths.problem(row) if widths is not None else None
    if wide is not None:
        add(KIND_TOO_WIDE, SEVERITY_WARNING, width_message(wide.ratio, wide.tolerance, wide.box))
    for term, pattern in glossary or ():
        if pattern.search(row.source) and turkish_lower(term.translation) not in turkish_lower(row.translation):
            add("glossary", SEVERITY_WARNING, f"Terminolojide “{term.term}” → “{term.translation}” var; çeviride yok.")
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
    if collapse_inner_spaces(row.source, row.translation) != row.translation:
        add("double_space", SEVERITY_WARNING, "Metnin içinde çift boşluk var.")
    if drop_repeated_words(row.source, row.translation) != row.translation:
        add("repeated_word", SEVERITY_WARNING, "Aynı sözcük art arda iki kez yazılmış.")
    if (
        fix_extra_dots(row.source, row.translation) != row.translation
        or collapse_repeated_punct(row.source, row.translation) != row.translation
    ):
        add("extra_dots", SEVERITY_WARNING, "Tekrarlı noktalama var (ör. “.....” “...”, “!!!!” “!!!” olmalı).")
    if drop_space_before_punct(row.source, row.translation) != row.translation:
        add("space_before_punct", SEVERITY_WARNING, "Noktalamadan önce boşluk var (“Merhaba !”).")
    end = added_end_punctuation(row.source, row.translation)
    if end:
        add("end_punctuation", SEVERITY_WARNING, f"Sonda orijinalde olmayan noktalama var: “{end}”")
    if spell is not None and row.translation.strip() != row.source.strip():
        unknown = spell.unknown_words(row.translation, row.source, spell_extra)
        if unknown:
            add("spelling", SEVERITY_INFO, f"Yazım sözlüğünde olmayan sözcükler: {', '.join(unknown)}", tuple(unknown))
    if spell is not None and row.translation.strip() != row.source.strip():
        repaired = repair_ascii_turkish(row.source, row.translation, spell, spell_extra)
        if repaired.changes or repaired.ambiguous:
            add("ascii_turkish", SEVERITY_WARNING, _ascii_message(repaired), choices=repaired.choices)
    if not problems and row.translation.strip() != row.source.strip():
        doubts = translation_problems(row.source, row.translation, "tr", breaks=False)
        if doubts:
            add("suspicious", SEVERITY_WARNING, " ".join(doubts))
    if profanity is not None and profanity.enabled:
        rude = find_profanity(row.translation, profanity, row.source)
        if rude:
            add(
                "profanity",
                SEVERITY_WARNING,
                describe(rude, english_rude(row.source)),
                tuple(m.key for m in rude),
            )
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
    terms: Mapping[str, str] | None = None,
    progress: ProgressCallback | None = None,
    widths: WidthMeasure | None = None,
    profanity: ProfanityConfig | None = None,
) -> list[QaIssue]:
    """Satırları denetler. `terms`: terim sözlüğü (`project_terms`); verilmezse `rows`tan çıkarılır.

    `widths`: tüm projeden hesaplanmış genişlik ölçümü (birkaç satır denetlenirken kutular o satırlardan
    çıkarılmaz).

    Birkaç satırı yeniden denetlerken (yerinde düzenleme) terimler tüm projeden çıkarılıp `terms` ile verilir.
    `progress`: her satırdan sonra (denetlenen, toplam, açıklama) bildirilir; toplam, satırlara ek olarak satır
    sonrası aşamaların (tutarlılık, terimler) payını da içerir. Geri çağrı istisna fırlatırsa (iptal) denetim durur.
    """
    from nxceviri.core.qa.terms import project_terms, term_issues  # noqa: PLC0415 - terms bu modülden QaIssue alır (döngüsel içe aktarma)

    patterns = glossary_patterns(glossary)
    extra = spell_extra_words(glossary, spell_ignored) if spell is not None else frozenset()
    count = len(rows)
    tail = max(count // _TAIL_SHARE, 2)  # satır sonrası aşamalar: tutarlılık ve terimler
    total = count + tail
    out: list[QaIssue] = []
    for done, row in enumerate(rows, 1):
        out.extend(
            check_row(
                row,
                missing_letters,
                transliterated,
                patterns,
                fit,
                spell=spell,
                spell_extra=extra,
                widths=widths,
                profanity=profanity,
            )
        )
        if progress is not None:
            progress(done, total, "")
    out.extend(consistency_issues(rows))
    if progress is not None:
        progress(count + tail // 2, total, _TAIL_MESSAGE)
    out.extend(term_issues(rows, project_terms(rows, glossary, ignored_terms) if terms is None else terms))
    if progress is not None:
        progress(total, total, _TAIL_MESSAGE)
    return out


#: Satır sonrası aşamaların (tutarlılık, terimler) ilerleme çubuğundaki payı: satır sayısının bu kadarda biri.
_TAIL_SHARE = 20
_TAIL_MESSAGE = "Tutarlılık ve terimler denetleniyor"


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
