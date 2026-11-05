"""Model çıktısının temizlenmesi: özgünde olmayan fazlalıkları atar, sona yığılmış satır sonu kodlarını yerleştirir.

Yerel modeller (ör. gemma) redaksiyonda bazen metne özgünde olmayan şeyler ekler veya kodların yerini bozar.
Subtitle Workshop'taki "hataları düzelt" seçeneklerinin bu programdaki karşılığıdır; her model sonucuna
yazılmadan önce, Kontrol Et'te satır denetimi düzeltmeleriyle de var olan çevirilere uygulanır:

- **Fazla biçim etiketi:** `<div>`, `</p>`, `<br/>`, `<b>` gibi özgünde geçmeyen HTML/XML etiketleri ve
  `&nbsp;` gibi varlıklar atılır (özgünde aynen geçenlere dokunulmaz).
- **Uydurma kod:** özgünde olmayan `⟦n⟧` ile özgündekinden fazla tekrarlanan kodlar atılır.
- **Sona yığılmış satır sonu kodları:** özgünde metnin ortasında duran satır sonu kodları çeviride hepsi en
  sona konmuşsa, metin sözcük sınırlarından özgündeki satır oranlarına göre bölünüp kodlar araya yerleştirilir.

Temizlik anlamı değiştirmez; sonuç her zaman ayrıca denetlenir (kontrol kodu, uzunluk …).
"""

from __future__ import annotations

import html
import re
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise

from nxceviri.core.translate import placeholders

#: HTML/XML biçim etiketi: <div>, </div>, <br/>, <span class="x">.
_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9:_-]*(?:\s[^<>]*)?/?>")
#: Adlı veya sayısal HTML varlığı: &nbsp; &amp; &#8217;
_ENTITY_RE = re.compile(r"&(?:[A-Za-z]+|#\d+|#x[0-9A-Fa-f]+);")
_SPACES_RE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r" +([.,!?;:…])")


def is_line_break(label: str) -> bool:
    return "satır sonu" in label.casefold()


def foreign_markup(source: str, text: str) -> list[str]:
    """Çeviride geçip özgünde geçmeyen etiket ve varlıklar (sırayla, tekrarsız)."""
    found = [m.group(0) for r in (_TAG_RE, _ENTITY_RE) for m in r.finditer(text)]
    return list(dict.fromkeys(x for x in found if x not in source))


def strip_markup(source: str, text: str) -> str:
    for item in foreign_markup(source, text):
        if _ENTITY_RE.fullmatch(item):
            text = text.replace(item, html.unescape(item).replace("\xa0", " "))
        else:
            text = text.replace(item, " " if item.lower().startswith(("<br", "</p", "</div")) else "")
    return text


def drop_invented_codes(source: str, text: str) -> str:
    """Özgünde olmayan kodları ve özgündekinden fazla tekrarları atar (ilk geçişler kalır)."""
    allowed = Counter(placeholders.tokens_in(source))
    seen: Counter[int] = Counter()

    def keep(m: re.Match[str]) -> str:
        n = int(m.group(1))
        seen[n] += 1
        return m.group(0) if seen[n] <= allowed[n] else ""

    return placeholders.TOKEN_RE.sub(keep, text)


def split_words(text: str, weights: Sequence[float]) -> list[str] | None:
    """Metni sözcük sınırlarından `len(weights)` parçaya, uzunlukları ağırlıklarla orantılı olacak biçimde böler.

    Her parçada en az bir sözcük olur; sözcük yetmezse None.
    """
    words = text.split()
    parts = len(weights)
    if parts < 1 or len(words) < parts:
        return None
    starts = []
    pos = 0
    for w in words:
        starts.append(pos)
        pos += len(w) + 1
    total = max(pos - 1, 1)
    if sum(weights) <= 0:
        weights = [1.0] * parts
    weight_sum = float(sum(weights))
    cuts: list[int] = []
    acc = 0.0
    prev = 0
    for k in range(1, parts):
        acc += weights[k - 1]
        target = total * acc / weight_sum
        lo, hi = prev + 1, len(words) - (parts - k)
        best = min(range(lo, hi + 1), key=lambda j: abs(starts[j] - 0.5 - target))  # araya düşen boşluğun yeri
        cuts.append(best)
        prev = best
    bounds = [0, *cuts, len(words)]
    return [" ".join(words[a:b]) for a, b in pairwise(bounds)]


