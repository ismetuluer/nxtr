"""Metin sığdırma: çeviri metnini sayfalara ve satırlara ayırır, sınır ihlallerini bulur.

Oyun ekranı sınırlıdır: bir satıra en çok `width` karakter, bir sayfaya en çok `max_lines` satır sığar.
Bu modül şunları yapar:

- **Sayfa ayrıştırma** (`split_pages`): metin, "sayfa sonu" türündeki `⟦n⟧` kodlarında sayfalara ayrılır. Kodlar
  sonuçta saklanır, yani parçalar birleştirilince metin aynen geri gelir.
- **Görünen uzunluk** (`visible_width`): kontrol kodları çıkarılır; `değişken` kodu `variable_width`, `sembol` kodu
  1 karakter sayılır; baştaki ve sondaki boşluklar sayılmaz.
- **Sorun bulma** (`find_problems`): satır taşması (`line_too_long`), sayfanın çok uzun olması (`page_too_tall`) ve
  gereksiz bölünmüş satır (`bad_break`).

- **Otomatik bölme** (`fit_text`): sorunlu sayfaları noktalamayı tercih ederek, dengeli ve kelime ortasından
  bölmeden yeniden satırlara ayırır. Sorunsuz sayfalara ve sayfa sonu kodlarına dokunmaz.
- **Yeniden bölme** (`reflow_text`): sorunlu olsun olmasın her sayfanın mevcut satır sonlarını kaldırıp yeniden
  yerleştirir; sınır varsa ona göre, yoksa orijinalin satır sayısına göre dengeli böler.

Modül saftır; arayüz veya veritabanı bilmez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import NamedTuple

from nxceviri.core.translate import placeholders
from nxceviri.core.translate.codekinds import (
    KIND_LINE_BREAK,
    KIND_PAGE_BREAK,
    KIND_SYMBOL,
    KIND_VARIABLE,
    KindOf,
)

PROBLEM_LINE = "line_too_long"
PROBLEM_PAGE = "page_too_tall"
PROBLEM_BREAK = "bad_break"

#: Cümle sonu noktalaması: ardından kesmek en iyisidir.
_SENTENCE_END = ".!?…"
#: Yan cümle noktalaması: ardından kesmek iyidir.
_CLAUSE_END = ",;:"
#: Bu karakterlerle biten satırın ardından satır kesilmesi yerindedir.
_BREAK_PUNCTUATION = _SENTENCE_END + _CLAUSE_END

# Bölme maliyetleri (düşük olan tercih edilir). Testler ağırlıkların kendisini değil, davranışı sabitler.
#: Son satır dışındaki her satırın boş kalan oranının karesiyle çarpılır (dolu satırlar tercih edilir).
RAGGED_WEIGHT = 100.0
#: Birden çok satırlı sayfada son satırın boş kalan oranının karesiyle çarpılır. Diğer satırlardan hafiftir (son
#: satırın kısa kalması doğaldır); ama sıfır değildir, yoksa ilk satırlar ağzına kadar doldurulup anlam birliği olan
#: sözcükler ("ve o / zaman") ayrılırdı.
LAST_LINE_WEIGHT = 0.4 * RAGGED_WEIGHT
#: Her satır için ceza (gereksiz yere çok satır kullanılmaz).
LINE_PENALTY = 8.0
#: Birden çok satırlı sayfada son satır tek kelimeyse ceza.
ORPHAN_PENALTY = 25.0
#: Cümle sonu noktalamasından sonra kesme ödülü.
SENTENCE_BONUS = 30.0
#: Virgül, noktalı virgül veya iki noktadan sonra kesme ödülü.
CLAUSE_BONUS = 10.0
#: Gereksiz bölünmüş (`bad_break`) satır cezası. Toplam puana eklenir; ayrıca düzenler önce bu tür satırların
#: sayısına göre karşılaştırılır, yani geçerli bir düzen varsa sonuçta `bad_break` kalmaz.
BAD_BREAK_PENALTY = 60.0


#: `değişken` türündeki bir kodun varsayılan görünen genişliği (karakter).
DEFAULT_VARIABLE_WIDTH = 6


@dataclass(frozen=True)
class FitRules:
    """Satır başına en çok karakter ve sayfa başına en çok satır."""

    width: int
    max_lines: int
    variable_width: int = DEFAULT_VARIABLE_WIDTH

    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError("Satır genişliği en az 1 karakter olmalıdır.")
        if self.max_lines < 1:
            raise ValueError("Sayfa başına satır sayısı en az 1 olmalıdır.")


class PageProblem(NamedTuple):
    """Bir sınır ihlali. `page` ve `line` 1'den başlar; `page_too_tall` için `line` 0'dır.

    `measured`: `line_too_long` için görünen uzunluk, `page_too_tall` için satır sayısı,
    `bad_break` için kısa kalan satırın görünen uzunluğu.
    """

    kind: str
    page: int
    line: int
    measured: int


def split_pages(text: str, kind_of: KindOf) -> list[tuple[str, str]]:
    """Metni sayfa sonu kodlarında böler: `(sayfa_metni, ardından_gelen_sayfa_sonu_kodu_veya_"")`.

    Her zaman `"".join(a + b for a, b in sonuç) == text` olur; son sayfanın ayırıcısı `""`dır.
    """
    pages: list[tuple[str, str]] = []
    start = 0
    for m in placeholders.TOKEN_RE.finditer(text):
        if kind_of(int(m.group(1))) == KIND_PAGE_BREAK:
            pages.append((text[start : m.start()], m.group(0)))
            start = m.end()
    pages.append((text[start:], ""))
    return pages


def visible_width(line: str, kind_of: KindOf, rules: FitRules) -> int:
    """Satırın ekranda kapladığı karakter sayısı (kenar boşlukları atılır, sonra kodlar çıkarılır)."""
    line = line.strip()
    extra = 0
    parts: list[str] = []
    pos = 0
    for m in placeholders.TOKEN_RE.finditer(line):
        parts.append(line[pos : m.start()])
        pos = m.end()
        kind = kind_of(int(m.group(1)))
        if kind == KIND_VARIABLE:
            extra += rules.variable_width
        elif kind == KIND_SYMBOL:
            extra += 1
    parts.append(line[pos:])
    return len("".join(parts)) + extra


def split_lines(page: str, kind_of: KindOf) -> list[str]:
    """Sayfayı `\\n` ve satır sonu kodlarından satırlara böler (satır sonu kodları satırlara girmez)."""
    lines: list[str] = []
    start = 0
    pos = 0
    while pos < len(page):
        if page[pos] == "\n":
            lines.append(page[start:pos])
            pos += 1
            start = pos
            continue
        m = placeholders.TOKEN_RE.match(page, pos)
        if m is not None:
            if kind_of(int(m.group(1))) == KIND_LINE_BREAK:
                lines.append(page[start:pos])
                start = m.end()
            pos = m.end()
        else:
            pos += 1
    lines.append(page[start:])
    return lines


#: Sözcük ayıracı: yalnızca boşluk, sekme ve satır sonu. Bölünmez boşluk (U+00A0, "10 km") sözcüğün parçasıdır.
_WORD_SEPARATOR = re.compile(r"[ \t\r\n]+")


def _words(text: str) -> list[str]:
    return [word for word in _WORD_SEPARATOR.split(text) if word]


def _balanced_parts(words: list[str], count: int) -> list[str] | None:
    """Kelimeleri (bölünmez boşlukları koruyarak) uzunluğa göre dengeli `count` satıra böler; kelime yetmezse `None`."""
    if count < 1 or len(words) < count:
        return None
    starts = []
    pos = 0
    for w in words:
        starts.append(pos)
        pos += len(w) + 1
    total = max(pos - 1, 1)
    cuts: list[int] = []
    prev = 0
    for k in range(1, count):
        target = total * k / count
        lo, hi = prev + 1, len(words) - (count - k)
        prev = min(range(lo, hi + 1), key=lambda j: abs(starts[j] - 0.5 - target))  # araya düşen boşluğun yeri
        cuts.append(prev)
    bounds = [0, *cuts, len(words)]
    return [" ".join(words[a:b]) for a, b in pairwise(bounds)]


def _bare_end(line: str) -> str:
    """Satırın kodları ve sondaki boşluğu atılmış hâli (noktalama denetimi için)."""
    return placeholders.TOKEN_RE.sub("", line).rstrip()


def _ends_with_punctuation(line: str) -> bool:
    return _bare_end(line).endswith(tuple(_BREAK_PUNCTUATION))


def _bad_break_measured(own: int, ends_with_punctuation: bool, next_word: int | None, rules: FitRules) -> bool:
    """`bad_break` tanımı, ölçülerle: `own` satırın, `next_word` sonraki satırın ilk kelimesinin görünen uzunluğu."""
    if own == 0 or next_word is None:
        return False
    if own * 2 >= rules.width or ends_with_punctuation:
        return False
    return own + 1 + next_word <= rules.width


def _is_bad_break(line: str, following: str, kind_of: KindOf, rules: FitRules) -> bool:
    """Satır genişliğin yarısından kısa, sonraki satırın ilk kelimesi sığardı ve satır noktalamayla bitmiyor."""
    words = _words(following)
    next_word = visible_width(words[0], kind_of, rules) if words else None
    own = visible_width(line, kind_of, rules)
    return _bad_break_measured(own, _ends_with_punctuation(line), next_word, rules)


#: Orijinalde de bulunan kısa bölünmelerin (sayfa, satır) konumları; bu konumlarda `bad_break` sayılmaz.
_Allowed = frozenset[tuple[int, int]]


def _page_problems(page: str, page_no: int, kind_of: KindOf, rules: FitRules, allowed: _Allowed) -> list[PageProblem]:
    problems: list[PageProblem] = []
    lines = split_lines(page, kind_of)
    if len(lines) > rules.max_lines:
        problems.append(PageProblem(PROBLEM_PAGE, page_no, 0, len(lines)))
    for line_no, line in enumerate(lines, start=1):
        measured = visible_width(line, kind_of, rules)
        if measured > rules.width:
            problems.append(PageProblem(PROBLEM_LINE, page_no, line_no, measured))
        elif (
            line_no < len(lines)
            and (page_no, line_no) not in allowed
            and _is_bad_break(line, lines[line_no], kind_of, rules)
        ):
            problems.append(PageProblem(PROBLEM_BREAK, page_no, line_no, measured))
    return problems


def _source_breaks(source_text: str | None, kind_of: KindOf, rules: FitRules) -> _Allowed:
    """Orijinal metindeki `bad_break` konumları (aynı tanım, aynı kurallar)."""
    if source_text is None:
        return frozenset()
    return frozenset(
        (p.page, p.line)
        for page_no, (page, _separator) in enumerate(split_pages(source_text, kind_of), start=1)
        for p in _page_problems(page, page_no, kind_of, rules, frozenset())
        if p.kind == PROBLEM_BREAK
    )


def find_problems(text: str, kind_of: KindOf, rules: FitRules, source_text: str | None = None) -> list[PageProblem]:
    """Metindeki sınır ihlallerini sayfa ve satır sırasıyla döndürür.

    `source_text` (orijinal metin) verilirse, orijinalde de aynı sayfa ve satırda bulunan kısa bölünme bilinçli
    sayılır (menü, liste, şiir) ve `bad_break` olarak bildirilmez; satır ve sayfa sınırı denetimi değişmez.
    """
    allowed = _source_breaks(source_text, kind_of, rules)
    problems: list[PageProblem] = []
    for page_no, (page, _separator) in enumerate(split_pages(text, kind_of), start=1):
        problems.extend(_page_problems(page, page_no, kind_of, rules, allowed))
    return problems


@dataclass(frozen=True)
class FitResult:
    """`fit_text` sonucu. `failed`: onarılamadığı için değiştirilmeden bırakılan sayfaların 1 tabanlı numaraları."""

    text: str
    failed: tuple[int, ...]


#: Düzen maliyeti: önce gereksiz bölünmüş satır sayısı, sonra toplam puan (küçük olan iyidir).
_Cost = tuple[int, float]


def _line_cost(words: list[str], widths: list[int], end: int, line_width: int, rules: FitRules) -> _Cost:
    """`words[end - 1]` ile biten, son satır olmayan satırın maliyeti (sonraki satır `words[end]` ile başlar)."""
    last = _bare_end(words[end - 1])
    score = LINE_PENALTY + RAGGED_WEIGHT * ((rules.width - line_width) / rules.width) ** 2
    if last.endswith(tuple(_SENTENCE_END)):
        score -= SENTENCE_BONUS
    elif last.endswith(tuple(_CLAUSE_END)):
        score -= CLAUSE_BONUS
    if _bad_break_measured(line_width, last.endswith(tuple(_BREAK_PUNCTUATION)), widths[end], rules):
        return (1, score + BAD_BREAK_PENALTY)
    return (0, score)


def _best_layout(words: list[str], widths: list[int], rules: FitRules, line_counts: range) -> list[int] | None:
    """Kelimeleri satırlara bölen en ucuz düzen (her satırın bitiş indeksi) ya da sığmıyorsa `None`.

    Sert kurallar: her satır `rules.width` içinde, satır sayısı `line_counts` içinde, her satırda en az bir kelime.
    Eşit maliyette ilk bulunan seçilir; sonuç yalnızca kelimelere bağlıdır.
    """
    n = len(words)
    prefix = [0] * (n + 1)
    for i, w in enumerate(widths):
        prefix[i + 1] = prefix[i] + w

    def span(a: int, b: int) -> int:
        return prefix[b] - prefix[a] + (b - a - 1)

    # best[k][j]: ilk j kelimeyi son satır olmayan k satıra dizmenin en ucuz maliyeti ve son satırın başlangıcı.
    best: list[dict[int, tuple[_Cost, int]]] = [{0: ((0, 0.0), -1)}]
    for _k in range(1, line_counts.stop - 1):
        layer: dict[int, tuple[_Cost, int]] = {}
        for i, (cost, _prev) in best[-1].items():
            for j in range(i + 1, n):
                width = span(i, j)
                if width > rules.width:
                    break
                bad, score = _line_cost(words, widths, j, width, rules)
                total = (cost[0] + bad, cost[1] + score)
                if j not in layer or total < layer[j][0]:
                    layer[j] = (total, i)
        best.append(layer)

    choice: tuple[_Cost, int, int] | None = None
    for count in line_counts:
        for i, (cost, _prev) in best[count - 1].items():
            if span(i, n) > rules.width:
                continue
            score = LINE_PENALTY
            if count > 1:
                score += LAST_LINE_WEIGHT * ((rules.width - span(i, n)) / rules.width) ** 2
                if n - i == 1:
                    score += ORPHAN_PENALTY
            total = (cost[0], cost[1] + score)
            if choice is None or total < choice[0]:
                choice = (total, count, i)
    if choice is None:
        return None

    _total, count, start = choice
    ends = [n]
    for k in range(count - 1, 0, -1):
        ends.append(start)
        start = best[k][start][1]
    ends.reverse()
    return ends


def _edges(page: str) -> tuple[str, str]:
    """Sayfanın başındaki ve sonundaki yatay boşluk (yeniden bölünen sayfada aynen korunur)."""
    body = page.strip(" \t")
    if not body:
        return "", ""
    head = page[: len(page) - len(page.lstrip(" \t"))]
    return head, page[len(head) + len(body) :]


def _refit_page(
    page: str,
    page_no: int,
    kind_of: KindOf,
    rules: FitRules | None,
    allowed: _Allowed,
    *,
    wanted_lines: int | None = None,
) -> str | None:
    """Bir sayfayı yeniden böler; onarılamıyorsa `None`.

    `rules` yoksa (yalnızca `reflow_text`) sınır denetimi yapılmaz: `\\n`'li sayfa `wanted_lines` satıra (verilmezse
    mevcut satır sayısına), kodlu sayfa mevcut satır sayısına dengeli bölünür.

    Satırlar birleştirilip kelimelere ayrılır (boşlukla ayrılmış parçalar; içinde kod olan parça tek kelimedir, kelime
    ortasından bölünmez). Satır sonu kodlu sayfada satır sayısı kod sayısı + 1'e sabittir ve kodlar aynı sırayla kesim
    yerlerine konur; bir kodun önünde/arkasında boşluk olup olmadığı o kodun mevcut metnindeki durumundan alınır.
    Bu yerleştirme bir kodu yanındaki başka bir kodun öbür yanına geçirecekse (kod sırası değişecekse) sayfa
    onarılmaz. Diğer sayfalarda satırlar `\\n` ile ayrılır ve satır sayısı 1 ile `max_lines` arasında serbesttir.
    Sondaki `\\n`'in oluşturduğu boş son satır birleştirmede kaybolur. Sayfanın içinde boş satır (paragraf arası,
    başlık altı) ya da sekme (girinti) varsa sayfa bilinçli biçimlendirilmiştir: birleştirilmez, onarılamamış sayılır.
    Sonuç `find_problems` denetiminden temiz geçmezse de sayfa onarılamamış sayılır.
    """
    codes = [m for m in placeholders.TOKEN_RE.finditer(page) if kind_of(int(m.group(1))) == KIND_LINE_BREAK]
    if codes and "\n" in page:
        return None
    segments = split_lines(page, kind_of)
    if "\t" in page or any(not segment.strip() for segment in segments[:-1]):
        return None
    words = _words(" ".join(segments))
    if not words:
        return None
    if rules is None:
        count = len(segments) if codes or wanted_lines is None else min(wanted_lines, len(words))
        parts = _balanced_parts(words, count)
        if parts is None:
            return None
        lines = parts
    else:
        widths = [visible_width(w, kind_of, rules) for w in words]
        if max(widths) > rules.width:
            return None
        if codes:
            if len(segments) > rules.max_lines:
                return None
            line_counts = range(len(segments), len(segments) + 1)
        else:
            line_counts = range(1, rules.max_lines + 1)
        ends = _best_layout(words, widths, rules, line_counts)
        if ends is None:
            return None
        lines = [" ".join(words[a:b]) for a, b in zip([0, *ends], ends, strict=False)]
    head, tail = _edges(page)
    if codes:
        parts = [head, lines[0]]
        for m, line in zip(codes, lines[1:], strict=True):
            before = " " if page[m.start() - 1 : m.start()].isspace() else ""
            after = " " if page[m.end() : m.end() + 1].isspace() else ""
            parts.append(before + m.group(0) + after + line)
        result = "".join(parts) + tail
    else:
        result = head + "\n".join(lines) + tail
    # Kodlar yalnızca kendi aralarında değil, yanlarındaki diğer kodlara göre de aynı sırada kalmalı (§4.3).
    if placeholders.tokens_in(result) != placeholders.tokens_in(page):
        return None
    if rules is not None and _page_problems(result, page_no, kind_of, rules, allowed):
        return None
    return result


def fit_text(text: str, kind_of: KindOf, rules: FitRules, source_text: str | None = None) -> FitResult:
    """Sorunlu sayfaları (`find_problems` en az bir sorun buluyorsa) yeniden böler.

    Sorunsuz sayfalar ve tüm sayfa sonu kodları bayt bayt aynen kalır; hiçbir sayfa değişmezse `text` nesnesinin
    kendisi döner. Onarılamayan sayfa (bir kelime satıra sığmıyor, gereken satır sayısı `max_lines`'ı aşıyor, aynı
    sayfada hem `\\n` hem satır sonu kodu var, sayfanın içinde boş satır ya da sekme var, kod sırası değişecek)
    değişmez ve numarası `failed`e yazılır; böyle sayfalar model ya da elle düzeltmeye kalır.
    Onarılan sayfa `find_problems` denetiminden temiz geçer; bu yüzden işlem
    idempotenttir: `fit_text(fit_text(x).text) == fit_text(x)`.

    Sondaki `\\n`, `find_problems`'taki gibi boş bir son satır sayılır. Sayfa sorunluysa (ör. yalnızca bu boş satır
    yüzünden `max_lines` aşılıyorsa) yeniden bölmede bu boş satır kalkar; sayfa sorunsuzsa olduğu gibi kalır.

    `source_text` verilirse sorunlar `find_problems(..., source_text)` gibi bulunur: orijinalde de olan kısa bölünme
    tek başına sayfayı sorunlu yapmaz.
    """
    allowed = _source_breaks(source_text, kind_of, rules)
    out: list[str] = []
    failed: list[int] = []
    changed = False
    for page_no, (page, separator) in enumerate(split_pages(text, kind_of), start=1):
        new_page = page
        if _page_problems(page, page_no, kind_of, rules, allowed):
            refit = _refit_page(page, page_no, kind_of, rules, allowed)
            if refit is None:
                failed.append(page_no)
            else:
                new_page = refit
                changed = changed or refit != page
        out.append(new_page + separator)
    return FitResult("".join(out) if changed else text, tuple(failed))


def reflow_text(text: str, kind_of: KindOf, rules: FitRules | None, source_text: str | None = None) -> str:
    """Her sayfanın mevcut satır sonlarını kaldırıp satırı yeniden böler (sorunlu olması gerekmez).

    Satır sonu `\\n` ya da satır sonu kodu olabilir; sayfa sonu kodları ve diğer tüm kodlar yerinde kalır, kod
    sayısı/türü/sırası değişmez (kodlu sayfada satır sayısı da sabittir). `rules` varsa sayfa sınıra göre dengeli
    bölünür; sınıra sığmayan sayfa değişmez. Yoksa `\\n`'li sayfa `source_text`teki aynı sayfanın satır sayısına
    dengeli bölünür. Bölünemeyen sayfa (içinde boş satır ya da sekme var, sözcük sayısı yetmiyor, `\\n` ile kod
    karışık) aynen kalır. Hiçbir şey değişmezse `text` nesnesinin kendisi döner.
    """
    allowed = _source_breaks(source_text, kind_of, rules) if rules is not None else frozenset()
    source_pages = split_pages(source_text, kind_of) if source_text is not None else []
    out: list[str] = []
    changed = False
    for page_no, (page, separator) in enumerate(split_pages(text, kind_of), start=1):
        wanted = len(split_lines(source_pages[page_no - 1][0], kind_of)) if page_no <= len(source_pages) else None
        body = page.rstrip("\n")
        tail = page[len(body) :]
        refit = _refit_page(body, page_no, kind_of, rules, allowed, wanted_lines=wanted) if body.strip() else None
        new_page = page if refit is None else refit + tail
        changed = changed or new_page != page
        out.append(new_page + separator)
    return "".join(out) if changed else text
