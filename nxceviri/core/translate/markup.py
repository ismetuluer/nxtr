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


def tokenize(
    text: str,
    tag_re: re.Pattern[str],
    label: Callable[[str], str],
    literals: tuple[str, ...] = (),
) -> tuple[str, tuple[ControlCode, ...]]:
    """`literals`: etiket olmayan ama aynen korunması gereken sabit yazılar (ör. metin içi `\\n`)."""
    out: list[str] = []
    codes: list[ControlCode] = []
    pos = 0
    plain_start = 0
    while pos < len(text):
        ch = text[pos]
        end = -1
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