def _visible_len(text: str) -> int:
    return len(placeholders.TOKEN_RE.sub("", text).strip())


_TAIL_RE = re.compile(r"(?:\s*⟦\d+⟧)+\s*$")


def _mid_breaks(source: str, labels: Sequence[str]) -> tuple[list[int], list[float]]:
    """Özgünde metnin ortasında duran satır sonu kodları ve aralarındaki metin parçalarının uzunlukları."""
    pieces = placeholders.split(source)
    mid: list[int] = []
    weights: list[float] = []
    segment = 0
    for i, piece in enumerate(pieces):
        if isinstance(piece, str):
            segment += len(piece.strip())
            continue
        later_text = any(isinstance(p, str) and p.strip() for p in pieces[i + 1 :])
        if 0 < piece <= len(labels) and is_line_break(labels[piece - 1]) and later_text and segment:
            mid.append(piece)
            weights.append(segment)
            segment = 0
    weights.append(segment)
    return mid, weights


def spread_trailing_breaks(source: str, text: str, labels: Sequence[str]) -> str | None:
    """Özgünde metin ortasındaki satır sonu kodları çeviride en sona yığılmışsa yerlerine dağıtır; yoksa None.

    Kodların yalnızca bir kısmı sona yığılmışsa (biri ortada kalmış) dokunulmaz: ortadakinin yeri de büyük
    olasılıkla yanlıştır ve oranla bölmek cümleyi bozar; bu durum denetimde "Kod yeri" olarak gösterilir.
    """
    mid, weights = _mid_breaks(source, labels)
    if not mid:
        return None
    tail = _TAIL_RE.search(text)
    if tail is None:
        return None
    trailing = placeholders.tokens_in(tail.group(0))
    body = text[: tail.start()]
    if any(n in placeholders.tokens_in(body) for n in mid) or not all(n in trailing for n in mid):
        return None
    if placeholders.tokens_in(body):
        return None  # gövdede başka kodlar var; sözcüklere bölmek onların yerini bozabilir
    lines = split_words(body, weights)
    if lines is None:
        return None

    def glue(n: int) -> tuple[str, str]:
        tok = placeholders.token(n)
        at = source.index(tok)
        before = " " if at > 0 and source[at - 1] == " " else ""
        after = " " if source[at + len(tok) : at + len(tok) + 1] == " " else ""
        return before, after

    out = lines[0]
    for n, line in zip(mid, lines[1:], strict=True):
        before, after = glue(n)
        out += f"{before}{placeholders.token(n)}{after}{line}"
    rest = [n for n in trailing if n not in mid]
    out += "".join(placeholders.token(n) for n in rest)
    lead = text[: len(text) - len(text.lstrip())]
    return lead + out


#: Tekrarlanan noktalama: `.` `!` `?` dizileri 3'ten uzunsa 3'e, `,` `;` `:` dizileri 2+ ise 1'e iner.
_LONG_RUN_RE = re.compile(r"([.!?])\1{3,}")
_COMMA_RUN_RE = re.compile(r"([,;:])\1+")


def _collapse_runs(source: str, text: str, pattern: re.Pattern[str], target: int, min_source_run: int) -> str:
    """Tekrar dizilerini `target` uzunluğuna indirir; özgünde aynı karakterin yeterince uzun dizisi varsa dokunmaz."""

    def shrink(m: re.Match[str]) -> str:
        char = m.group(1)
        if re.search(f"{re.escape(char)}{{{min_source_run},}}", source):
            return m.group(0)
        return char * target

    return pattern.sub(shrink, text)


def tidy_punctuation(
    source: str, text: str, *, spaces: bool = True, before_punct: bool = True, repeated: bool = True
) -> str:
    """Çift boşluk, noktalamadan önceki boşluk ve tekrarlı noktalamayı toplar (özgünde öyle değilse).

    Kontrol kodlarına (`⟦n⟧`) dokunulmaz: yalnızca noktalama karakterleri eşleştirilir.
    """
    if spaces and not _SPACES_RE.search(source):
        text = _SPACES_RE.sub(" ", text)
    if before_punct and not _SPACE_BEFORE_PUNCT_RE.search(source):
        text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    if repeated:
        text = _collapse_runs(source, text, _LONG_RUN_RE, 3, 3)
        text = _collapse_runs(source, text, _COMMA_RUN_RE, 1, 2)
    return text


