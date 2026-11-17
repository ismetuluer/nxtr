"""Metin içine gömülü biçim kodları (etiketler, değişkenler) için ortak ayrıştırıcı.

Unity (TextMeshPro) ve Unreal (UMG zengin metin) gibi biçimlerde kontrol kodları metnin
kendisinde düz yazı olarak durur: `<b>`, `<color=…>`, `</>`, `{0}`, `{PlayerName}`.
`tokenize` bunları sırayla `⟦n⟧` yer tutucularına çevirir; `detokenize` geri koyar.
Süslü parantezler iç içe olabilir (`{0:plural:{} item|{} items}`); bütün ifade tek koddur. İstenirse
(`plural=True`) çoğul ifadesi ayrılır: iskeleti (`{0:plural:`, dal ayracı `|`, kapanış `}`) kod olarak kalır, dalların
metni çevrilebilir.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from nxceviri.core.formats.base import ControlCode, FormatError
from nxceviri.core.translate import placeholders


def brace_end(text: str, start: int) -> int:
    """`text[start] == "{"` için eşleşen kapanış parantezinin bir sonrasını; yoksa -1."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


#: Çoğul ifadesinin başı: `{0:plural:` (Smart Format); ardından dallar `|` ile ayrılır.
_PLURAL_OPEN = re.compile(r"\{[^{}|:<>]*:plural:")


def _plural_open_end(text: str, start: int, end: int) -> int:
    """`text[start:end]` en az iki dallı bir çoğul ifadesiyse başlığının bir sonrasını; değilse -1.

    Dal ayracı yalnızca iç içe parantezlerin dışındaki `|` sayılır; tek dallı ifade ayrılmaz (çevrilecek bir şey
    değişmez), `choose`, `cond`, `list` gibi öteki ifadeler hiç ayrılmaz.
    """
    m = _PLURAL_OPEN.match(text, start)
    if m is None:
        return -1
    i = m.end()
    while i < end - 1:
        if text[i] == "{":
            nested = brace_end(text, i)
            if nested < 0:
                return -1
            i = nested
        elif text[i] == "|":
            return m.end()
        else:
            i += 1
    return -1


#: `tokenize`'ın biçime özgü ifade tanıyıcısı: (parçalar [(metin, kod etiketi | None)], bitiş konumu) ya da None.
Expression = Callable[[str, int], tuple[list[tuple[str, str | None]], int] | None]

_XML_TAG = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9_.\-]*)(?:[\s=][^<>]*)?>\Z")


def tag_pair(raw: bytes, single: frozenset[str] = frozenset()) -> tuple[str, str] | None:
    """XML benzeri etiketin aç/kapa rolü (`paired_code` için): `<ad …>` → (ad, "open"), `</ad>` → (ad, "close").

    Aile adı küçük harfe çevrilir (`<B>` … `</b>`). Kendini kapatan `<ad/>`, `single` içindeki adlar (ör. `br`,
    `sprite`: eşi olmayan etiketler) ve etiket olmayan kodlar için None. Kaynakta eşi bulunmayan açılış ya da kapanış
    `placeholders.check` içinde zaten katı sayılır."""
    text = raw.decode("utf-8", errors="replace")
    m = _XML_TAG.match(text)
    if m is None or text.endswith("/>"):
        return None
    name = m.group(2).lower()
    if name in single or (m.group(1) and text != f"</{m.group(2)}>"):
        return None  # kapanışta öznitelik olmaz; `</b x>` gibi bir şey tanınmaz
    return (name, "close" if m.group(1) else "open")


def tokenize(
    text: str,
    tag_re: re.Pattern[str],
    label: Callable[[str], str],
    literals: tuple[str, ...] = (),
    *,
    plural: bool = False,
    expression: Expression | None = None,
) -> tuple[str, tuple[ControlCode, ...]]:
    """`literals`: etiket olmayan ama aynen korunması gereken sabit yazılar (ör. metin içi `\n`).

    `plural`: Smart Format çoğul ifadesini (`{0:plural:bir|{} tane}`) tek kod yapmak yerine ayırır; böylece dallardaki
    sözcükler çevrilebilir. İskelet kodları (başlık, her `|`, kapanış `}`) sırayla ve eksiksiz korunmak zorundadır.

    `expression(text, pos)`: `{` konumunda biçime özgü bir ifade (ör. Unreal çoğul ifadesi) tanınırsa parçaları
    (sırayla; etiket None ise düz metin, değilse o etiketle kod) ve ifadenin bittiği konum; tanınmazsa None."""
    out: list[str] = []
    codes: list[ControlCode] = []
    closers: list[int] = []  # açık çoğul ifadelerinin kapanış `}` konumları
    pos = 0
    plain_start = 0
    while pos < len(text):
        ch = text[pos]
        end = -1
        limit = closers[-1] if closers else len(text)  # çoğul ifadesinin içindeki kod, ifadenin dışına taşamaz
        if ch == "{" and expression is not None:
            found = expression(text, pos)
            if found is not None:
                pieces, end = found
                out.append(text[plain_start:pos])
                for piece, piece_label in pieces:
                    if piece_label is None:
                        out.append(piece)
                    else:
                        codes.append(ControlCode(piece.encode("utf-8"), piece_label))
                        out.append(placeholders.token(len(codes)))
                pos = plain_start = end
                continue
        if closers and pos == limit:
            end = pos + 1  # çoğul ifadesinin kapanışı
            closers.pop()
        elif closers and ch == "|":
            end = pos + 1  # dal ayracı (iç içe parantezler `brace_end` ile atlandığından hep bu ifadeye aittir)
        elif ch == "<":
            m = tag_re.match(text, pos)
            end = m.end() if m and m.end() <= limit else -1
        elif ch == "{":
            end = brace_end(text, pos)
            head = _plural_open_end(text, pos, end) if plural and end > 0 else -1
            if head > 0:
                closers.append(end - 1)
                end = head
        if end < 0:
            literal = next((lit for lit in literals if text.startswith(lit, pos)), None)
            end = pos + len(literal) if literal and pos + len(literal) <= limit else -1
        if end < 0:
            pos += 1
            continue
        out.append(text[plain_start:pos])
        tag = text[pos:end]
        codes.append(ControlCode(tag.encode("utf-8"), label(tag)))
        out.append(placeholders.token(len(codes)))
        pos = plain_start = end
    out.append(text[plain_start:])
    return "".join(out), tuple(codes)


def detokenize(display: str, codes: tuple[ControlCode, ...]) -> str:
    parts: list[str] = []
    for piece in placeholders.split(display):
        if isinstance(piece, int):
            if not 1 <= piece <= len(codes):
                raise FormatError(f"Çeviride geçersiz kontrol kodu: {placeholders.token(piece)}")
            parts.append(codes[piece - 1].raw.decode("utf-8"))
        else:
            parts.append(piece)
    return "".join(parts)
