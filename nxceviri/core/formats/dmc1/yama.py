"""Devil May Cry HD Collection (PC) topluluk Türkçe yamasını okuma: `fsd_tr.yama` ve `common.msg`.

Yama dosyası (`D1FS`): `"D1FS" | u32 dosya sayısı | dosya × { u16 ad uzunluğu, ad, u32 yama sayısı,
yama × { u32 ofset, u32 boyut, veri } }`. Her yama, oyunun `.fsd` dosyasındaki İngilizce mesaj tablosunun
(23. bölüm) üzerine yerinde yazılır; Switch ve PC sürümlerinin `.fsd` dosyaları aynı düzendedir
(docs/formats/dmc1.md), bu yüzden metin satır sırasıyla eşleşir. Yalnızca metin okunur: yamadaki
font ve görüntü dosyaları kullanılmaz.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.dmc1 import codec, fsd

MAGIC = b"D1FS"


@dataclass(frozen=True)
class YamaTable:
    file: str  # "r002.fsd"
    texts: tuple[str, ...]  # Türkçe metinler (⟦n⟧ yer tutuculu), dizgi sırasıyla


def _first_table(block: bytes) -> codec.MessageTable | None:
    for pos in range(0, max(0, len(block) - 8), 4):
        table = codec.parse_table(block, pos)
        if table is not None:
            return table
    return None


def read_yama(data: bytes) -> list[YamaTable]:
    """Yama dosyasındaki mesaj tablolarını (dosya başına en çok bir) okur; tablo olmayan yamalar atlanır."""
    if data[:4] != MAGIC:
        raise FormatError("Bu bir Devil May Cry yama dosyası (D1FS) değil.", "fsd_tr.yama dosyasını seçin.")
    out: list[YamaTable] = []
    try:
        files = struct.unpack_from("<I", data, 4)[0]
        pos = 8
        for _ in range(files):
            (name_len,) = struct.unpack_from("<H", data, pos)
            name = data[pos + 2 : pos + 2 + name_len].decode("ascii")
            pos += 2 + name_len
            (patches,) = struct.unpack_from("<I", data, pos)
            pos += 4
            found: codec.MessageTable | None = None
            block_of: bytes = b""
            for _ in range(patches):
                _offset, size = struct.unpack_from("<II", data, pos)
                pos += 8
                block = data[pos : pos + size]
                pos += size
                table = _first_table(block) if found is None else None
                if table is not None:
                    found, block_of = table, block
            if found is not None:
                texts = tuple(codec.decode(block_of[o : o + n]).text for o, n in found.strings)
                out.append(YamaTable(name.rsplit("/", 1)[-1], texts))
    except (struct.error, UnicodeDecodeError):
        raise FormatError("Yama dosyası bozuk veya eksik.", "Yamanın indirmesini yeniden yapın.") from None
    return out


def read_status_file(data: bytes, name: str) -> YamaTable:
    """`status_e/st_init.dat`: u32 dizinli dosyanın 0. bölümündeki mesaj tablosu."""
    try:
        offsets = fsd.read_directory(data, wide=False)
    except FormatError:
        raise FormatError(f"'{name}' bir Devil May Cry durum dosyası değil.") from None
    table = codec.parse_table(data, offsets[0])
    if table is None:
        raise FormatError(f"'{name}' içinde mesaj tablosu yok.")
    return YamaTable(name, tuple(codec.decode(data[o : o + n]).text for o, n in table.strings))


def read_message_file(data: bytes, name: str) -> YamaTable:
    """Tek başına bir `.msg` dosyası (ör. `Etc_e/common.msg`)."""
    table = codec.parse_table(data, 0)
    if table is None:
        raise FormatError(f"'{name}' bir mesaj dosyası değil.")
    return YamaTable(name, tuple(codec.decode(data[o : o + n]).text for o, n in table.strings))