def tidy_spaces(source: str, text: str) -> str:
    """Temizlikten kalan çift boşlukları ve noktalamadan önceki boşluğu toplar (özgünde öyle değilse)."""
    return tidy_punctuation(source, text, repeated=False)


def clean_output(source: str, text: str, labels: Sequence[str] = ()) -> str:
    """Tüm temizlik adımları; değişecek bir şey yoksa metni aynen döndürür."""
    cleaned = strip_markup(source, text)
    cleaned = drop_invented_codes(source, cleaned)
    cleaned = spread_trailing_breaks(source, cleaned, labels) or cleaned
    if cleaned == text:
        return text
    return tidy_spaces(source, cleaned)


def misplaced_breaks(source: str, text: str, labels: Sequence[str]) -> bool:
    """Denetim için: özgünde cümlenin ortasındaki satır sonu kodlarından biri çeviride en sona mı konmuş?"""
    mid, _weights = _mid_breaks(source, labels)
    tail = _TAIL_RE.search(text)
    if not mid or tail is None or _visible_len(text) == 0:
        return False
    return any(n in placeholders.tokens_in(tail.group(0)) for n in mid)


#: Cümle sonu ve ara noktalama işaretleri (orijinalde yoksa çeviride fazla sayılır). Virgül ve tırnak sayılmaz:
#: Türkçe cümle yapısı bunları doğal olarak değiştirir.
END_PUNCTUATION = ".!?…:;"
#: Sondaki noktalama dizisi; ardından yalnızca boşluk ve kontrol kodu gelebilir.
_END_PUNCT_RE = re.compile(rf"([{re.escape(END_PUNCTUATION)}]+)((?:\s|⟦\d+⟧)*)$")
#: Sondaki kapanış işaretleri: noktalama bunların içinde de olabilir (“Koş.”).
_CLOSERS = "\"'”’»)]」』"


def _tail_text(text: str) -> str:
    return placeholders.TOKEN_RE.sub("", text).rstrip().rstrip(_CLOSERS).rstrip()


def added_end_punctuation(source: str, text: str) -> str:
    """Çevirinin sonuna eklenmiş, orijinalin sonunda olmayan noktalama ("Start Game" → "Oyunu Başlat."); yoksa ""."""
    tail = _tail_text(source)
    if tail and tail[-1] in END_PUNCTUATION:
        return ""
    m = _END_PUNCT_RE.search(text)
    return m.group(1) if m else ""


def strip_added_end_punctuation(source: str, text: str) -> str:
    """`added_end_punctuation` varsa onu atar; sondaki boşluk ve kontrol kodları kalır."""
    if not added_end_punctuation(source, text):
        return text
    return _END_PUNCT_RE.sub(lambda m: m.group(2), text)


#: Çeviride kalması beklenen ham etiketler: HTML/XML etiketi, bilinen BBCode etiketi, `{değişken}`.
#: `[Laughs]` gibi köşeli parantezli düz metin etiket sayılmaz.
_BBCODE_TAGS = "b|i|u|s|color|colour|size|font|url|img|center|quote|align|sprite"
_KEEP_MARKUP_RE = re.compile(
    rf"</?[A-Za-z][A-Za-z0-9:_-]*(?:\s[^<>]*|=[^<>]*)?/?>|\[/?(?:{_BBCODE_TAGS})(?:=[^\]\s]*)?\]|\{{[A-Za-z0-9_.:]+\}}",
    re.IGNORECASE,
)


def missing_markup(source: str, text: str) -> list[str]:
    """Özgünde geçip çeviride eksik kalan ham etiketler (sayıma göre; sırayla, her eksik için bir kez)."""
    have = Counter(m.group(0) for m in _KEEP_MARKUP_RE.finditer(text))
    out: list[str] = []
    for m in _KEEP_MARKUP_RE.finditer(source):
        tag = m.group(0)
        if have[tag] > 0:
            have[tag] -= 1
        elif tag not in out:
            out.append(tag)
    return out


