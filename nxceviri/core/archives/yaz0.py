"""Yaz0 (Nintendo LZ77 türevi) açma ve sıkıştırma.

Başlık: "Yaz0" | açılmış boyut u32 (big-endian) | hizalama u32 | 4 bayt ayrılmış.
Veri: her grup bir bayraklar baytıyla başlar; 1 bit = düz bayt, 0 bit = geri başvuru
(2 bayt: uzunluk-2 üst 4 bit ve mesafe-1 alt 12 bit; uzunluk 0 ise üçüncü bayt + 0x12).
Ayrıntılar: docs/formats/archives.md
"""

from __future__ import annotations

import struct

from nxceviri.core.errors import ArchiveError

MAGIC = b"Yaz0"
HEADER_SIZE = 0x10


def decompressed_size(data: bytes) -> int:
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise ArchiveError("Yaz0 verisi geçersiz: imza yok.")
    return int(struct.unpack_from(">I", data, 4)[0])


def header_alignment(data: bytes) -> int:
    """Başlıktaki hizalama alanı (yeniden sıkıştırırken korunur)."""
    decompressed_size(data)
    return int(struct.unpack_from(">I", data, 8)[0])


def decompress(data: bytes, max_size: int) -> bytes:
    """Yaz0 verisini açar. Açılmış boyut `max_size`'ı aşarsa hata verir."""
    size = decompressed_size(data)
    if size > max_size:
        raise ArchiveError(f"Yaz0 verisi çok büyük ({size:,} bayt); bu aşamada atlanıyor.")
    out = bytearray(size)
    src = HEADER_SIZE
    dst = 0
    try:
        while dst < size:
            flags = data[src]
            src += 1
            for bit in range(7, -1, -1):
                if dst >= size:
                    break
                if flags >> bit & 1:
                    out[dst] = data[src]
                    src += 1
                    dst += 1
                    continue
                b1 = data[src]
                b2 = data[src + 1]
                src += 2
                dist = ((b1 & 0x0F) << 8 | b2) + 1
                length = b1 >> 4
                if length == 0:
                    length = data[src] + 0x12
                    src += 1
                else:
                    length += 2
                start = dst - dist
                if start < 0 or dst + length > size:
                    raise ArchiveError("Yaz0 verisi bozuk: geçersiz geri başvuru.")
                if dist >= length:
                    out[dst : dst + length] = out[start : start + length]
                else:
                    for k in range(length):
                        out[dst + k] = out[start + k]
                dst += length
    except IndexError:
        raise ArchiveError("Yaz0 verisi bozuk: veri beklenenden önce bitti.") from None
    if dst != size:
        raise ArchiveError("Yaz0 verisi bozuk: açılan boyut başlıkla uyuşmuyor.")
    return bytes(out)


_WINDOW = 0x1000
_MAX_MATCH = 0xFF + 0x12
_MAX_CHAIN = 32


def compress(data: bytes, alignment: int = 0) -> bytes:
    """Yaz0 ile sıkıştırır (açgözlü LZ77, 3 baytlık hash zincirleri).

    Çıktı geçerli bir Yaz0 akışıdır; Nintendo'nun aracıyla bayt bayt aynı olması
    beklenmez (oyun yalnızca açılabilir olmasını ister).
    """
    out = bytearray(MAGIC + struct.pack(">II", len(data), alignment) + b"\0" * 4)
    chains: dict[bytes, list[int]] = {}
    pos = 0
    n = len(data)
    while pos < n:
        flag_index = len(out)
        out.append(0)
        flags = 0
        for bit in range(7, -1, -1):
            if pos >= n:
                break
            best_len, best_dist = 0, 0
            key = data[pos : pos + 3]
            if len(key) == 3:
                candidates = chains.get(key, ())
                limit = min(_MAX_MATCH, n - pos)
                for cand in reversed(candidates[-_MAX_CHAIN:]):
                    dist = pos - cand
                    if dist > _WINDOW:
                        break
                    length = 3
                    while length < limit and data[cand + length] == data[pos + length]:
                        length += 1
                    if length > best_len:
                        best_len, best_dist = length, dist
                        if length == limit:
                            break
            if best_len >= 3:
                d = best_dist - 1
                if best_len >= 0x12:
                    out += bytes([d >> 8, d & 0xFF, best_len - 0x12])
                else:
                    out += bytes([(best_len - 2) << 4 | d >> 8, d & 0xFF])
                step = best_len
            else:
                flags |= 1 << bit
                out.append(data[pos])
                step = 1
            for p in range(pos, min(pos + step, n - 2)):
                chains.setdefault(data[p : p + 3], []).append(p)
            pos += step
        out[flag_index] = flags
    return bytes(out)
