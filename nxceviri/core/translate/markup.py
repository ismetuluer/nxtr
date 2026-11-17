"""Metin içine gömülü biçim kodları (etiketler, değişkenler) için ortak ayrıştırıcı.

Unity (TextMeshPro) ve Unreal (UMG zengin metin) gibi biçimlerde kontrol kodları metnin
kendisinde düz yazı olarak durur: `<b>`, `<color=…>`, `</>`, `{0}`, `{PlayerName}`.
`tokenize` bunları sırayla `⟦n⟧` yer tutucularına çevirir; `detokenize` geri koyar.
Süslü parantezler iç içe olabilir (`{0:plural:{} item|{} items}`); bütün ifade tek koddur.
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
    expression: Expression | None = None,
) -> tuple[str, tuple[ControlCode, ...]]:
    """`literals`: etiket olmayan ama aynen korunması gereken sabit yazılar (ör. metin içi `\\n`).

    `expression(text, pos)`: `{` konumunda biçime özgü bir ifade (ör. Unreal çoğul ifadesi) tanınırsa parçaları
    (sırayla; etiket None ise düz metin, değilse o etiketle kod) ve ifadenin bittiği konum; tanınmazsa None."""
    out: list[str] = []
    codes: list[ControlCode] = []
    pos = 0
    plain_start = 0
    while pos < len(text):
        ch = text[pos]
        end = -1
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
        if ch == "<":
            m = tag_re.match(text, pos)
            end = m.end() if m else -1
        elif ch == "{":
            end = brace_end(text, pos)
        if end < 0:
            literal = next((lit for lit in literals if text.startswith(lit, pos)), None)
            end = pos + len(literal) if literal else -1
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
