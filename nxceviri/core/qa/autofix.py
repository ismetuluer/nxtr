"""Kalite denetimi bulgularının türe göre düzeltilmesi.

Düzeltmelerin hepsi programla, kesin kurallarla yapılır (model kullanılmaz). Her düzeltme bir bulgu türüne
bağlıdır (`FIX_KINDS`); kullanıcı hangi türlerin düzeltileceğini seçer ve yalnızca o düzeltmeler uygulanır:

- `markup`: çeviriye girmiş, özgünde olmayan HTML/XML etiketleri atılır;
- `placeholder`: özgünde olmayan uydurma kodlar atılır; aynı kodların sırası karışmışsa (ör. iki "Satır sonu")
  numaralar özgünün sırasına dizilir (Hatalı satır da böyle düzelir); yarım yazılmış yer tutucu (`[1]`) düzelir ve
  tam satırı kaplayan eksik biçim zarfı tamamlanır (`codefix`: yalnızca güvenli durumlar);
- `code_position`: sona yığılmış satır sonu kodları özgündeki yerlerine dağıtılır;
- `newlines`: özgünde satır sonu yokken çeviriye girmiş satır sonları boşluğa çevrilir; özgünde varsa ve sayısı
  tutmuyorsa çeviri sözcük sınırlarından dengeli satırlara yeniden bölünür;
- `spaces`: baştaki/sondaki boşluklar özgünle eşlenir;
- `glossary`: çeviride İngilizce kalmış sözlük terimi karşılığıyla değiştirilir, kesme işaretinden sonraki ek
  korunur ("Sheriff'e" → "Şerif'e");
- `ascii_turkish`: ASCII'ye çevrilmiş Türkçe harfler sözlükle onarılır (`asciitr`); belirsiz sözcüğe dokunulmaz;
- `end_punctuation`, `double_space`, `repeated_word`, `extra_dots`, `space_before_punct`: metin temizliği;
- `line_too_long`, `page_too_tall`, `bad_break`: projede satır/sayfa sınırı tanımlıysa sorunlu sayfa kelime
  sınırlarından, noktalamayı tercih ederek yeniden bölünür (`fit_text`); sayfa sonu kodlarına dokunulmaz. Sınırlı
  satırda "satır sonu sayısı özgünle aynı olmalı" kuralı uygulanmaz; satır sayısını sınır belirler.

Olası taşma, uzunluk sınırı aşımı, güvenle onarılamayan eksik kontrol kodu, şüpheli çeviri, eksik harf (font) ve
kod adı uyarıları düzeltilmez: anlam gerektirir ya da kararı insan verir. Onaylanmış satırlara dokunulmaz.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass, field, replace
from typing import NamedTuple

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.asciitr import repair_ascii_turkish
from nxceviri.core.qa.checks import QaIssue, check_row, glossary_patterns
from nxceviri.core.qa.codefix import closer_base, repair_codes
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.cleanup import (
    collapse_inner_spaces,
    collapse_repeated_punct,
    drop_invented_codes,
    drop_repeated_words,
    drop_space_before_punct,
    fix_extra_dots,
    split_words,
    spread_trailing_breaks,
    strip_added_end_punctuation,
    strip_markup,
    tidy_punctuation,
    tidy_spaces,
)
from nxceviri.core.translate.codekinds import KIND_LINE_BREAK, KIND_PAGE_BREAK, KIND_STYLE, guess_kind
from nxceviri.core.translate.fit import (
    PROBLEM_BREAK,
    PROBLEM_LINE,
    PROBLEM_PAGE,
    find_problems,
    fit_text,
    reflow_text,
)
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.runner import match_edges
from nxceviri.core.translate.status import Status

#: Satır/sayfa sınırı bulgu türleri (yalnızca projede sınır tanımlıysa çıkar).
FIT_KINDS = frozenset({PROBLEM_LINE, PROBLEM_PAGE, PROBLEM_BREAK})
#: Düzeltilebilen bulgu türleri, arayüzdeki liste sırasıyla.
FIX_KINDS = (
    "placeholder",
    "markup",
    "code_position",
    "newlines",
    "spaces",
    "glossary",
    "ascii_turkish",
    "end_punctuation",
    "double_space",
    "repeated_word",
    "extra_dots",
    "space_before_punct",
    PROBLEM_LINE,
    PROBLEM_PAGE,
    PROBLEM_BREAK,
)


@dataclass
class FixPlan:
    #: Yazılacak düzeltmeler: (satır kimliği, yeni çeviri).
    changes: list[tuple[int, str]] = field(default_factory=list)
    #: Satır kimliği → o satırda düzelen türler (`FIX_KINDS` sırasıyla).
    applied: dict[int, tuple[str, ...]] = field(default_factory=dict)
    #: Düzeltilebilir sorunu olduğu hâlde onaylandığı için dokunulmayan satır sayısı.
    approved: int = 0
    #: Seçilen türde sorunu olup program düzeltemediği için değişmeyen satır sayısı.
    unfixed: int = 0

    @property
    def empty(self) -> bool:
        return not self.changes


def rebalance_lines(text: str, lines: int) -> str | None:
    """Metni sözcük sınırlarından `lines` satıra, satır uzunlukları dengeli olacak biçimde böler."""
    parts = split_words(text, [1.0] * lines)
    return None if parts is None else "\n".join(parts)


def _pairs_nest(sequence: Sequence[int], labels: Sequence[str]) -> bool:
    """Açılış/kapanış kodları dizide geçerli mi: her kapanıştan önce eşi açılmış ve kapanmamış olmalı."""
    bases = {b for lb in labels if (b := closer_base(lb, labels)) is not None}
    opened: list[str] = []
    for n in sequence:
        if not 0 < n <= len(labels):
            return False
        label = labels[n - 1].casefold()
        base = closer_base(labels[n - 1], labels)
        if base is None:
            opened.extend(b for b in bases if label.startswith(b) and not label.endswith(" sonu"))
        elif base in opened:
            opened.remove(base)
        else:
            return False
    return True


#: Yeri değiştirilebilen (değer taşımayan) kod türleri; değişken, sembol ve tanınmayan kodlar asla başka koda çevrilmez.
_MOVABLE_KINDS = frozenset({KIND_LINE_BREAK, KIND_PAGE_BREAK, KIND_STYLE})


def reorder_codes(source: str, text: str, labels: Sequence[str]) -> str | None:
    """Kodların çoklu kümesi özgünle aynı ama sırası farklıysa, kodları özgünün sırasına göre yeniden numaralar.

    Yalnızca değer taşımayan kodlar (satır/sayfa sonu, biçim açma/kapama) ve yalnızca aynı türden, aynı etiketli
    (birbirinin yerine geçebilen) kodlar arasında yapılır: k'inci geçiş özgündeki k'inci kodla değiştirilir. Değişkenler
    (oyuncu adı, sayı, eşya adı …) ve tanınmayan kodlar yerinde ve aynı sırada kalmalıdır; kalmıyorsa hiçbir şey
    yapılmaz. Çevirideki açılış/kapanış çiftleri de iç içe geçerli olmalı. Metin aynı kalır. Sorun yoksa, kümeler
    farklıysa (eksik/fazla kod) ya da düzeltilemiyorsa None.
    """
    expected = placeholders.tokens_in(source)
    got = placeholders.tokens_in(text)
    if expected == got or sorted(expected) != sorted(got):
        return None
    if not _pairs_nest(expected, labels) or not _pairs_nest(got, labels):
        return None

    def kind_of(n: int) -> str:
        return guess_kind(labels[n - 1]) if 0 < n <= len(labels) else ""

    def fixed(n: int) -> bool:
        return kind_of(n) not in _MOVABLE_KINDS

    if [n for n in expected if fixed(n)] != [n for n in got if fixed(n)]:
        return None
    wanted: dict[str, Iterator[int]] = {}
    for kind in _MOVABLE_KINDS:
        wanted[kind] = iter([n for n in expected if kind_of(n) == kind])
    result: list[int] = []
    for n in got:
        if fixed(n):
            result.append(n)
            continue
        new = next(wanted[kind_of(n)])
        if labels[new - 1].casefold() != labels[n - 1].casefold():
            return None
        result.append(new)
    if result != expected:
        return None
    order = iter(result)
    return placeholders.TOKEN_RE.sub(lambda _m: placeholders.token(next(order)), text)


def apply_glossary(source: str, text: str, glossary: Sequence[GlossaryTerm]) -> str:
    """Kaynakta geçip çeviride İngilizce kalmış sözlük terimlerini karşılığıyla değiştirir (ekler korunur)."""
    for term, pattern in glossary_patterns(list(glossary)):
        if pattern.search(source) and term.translation.casefold() not in text.casefold():
            text = pattern.sub(term.translation.replace("\\", "\\\\"), text)
    return text


class Tidy(NamedTuple):
    """Satır sığdırılırken hangi temizlikler yapılsın (düzeltme türleri seçimine göre)."""

    spaces: bool = True
    before_punct: bool = True
    repeated: bool = True


ALL_TIDY = Tidy()


def fit_and_tidy(row: TranslationRow, text: str, fit: FitConfig, tidy: Tidy = ALL_TIDY) -> str:
    """Sınırı olan satırı sığdırır (`fit_text`), sonra projenin temizlik seçeneklerini uygular.

    Temizlik yalnızca karakter atar; yine de sığdırma sonucunu bozarsa (ör. kısalan satır gereksiz kısa kalırsa)
    metin yeniden sığdırılır, bu da bulgu sayısını artırıyorsa temizlenmemiş hâl korunur.
    """
    rules = fit.rules_for_row(row)
    if rules is None:
        return text
    kind_of = fit.kind_of_row(row)
    fitted = fit_text(text, kind_of, rules, row.source).text
    tidied = tidy_punctuation(
        row.source, fitted, spaces=tidy.spaces, before_punct=tidy.before_punct, repeated=tidy.repeated
    )
    if tidied == fitted:
        return fitted
    before = len(find_problems(fitted, kind_of, rules, row.source))
    if len(find_problems(tidied, kind_of, rules, row.source)) <= before:
        return tidied
    refitted = fit_text(tidied, kind_of, rules, row.source).text
    # Yeniden bölme de sığdıramazsa (ör. noktalamaya yapışan kelime satırdan uzun kaldıysa) temizliksiz hâl korunur.
    return refitted if len(find_problems(refitted, kind_of, rules, row.source)) <= before else fitted


def reflow_row(row: TranslationRow, fit: FitConfig) -> str | None:
    """Çevirideki satır sonlarını kaldırıp yeniden böler (`reflow_text`); değişmiyorsa ya da bölünemiyorsa `None`.

    Satırın sınırı varsa ona, yoksa orijinalin satır sayısına göre bölünür. Kontrol kodlarının sayısı, türü ve sırası
    ile yer tutucu denetimi sonucu kötüleşiyorsa satıra dokunulmaz.
    """
    if not row.translation:
        return None
    new = reflow_text(row.translation, fit.kind_of_row(row), fit.rules_for_row(row), row.source)
    if new == row.translation or placeholders.tokens_in(new) != placeholders.tokens_in(row.translation):
        return None
    if not set(placeholders.problems(row.source, new)) <= set(placeholders.problems(row.source, row.translation)):
        return None
    return new


def plan_reflow(rows: Sequence[TranslationRow], fit: FitConfig) -> list[tuple[int, str]]:
    """Verilen satırları yeniden bölme planı: `(satır kimliği, yeni çeviri)`; yalnızca değişen satırlar."""
    plan: list[tuple[int, str]] = []
    for row in rows:
        new = reflow_row(row, fit)
        if new is not None:
            plan.append((row.id, new))
    return plan


def local_fix(
    row: TranslationRow,
    glossary: Sequence[GlossaryTerm] = (),
    fit: FitConfig | None = None,
    kinds: Collection[str] | None = None,
    *,
    spell: SpellChecker | None = None,
    spell_extra: frozenset[str] = frozenset(),
) -> str:
    """Seçilen türlerin düzeltmelerini uygular (`kinds=None`: hepsi); değişiklik yoksa çeviriyi aynen döndürür.

    Her tür yalnızca kendi düzeltmesini yapar. Satırın dosyasına sınır tanımlıysa satır sonu sayısını özgüne
    eşitleme yerine sığdırma ve temizlik seçenekleri uygulanır (`fit_and_tidy`). Sonuçta özgünün kontrol
    kodlarına göre çeviride olmayan yeni bir kod sorunu (`placeholders.problems`) çıkıyorsa hiçbir düzeltme
    uygulanmaz; çeviri aynen döner.
    """
    want = frozenset(FIX_KINDS if kinds is None else kinds)
    source = row.source
    limited = fit is not None and fit.rules_for_row(row) is not None
    text = row.translation
    cleaned = text
    if "markup" in want:
        cleaned = strip_markup(source, cleaned)
    if "placeholder" in want:
        cleaned = drop_invented_codes(source, cleaned)
    if "code_position" in want:
        cleaned = spread_trailing_breaks(source, cleaned, row.code_labels) or cleaned
    if cleaned != text:
        text = tidy_spaces(source, cleaned)
    source_breaks = source.count("\n")
    if "newlines" in want and not limited and text.count("\n") != source_breaks:
        if not source_breaks:
            text = " ".join(part.strip() for part in text.split("\n") if part.strip())
        else:
            text = rebalance_lines(text, source_breaks + 1) or text
    if "placeholder" in want:
        text = reorder_codes(source, text, row.code_labels) or text
        text = repair_codes(source, text, row.code_labels) or text
    if "glossary" in want:
        text = apply_glossary(source, text, glossary)
    if "ascii_turkish" in want and spell is not None:
        text = repair_ascii_turkish(source, text, spell, spell_extra).text
    if "end_punctuation" in want:
        text = strip_added_end_punctuation(source, text)
    # Sınırlı satırda boşluk ve noktalama temizliğini `fit_and_tidy` (sığdırmayı bozarsa geri alarak) yapar.
    tidy = Tidy("double_space" in want, "space_before_punct" in want, "extra_dots" in want)
    if "double_space" in want and not limited:
        text = collapse_inner_spaces(source, text)
    if "repeated_word" in want:
        text = drop_repeated_words(source, text)
    if "extra_dots" in want:
        text = fix_extra_dots(source, text)
        if not limited:
            text = collapse_repeated_punct(source, text)
    if "space_before_punct" in want and not limited:
        text = drop_space_before_punct(source, text)
    if fit is not None and limited:
        if want & FIT_KINDS:
            # Sığdırma uzunluğu değiştiren son adımdır: sözlük terimi satırı uzatmış olabilir.
            text = fit_and_tidy(row, text, fit, tidy)
        else:
            text = tidy_punctuation(
                source, text, spaces=tidy.spaces, before_punct=tidy.before_punct, repeated=tidy.repeated
            )
    text = match_edges(source if "spaces" in want else row.translation, text)
    # Kontrol kodu bütünlüğü hiçbir yerel adımda kötüleşmemeli (§4.3); kötüleşirse çeviri olduğu gibi kalır.
    before = set(placeholders.problems(source, row.translation))
    if not set(placeholders.problems(source, text)) <= before:
        return row.translation
    return text


def plan_fixes(
    rows: Sequence[TranslationRow],
    issues: Sequence[QaIssue],
    kinds: Collection[str] | None = None,
    *,
    include_approved: bool = False,
    glossary: Sequence[GlossaryTerm] = (),
    fit: FitConfig | None = None,
    spell: SpellChecker | None = None,
    spell_extra: frozenset[str] = frozenset(),
) -> FixPlan:
    """Denetim bulgularından, yalnızca seçilen türler için düzeltme planı çıkarır (`kinds=None`: hepsi).

    Her satır yalnızca kendisinde bulunan ve seçilen türlerin düzeltmeleriyle işlenir. Onaylanmış satırlar yalnızca
    istenirse ele alınır. Hatalı satırda yalnızca kod sırası düzeltilir (düzeltince sorun kalmıyorsa); yazılırken
    durumu kod denetimiyle yeniden belirlenir. Düzeltmeyle ortadan kalkan türler `applied`a yazılır.
    """
    want = frozenset(FIX_KINDS if kinds is None else kinds) & frozenset(FIX_KINDS)
    by_id = {r.id: r for r in rows}
    found: dict[int, set[str]] = {}
    for issue in issues:
        if issue.kind in want:
            found.setdefault(issue.row_id, set()).add(issue.kind)
    plan = FixPlan()
    patterns = glossary_patterns(list(glossary))
    for row_id, row_kinds in found.items():
        row = by_id.get(row_id)
        if row is None or not row.translation:
            continue
        if row.status == Status.APPROVED and not include_approved:
            plan.approved += 1
            continue
        targeted = tuple(k for k in FIX_KINDS if k in row_kinds)
        if row.status == Status.ERROR:
            reordered = None
            if "placeholder" in row_kinds:
                reordered = reorder_codes(row.source, row.translation, row.code_labels) or repair_codes(
                    row.source, row.translation, row.code_labels
                )
            if reordered is None or placeholders.problems(row.source, reordered):
                plan.unfixed += 1
                continue
            plan.changes.append((row.id, reordered))
            plan.applied[row.id] = ("placeholder",)
            continue
        fixed = local_fix(row, glossary, fit, row_kinds, spell=spell, spell_extra=spell_extra)
        if fixed == row.translation:
            plan.unfixed += 1
            continue
        left = {
            i.kind
            for i in check_row(
                replace(row, translation=fixed), "", "", patterns, fit, spell=spell, spell_extra=spell_extra
            )
        }
        plan.changes.append((row.id, fixed))
        plan.applied[row.id] = tuple(k for k in targeted if k not in left) or targeted
    return plan
