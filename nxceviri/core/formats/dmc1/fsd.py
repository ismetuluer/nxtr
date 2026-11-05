"""Devil May Cry `.fsd` kapsayıcısı: bölüm dizini ve bölüm değiştirme.

`u32 adet | 4 bayt dolgu | adet × u64 mutlak ofset | bölümler`. Ofset 0 boş girdidir; bölümler dosyada
ardışık durur, bir bölümün boyutu sonraki ofsetle (veya dosya sonuyla) bulunur. Dizin dışında bölümlerin
içinde mutlak ofset yoktur: Rusça topluluk modu bölümleri büyütüp küçülterek yalnızca dizini günceller
(docs/formats/dmc1.md), aynı yöntem burada kullanılır.
"""

from __future__ import annotations

import itertools
import struct
from collections.abc import Mapping

from nxceviri.core.formats.base import FormatError

_ALIGN = 16
_MAX_ENTRIES = 256


def _layout(wide: bool) -> tuple[int, int, str]:
    """(ilk ofsetin konumu, ofset boyutu, struct biçimi): `.fsd` u64 ofset kullanır, `st_init.dat` u32."""
    return (8, 8, "Q") if wide else (4, 4, "I")


def read_directory(data: bytes, *, wide: bool = True) -> list[int]:
    """Dizindeki ofsetler (boş girdiler 0)."""
    first, size, fmt = _layout(wide)
    if len(data) < first:
        raise FormatError("Dosya çok kısa.")
    count = struct.unpack_from("<I", data, 0)[0]
    end = first + size * count
    if not 1 <= count <= _MAX_ENTRIES or end > len(data):
        raise FormatError("Bölüm dizini bozuk.")
    offsets = list(struct.unpack_from(f"<{count}{fmt}", data, first))
    used = [o for o in offsets if o]
    if not used or min(used) < end or max(used) >= len(data):
        raise FormatError("Bölüm dizini dosya sınırları dışında.")
    return offsets


def _boundaries(offsets: list[int], size: int) -> list[int]:
    return sorted({o for o in offsets if o} | {size})


def block_range(data: bytes, offset: int, *, wide: bool = True) -> tuple[int, int]:
    """Dizinde başlangıcı `offset` olan bölümün (başlangıç, bitiş) aralığı."""
    offsets = read_directory(data, wide=wide)
    if offset not in offsets:
        raise FormatError(f"0x{offset:X} konumunda dizinde kayıtlı bir bölüm yok.")
    bounds = _boundaries(offsets, len(data))
    return offset, min(b for b in bounds if b > offset)


def replace_blocks(data: bytes, replacements: Mapping[int, bytes], *, wide: bool = True) -> bytes:
    """Verilen bölümleri yenileriyle değiştirir, sonraki bölümleri kaydırır ve dizini günceller.

    Yeni bölümler 16 bayta tamamlanır (son bölüm hariç). Dosyanın geri kalanı bayt bayt aynı kalır.
    """
    offsets = read_directory(data, wide=wide)
    first, size, fmt = _layout(wide)
    bounds = _boundaries(offsets, len(data))
    out = bytearray(data[: bounds[0]])
    shift = 0
    new_offset: dict[int, int] = {}
    for start, end in itertools.pairwise(bounds):
        new_offset[start] = start + shift
        if start in replacements:
            block = bytes(replacements[start])
            if end != len(data):
                block += bytes(-len(block) % _ALIGN)
            out += block
            shift += len(block) - (end - start)
        else:
            out += data[start:end]
    for i, old in enumerate(offsets):
        if old:
            struct.pack_into(f"<{fmt}", out, first + size * i, new_offset[old])
    missing = [hex(o) for o in replacements if o not in new_offset]
    if missing:
        raise FormatError(f"Dizinde olmayan bölümler değiştirilemez: {', '.join(missing)}")
    return bytes(out)