#: Çeviride kod adı gibi korunması gereken ifade: `Barrel_Cannon`, `DK_Coin`.
_PROTECTED_RE = re.compile(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+")


def missing_protected(source: str, text: str) -> list[str]:
    """Özgün cümlenin içinde geçen alt çizgili kod adlarından çeviride aynen bulunmayanlar (tekrarsız).

    Kaynağın tamamı tek bir kod adıysa boş döner: o durumu "Kod adı" denetimi bildirir.
    """
    if _PROTECTED_RE.fullmatch(source.strip()):
        return []
    return [name for name in dict.fromkeys(_PROTECTED_RE.findall(source)) if name not in text]


#: Kodlara ve satır sonuna bitişik olmayan, iki yanı görünür karakter olan çoklu boşluk.
_INNER_SPACES_RE = re.compile(r"(?<=[^\s⟧]) {2,}(?=[^\s⟦])")


def collapse_inner_spaces(source: str, text: str) -> str:
    """Metnin içindeki çoklu boşluğu tek boşluğa indirir (kaynakta da varsa, kod/satır sonu yanındaysa dokunmaz)."""
    if _INNER_SPACES_RE.search(source):
        return text
    return _INNER_SPACES_RE.sub(" ", text)


#: Art arda tekrarı yazım hatası sayılan işlev sözcükleri. Öbür tekrarlar ("güle güle", "hemen hemen", "bol bol")
#: Türkçede çoğunlukla kasıtlı ikilemedir; bu yüzden yalnızca bu küçük liste yakalanır.
_FUNCTION_WORDS = frozenset({"ve", "bir", "bu", "şu", "o", "de", "da", "ile", "için", "ama", "gibi"})
_WORD_RE = re.compile(r"[^\W\d_]+")


def _repeated_runs(text: str) -> list[tuple[int, int, int]]:
    """Aralarında yalnızca boşluk olan, aynı sözcüğün (harf duyarsız) ardışık dizileri: (başlangıç, bitiş, sayı)."""
    words = [(m.start(), m.end(), m.group(0).casefold()) for m in _WORD_RE.finditer(text)]
    runs: list[tuple[int, int, int]] = []
    i = 0
    while i < len(words):
        j = i
        while (
            j + 1 < len(words) and words[j + 1][2] == words[i][2] and set(text[words[j][1] : words[j + 1][0]]) == {" "}
        ):
            j += 1
        if j > i:
            runs.append((words[i][0], words[j][1], j - i + 1))
        i = j + 1
    return runs


def drop_repeated_words(source: str, text: str) -> str:
    """Art arda yazılmış iki aynı işlev sözcüğünden ikincisini atar ("ve ve" → "ve").

    Yalnızca `_FUNCTION_WORDS` içindeki sözcükler; 3+ tekrar ("ha ha ha") ve özgünde de art arda tekrar bulunan metin
    kasıtlı sayılır, dokunulmaz.
    """
    if _repeated_runs(source):
        return text
    out = text
    for a, b, n in reversed(_repeated_runs(text)):
        first = text[a:b].split(maxsplit=1)[0]
        if n == 2 and first.casefold() in _FUNCTION_WORDS:
            out = out[:a] + first + out[b:]
    return out


_TWO_DOTS_RE = re.compile(r"(?<!\.)\.{2}(?!\.)")
_LONG_DOTS_RE = re.compile(r"\.{4,}")


def fix_extra_dots(source: str, text: str) -> str:
    """4+ noktayı ve özgünde olmayan ".." yı "..." yapar (özgünde "…" varsa "…"); özgünde aynısı varsa dokunmaz."""
    ellipsis = "…" if "…" in source else "..."
    if not _LONG_DOTS_RE.search(source):
        text = _LONG_DOTS_RE.sub(ellipsis, text)
    if not _TWO_DOTS_RE.search(source):
        text = _TWO_DOTS_RE.sub(ellipsis, text)
    return text


def tidy_text(source: str, text: str, *, spaces: bool = True, dots: bool = True) -> str:
    """Metin temizliği: iç çoklu boşluk (`spaces`), art arda tekrar eden sözcük, fazla nokta (`dots`)."""
    if spaces:
        text = collapse_inner_spaces(source, text)
    text = drop_repeated_words(source, text)
    return fix_extra_dots(source, text) if dots else text
