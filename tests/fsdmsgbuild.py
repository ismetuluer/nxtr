"""Test için elle üretilmiş küçük Devil May Cry mesaj tabloları (gerçek oyun verisi içermez)."""

from __future__ import annotations

import struct

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_PUNCT = {".": 0x43, ",": 0x44, ":": 0x45, "!": 0x4A, "?": 0x4B, "'": 0x0D, "-": 0x4F}


def text(s: str) -> bytes:
    """Düz İngilizce metni oyun baytlarına çevirir (boşluk 7E 05, satır sonu 7E 0C)."""
    out = bytearray()
    for ch in s:
        if ch == " ":
            out += b"\x7e\x05"
        elif ch == "\n":
            out += b"\x7e\x0c"
        elif ch.isdigit():
            out.append(int(ch))
        elif ch in _LETTERS:
            out.append(0x0E + _LETTERS.index(ch))
        elif ch in _LOWER:
            out.append(0x28 + _LOWER.index(ch))
        else:
            out.append(_PUNCT[ch])
    return bytes(out)


def message(s: str, *, pad: int = 4) -> bytes:
    """Bir dizgi: metin + `7E 0E 00 50` bitişi + sıfır dolgusu."""
    return text(s) + b"\x7e\x0e\x00\x50" + b"\0" * pad


def table(strings: list[bytes], *, align: bool = True) -> bytes:
    n = len(strings)
    base = 4 + 8 * n
    pos = (base + 15) & ~15 if align else base
    head = struct.pack("<I", n)
    body = b""
    for s in strings:
        head += struct.pack("<II", pos + len(body), len(s))
        body += s
    return (head + b"\0" * (pos - len(head))) + body


ENGLISH_SLOT = 23


def fsd(english: bytes, *, others: dict[int, bytes] | None = None, slots: int = 35) -> bytes:
    """`.fsd` kapsayıcısı: dizin + ardışık 16 bayta hizalı bölümler; 23. bölüm İngilizce tablodur."""
    blocks = {i: bytes([0x55 + i]) * 48 for i in (0, 1, 22, 24, 30)}
    blocks.update(others or {})
    blocks[ENGLISH_SLOT] = english
    head = 8 + 8 * slots
    offsets = [0] * slots
    body = bytearray()
    for slot in sorted(blocks):
        body += bytes(-(head + len(body)) % 16)
        offsets[slot] = head + len(body)
        body += blocks[slot]
    return struct.pack("<I4s", slots, bytes([0xCC]) * 4) + struct.pack(f"<{slots}Q", *offsets) + bytes(body)
