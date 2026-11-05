"""Test için elle üretilmiş küçük Yacht Club YCD dosyaları (gerçek oyun verisi içermez)."""

from __future__ import annotations

import struct

MAGIC = b"YCD\0"
LANGUAGES = ["English", "French", "Italian", "German", "Spanish"]
UI_HEADER = ["ID", *LANGUAGES]
DIALOGUE_HEADER = ["ID", "Speaker", "Trigger", "Branch", *LANGUAGES]
NAMES_HEADER = ["ID", "Speaker", "Gender", *LANGUAGES]


def block(cells: list[str]) -> bytes:
    """Bir satırın betimleyicileri ve hemen ardından kendi dizgi havuzu.

    Aynı dizgi ikinci kez geçerse havuzda tekrar yazılmaz, ilk kopyayı gösterir.
    """
    width = len(cells)
    pool = bytearray()
    where: dict[str, int] = {}
    for text in cells:
        if text and text not in where:
            where[text] = width * 16 + len(pool)
            pool += text.encode("utf-8") + b"\0"
    out = bytearray()
    for i, text in enumerate(cells):
        pos = i * 16
        rel = where[text] - (pos + 8) if text else -1
        kind = 0xFFFFFE00 if i == width - 1 else 0x10
        out += struct.pack("<IIIi", 0, len(text.encode("utf-8")), kind, rel)
    out += pool
    out += b"\0" * (-len(out) % 4)
    return bytes(out)


def table(header: list[str], rows: list[list[str]]) -> bytes:
    return block(header) + b"".join(block(r) for r in rows)


def ycd(*tables: bytes) -> bytes:
    return MAGIC + b"\0" * 60 + b"".join(tables)
