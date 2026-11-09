"""Terim tutarsızlığı: aynı özel adın/terimin projede hep aynı çevrilmesini denetler.

Kanonik çeviri iki yerden gelir: sözlük (öncelikli) ve en az iki satırda kendi başına bir satır olan kısa, büyük
harfle başlayan kaynak metinlerin en sık görülen çevirisi. Sonra kaynağında ifade geçen her satırın çevirisinde
kanonik çeviri aranır. Yanlış pozitifleri azaltmak için kaynakta eşleşme büyük/küçük harfe duyarlıdır (büyük harfle
başlayan ifade kaynakta da büyük harfle geçmeli), tek sözcüklü ifadelerin cümle başındaki geçişleri sayılmaz ve
kanonik çeviride Türkçe ünsüz yumuşaması (Kılıç → Kılıcı) kabul edilir.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter, defaultdict
from collections.abc import Collection, Mapping, Sequence

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import SEVERITY_WARNING, QaIssue
from nxceviri.core.spell.checker import turkish_lower
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import Status

#: Kendi başına satır olan bir ifadenin terim sayılması için en çok sözcük sayısı.
MAX_TERM_WORDS = 4
#: Bir ifadenin kanonik sayılması için kendi başına bir satır olarak geçmesi gereken en az satır sayısı.
MIN_TERM_ROWS = 2
#: Tek sözcüklü bir ifadenin en az harf sayısı ("I", "A" gibi harfler terim sayılmaz).
MIN_SINGLE_WORD_LETTERS = 2
#: Kanonik çevirinin son sözcüğüne doğrudan (kesmesiz) eklenebilen en çok harf sayısı: "Çamlar" + "daki".
MAX_SUFFIX_LETTERS = 8

_WORD = re.compile(r"[^\W_]+")
_CANDIDATE_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")
_SPACES = re.compile(r"\s+")
_VOWELS = "aeıioöuü"
#: Son harfin ek öncesi yumuşamış biçimi: Kılıç → Kılıcı, Mızrak → Mızrağı, Kitap → Kitabı, Ağaç → Ağacı.
_SOFTENED = {"ç": "c", "k": "ğ", "p": "b", "t": "d"}
#: Cümle başı sayılması için ifadenin önündeki metnin sonunda bulunabilen işaretler.
_SENTENCE_END = ".!?…:"
#: Kanonik çevirinin sonundaki, cümle içi geçişte bulunmayacak noktalama.
_TRAILING_PUNCTUATION = " .!?…,;:"
_OPENERS = " \t\r\n\"'“‘«([{"


def _squash(text: str) -> str:
    """Kodları ve satır sonlarını tek boşluğa, fazla boşlukları tek boşluğa indirir."""
    if placeholders.OPEN in text:
        text = placeholders.TOKEN_RE.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def _blank_codes(text: str) -> str:
    if placeholders.OPEN not in text:
        return text
    return placeholders.TOKEN_RE.sub(lambda m: " " * len(m.group(0)), text)


def _tokens(visible: str) -> list[tuple[str, int, int]]:
    """Sözcükler (Türkçe küçük harf) ve konumları. Küçük harfe çevirme konumları değiştirmez."""
    low = turkish_lower(visible)
    return [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(low)]


def _gap(text: str) -> str:
    return _SPACES.sub(" ", text)


def _phrase_key(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """İfadenin sözcükleri ve aralarındaki ayraçlar (eşleşmede ayraçlar da aynı olmalı)."""
    visible = _squash(text)
    tokens = _tokens(visible)
    gaps = tuple(visible[a[2] : b[1]] for a, b in itertools.pairwise(tokens))
    return tuple(t[0] for t in tokens), gaps


def _candidate_source(source: str) -> str | None:
    """Kendi başına terim olabilecek kaynak metin (1-4 sözcük, büyük harfle başlar, kod/noktalama yok) ya da None."""
    if placeholders.TOKEN_RE.search(source):
        return None
    words = source.split()
    if not 1 <= len(words) <= MAX_TERM_WORDS:
        return None
    if len(words) == 1 and len(words[0]) < MIN_SINGLE_WORD_LETTERS:
        return None
    if not all(_CANDIDATE_WORD.fullmatch(w) for w in words) or not words[0][0].isupper():
        return None
    return " ".join(words)


def canonical_terms(
    rows: Sequence[TranslationRow], glossary: Sequence[GlossaryTerm], ignored: Collection[str] = ()
) -> dict[str, str]:
    """Kaynak ifade → kanonik çeviri. Sözlük, satırlardan çıkarılana göre önceliklidir; `ignored` atlanır."""
    skip = {turkish_lower(_squash(i)) for i in ignored}
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    approved: dict[str, Counter[str]] = defaultdict(Counter)
    shown: dict[str, str] = {}
    seen: Counter[str] = Counter()  # ifadenin kendi başına satır olarak geçtiği satır sayısı (çevrilmemişler dahil)
    for row in rows:
        phrase = _candidate_source(row.source.strip())
        if phrase is None:
            continue
        key = turkish_lower(phrase)
        seen[key] += 1
        translation = _squash(row.translation)
        if not translation:
            continue
        shown.setdefault(key, phrase)
        votes[key][translation] += 1
        if row.status == Status.APPROVED:
            approved[key][translation] += 1
    canon: dict[str, str] = {}
    for key, counter in votes.items():
        if key in skip or seen[key] < MIN_TERM_ROWS:
            continue
        # En sık çeviri; eşitlikte onaylı olan, sonra ilk görülen (sıralama kararlı).
        best = max(counter, key=lambda t: (counter[t], approved[key][t]))
        canon[shown[key]] = best
    for term in glossary:
        phrase = _squash(term.term)
        if not phrase or not term.translation.strip() or turkish_lower(phrase) in skip:
            continue
        low = turkish_lower(phrase)
        for existing in [p for p in canon if turkish_lower(p) == low]:
            del canon[existing]
        canon[phrase] = _squash(term.translation)
    return canon


def project_terms(
    rows: Sequence[TranslationRow], glossary: Sequence[GlossaryTerm] | None, ignored: Collection[str] = ()
) -> dict[str, str]:
    """Terim tutarsızlığı denetiminde aranacak kanonik terimler.

    Sözlük terimlerini "glossary" denetimi zaten bildirir; burada yalnızca satırlardan çıkan terimler aranır.
    """
    listed = {turkish_lower(" ".join(t.term.split())) for t in glossary or ()}
    canon = canonical_terms(rows, glossary or (), ignored)
    return {k: v for k, v in canon.items() if turkish_lower(" ".join(k.split())) not in listed}


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _stem_variants(needle: str) -> list[tuple[str, bool]]:
    """Aranacak kök biçimleri: (kök, ek şart mı). Yumuşamış biçim yalnızca ünlüyle başlayan bir ekle geçerlidir."""
    variants = [(needle, False)]
    if needle.endswith("nk"):
        variants.append((needle[:-1] + "g", True))  # denk → dengi
    elif needle and needle[-1] in _SOFTENED:
        variants.append((needle[:-1] + _SOFTENED[needle[-1]], True))
    return variants


def _has_stem(normal: str, stem: str, vowel_suffix: bool) -> bool:
    pos = normal.find(stem)
    while pos != -1:
        end = pos + len(stem)
        if pos == 0 or not _is_word_char(normal[pos - 1]):
            if end == len(normal):
                if not vowel_suffix:
                    return True
            elif normal[end] in "'’":
                if (
                    end + 1 < len(normal)
                    and _is_word_char(normal[end + 1])
                    and (not vowel_suffix or normal[end + 1] in _VOWELS)
                ):
                    return True
            elif not vowel_suffix or normal[end] in _VOWELS:
                stop = end
                while stop < len(normal) and normal[stop].isalpha():
                    stop += 1
                if stop - end <= MAX_SUFFIX_LETTERS and (stop == len(normal) or not _is_word_char(normal[stop])):
                    return True
        pos = normal.find(stem, pos + 1)
    return False


def _has_term(normal: str, needle: str) -> bool:
    """`normal` (`_normal` biçimi) içinde `needle` sözcük sınırıyla geçiyor mu; sonuna Türkçe ek gelebilir.

    Ek ya kesme işaretiyle (Çamlar'a), ya doğrudan en çok `MAX_SUFFIX_LETTERS` harfle (Çamlarda) gelir. Son harf
    ç/k/p/t ise ünlüyle başlayan ekin önünde c/ğ/b/d'ye (nk ise ng'ye) yumuşamış biçimi de kabul edilir.
    """
    return any(_has_stem(normal, stem, vowel) for stem, vowel in _stem_variants(needle))


def _sentence_start(visible: str, pos: int) -> bool:
    """`pos` konumundaki sözcük satır başında ya da cümle sonu işaretinden sonra mı."""
    before = visible[:pos].rstrip(_OPENERS)
    if not before:
        return True
    return before[-1] in _SENTENCE_END or "\n" in visible[len(before) : pos]


def _normal(text: str) -> str:
    return turkish_lower(_squash(text))


def term_issues(rows: Sequence[TranslationRow], canon: Mapping[str, str]) -> list[QaIssue]:
    """Kaynağında terim geçen ama çevirisinde kanonik çeviri olmayan satırlar (tür "term", uyarı)."""
    phrases: dict[tuple[str, ...], list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
    needles: dict[str, str] = {}  # kanonik çevirinin karşılaştırma biçimi, ilk kullanımda kurulur
    for phrase, canonical in canon.items():
        words, gaps = _phrase_key(phrase)
        if words and _squash(canonical):
            phrases[words].append((phrase, gaps))
    if not phrases:
        return []
    sizes: dict[str, set[int]] = defaultdict(set)
    for words in phrases:
        sizes[words[0]].add(len(words))
    found: dict[str, list[tuple[TranslationRow, bool]]] = defaultdict(list)
    for row in rows:
        if not row.translation or not row.source:
            continue
        visible = _blank_codes(row.source)
        names = _WORD.findall(turkish_lower(visible))
        starts = [i for i, name in enumerate(names) if name in sizes]
        if not starts:
            continue
        spans = [m.span() for m in _WORD.finditer(visible)]  # konumlar yalnızca terimli satırlarda gerekir
        normal: str | None = None
        seen: set[str] = set()
        for start in starts:
            for size in sizes[names[start]]:
                group = spans[start : start + size]
                options = phrases.get(tuple(names[start : start + size]))
                if len(group) != size or not options:
                    continue
                between = tuple(_gap(visible[a[1] : b[0]]) for a, b in itertools.pairwise(group))
                standalone = visible[group[0][0] : group[-1][1]] == visible.strip()
                first = visible[group[0][0]]
                at_start = size == 1 and _sentence_start(visible, group[0][0])
                for phrase, gaps in options:
                    if gaps != between or standalone or at_start or phrase in seen:
                        continue
                    if phrase[:1].isupper() and not first.isupper():
                        continue  # büyük harfle başlayan ifade kaynakta da büyük harfle geçmeli
                    seen.add(phrase)
                    if normal is None:
                        normal = _normal(row.translation)
                    if phrase not in needles:
                        needle = _normal(canon[phrase])
                        needles[phrase] = needle.rstrip(_TRAILING_PUNCTUATION) or needle
                    found[phrase].append((row, _has_term(normal, needles[phrase])))
    out: list[QaIssue] = []
    for phrase, uses in found.items():
        canonical = _squash(canon[phrase])
        good = sum(1 for _, ok in uses if ok)
        if good:
            message = f"‘{phrase}’ burada çevrilmemiş ya da farklı çevrilmiş; {good} satırda ‘{canonical}’."
        else:
            message = f"‘{phrase}’ burada çevrilmemiş ya da farklı çevrilmiş; kanonik çeviri ‘{canonical}’."
        out.extend(
            QaIssue(r.id, r.context or r.key, "term", SEVERITY_WARNING, message, (phrase,)) for r, ok in uses if not ok
        )
    out.sort(key=lambda i: i.row_id)
    return out
