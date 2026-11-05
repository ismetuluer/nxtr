"""NSO (ExeFS içindeki çalıştırılabilir kod) açma.

Başlık: "NSO0" | sürüm u32 | ayrılmış u32 | bayraklar u32 (bit 0–2: text/ro/data LZ4 ile
sıkıştırılmış mı) | üç bölüm başlığı (0x10'dan, 16'şar bayt: dosya ofseti, bellek ofseti,
açık boyut, hizalama/bss) | ... | sıkıştırılmış boyutlar (0x60'tan, 3 × u32).

Uygulama kodu yalnızca okur; amacı oyunun kendi kodunda geçen dizgelere bakmaktır
(ör. M2 arşivlerinin oyuna özgü anahtarı). Kod çalıştırılmaz, değiştirilmez.
"""

from __future__ import annotations

import struct

import lz4.block

from nxceviri.core.container.nca import FsType, Nca
from nxceviri.core.errors import ContainerError

MAGIC = b"NSO0"
_MAX_SEGMENT = 512 * 1024 * 1024


def decompress(nso: bytes) -> bytes:
    """text + ro + data bölümlerini açılmış ve art arda eklenmiş olarak döndürür."""
    if len(nso) < 0x100 or nso[:4] != MAGIC:
        raise ContainerError("Oyun kodu (NSO) geçersiz: imza yok.")
    flags = struct.unpack_from("<I", nso, 0x0C)[0]
    out = bytearray()
    for i in range(3):
        file_off, _mem_off, size = struct.unpack_from("<III", nso, 0x10 + i * 0x10)
        packed_size = struct.unpack_from("<I", nso, 0x60 + i * 4)[0]
        if size > _MAX_SEGMENT or file_off + packed_size > len(nso):
            raise ContainerError("Oyun kodu (NSO) bozuk: bölüm dosyanın dışında.")
        raw = nso[file_off : file_off + packed_size]
        if flags & (1 << i):
            try:
                raw = lz4.block.decompress(raw, uncompressed_size=size)
            except lz4.block.LZ4BlockError as exc:
                raise ContainerError("Oyun kodu (NSO) açılamadı: LZ4 verisi bozuk.") from exc
        out += raw
    return bytes(out)


def read_main(program: Nca) -> bytes | None:
    """Program NCA'sının ExeFS'indeki `main` kodunu açılmış olarak döndürür (yoksa None)."""
    fs = program.find_section(FsType.PFS0)
    if fs is None:
        return None
    exefs = program.open_pfs0(fs)
    entry = exefs.find("main")
    if entry is None:
        return None
    return decompress(exefs.open(entry).read_all())
