"""Falcom NNI arşivi (Ys Origin): `.ni` dizini + `.na` veri dosyası.

Dizin (`.ni`):
- Başlık 16 bayt: `NNI\\0` | girdi sayısı u32 | ad tablosu boyutu u32 | bayraklar u32.
- Girdi tablosu (sayı × 16 bayt): ad özeti u32 | boyut u32 | `.na` içindeki ofset u32 | ad ofseti u32.
- Ad tablosu: sıfırla biten CP932 adlar (`LOC\\EN\\DATA\\MAP\\…\\X.XSO.Z`).
- Girdi ve ad tabloları ayrı ayrı karıştırılmıştır: her bayttan, her adımda 0x3D09 ile çarpılan
  32 bitlik bir sayacın (başlangıç 0x7C53F961) 16.–23. bitleri çıkarılır.

Adı `.Z` ile biten üyeler zlib ile sıkıştırılmıştır: CRC32 u32 | açık boyut u32 | zlib akışı.

Yazma: orijinal `.na` olduğu gibi kopyalanır, değişen üyeler sonuna eklenir ve dizindeki ofset/boyut
alanları yeni yerleri gösterir. Adlar ve özetler değişmez. Ayrıntılar: docs/formats/ys-origin.md
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from nxceviri.core.container.storage import Storage
from nxceviri.core.errors import ArchiveError

MAGIC = b"NNI\0"
INDEX_SUFFIX = ".ni"
DATA_SUFFIX = ".na"
_HEADER = struct.Struct("<4sIII")
_ENTRY = struct.Struct("<IIII")
_SEED = 0x7C53F961
_MULTIPLIER = 0x3D09
_COMPRESSED = ".Z"
#: Bir üyenin açılmış hâli için üst sınır (bellek koruması).
MAX_MEMBER = 64 * 1024 * 1024


def _keystream(n: int) -> bytes:
    k = _SEED
    out = bytearray(n)
    for i in range(n):
        k = (k * _MULTIPLIER) & 0xFFFFFFFF
        out[i] = (k >> 16) & 0xFF
    return bytes(out)


def descramble(data: bytes) -> bytes:
    ks = _keystream(len(data))
    return bytes((b - k) & 0xFF for b, k in zip(data, ks, strict=True))


def scramble(data: bytes) -> bytes:
    ks = _keystream(len(data))
    return bytes((b + k) & 0xFF for b, k in zip(data, ks, strict=True))


def name_hash(raw_name: bytes) -> int:
    """Dizindeki ad özeti (oyunun dosya arama işlevi)."""
    return sum((b - 32) << (i % 5 * 5) for i, b in enumerate(raw_name)) % 0xFFF1


def data_name(index_path: str) -> str:
    return index_path[: -len(INDEX_SUFFIX)] + DATA_SUFFIX


def is_index(path: str, head: bytes) -> bool:
    return path.lower().endswith(INDEX_SUFFIX) and head.startswith(MAGIC)


@dataclass(frozen=True)
class NniEntry:
    name: str  # "/" ile ayrılmış, ".Z" eki atılmış ad (ör. "LOC/EN/DATA/MAP/S_00/S_0003/EVT.XSO")
    slot: int  # girdi tablosundaki sıra
    offset: int
    size: int
    compressed: bool


class NniArchive:
    def __init__(self, name: str, index: bytes, data: Storage) -> None:
        self.name = name
        self._index = index
        self._data = data
        if len(index) < _HEADER.size:
            raise ArchiveError(f"{name} bozuk: dizin başlığı eksik.")
        magic, count, names_size, flags = _HEADER.unpack_from(index)
        if magic != MAGIC:
            raise ArchiveError(f"{name} bir NNI dizini değil.")
        if flags & 1:
            raise ArchiveError(f"{name}: artımlı (incremental) NNI dizinleri desteklenmiyor.")
        toc_end = _HEADER.size + count * _ENTRY.size
        if toc_end + names_size != len(index):
            raise ArchiveError(f"{name} bozuk: dizin boyutu başlıkla uyuşmuyor.")
        self._toc = bytearray(descramble(index[_HEADER.size : toc_end]))
        self._names = index[toc_end:]
        names = descramble(self._names)
        self.entries: dict[str, NniEntry] = {}
        for slot in range(count):
            _hash, size, offset, name_off = _ENTRY.unpack_from(self._toc, slot * _ENTRY.size)
            end = names.find(b"\0", name_off)
            if end < 0:
                raise ArchiveError(f"{name} bozuk: ad tablosu sonlanmamış.")
            raw = names[name_off:end].decode("cp932", errors="replace").replace("\\", "/")
            compressed = raw.upper().endswith(_COMPRESSED)
            member = raw[: -len(_COMPRESSED)] if compressed else raw
            if (offset, size) == (0, 0):
                continue  # oyunun boş bıraktığı kayıt
            if offset + size > data.size:
                raise ArchiveError(f"{name} bozuk: '{member}' veri dosyasının dışına taşıyor.")
            self.entries[member] = NniEntry(member, slot, offset, size, compressed)

    def read(self, member: str) -> bytes:
        entry = self.entries.get(member)
        if entry is None:
            raise ArchiveError(f"{self.name} içinde '{member}' yok.")
        raw = self._data.read(entry.offset, entry.size)
        if not entry.compressed:
            return raw
        if len(raw) < 8:
            raise ArchiveError(f"{self.name}: '{member}' sıkıştırma başlığı eksik.")
        crc, size = struct.unpack_from("<II", raw)
        if size > MAX_MEMBER:
            raise ArchiveError(f"{self.name}: '{member}' çok büyük ({size:,} bayt).")
        try:
            out = zlib.decompress(raw[8:])
        except zlib.error as exc:
            raise ArchiveError(f"{self.name}: '{member}' açılamadı ({exc}).") from None
        if len(out) != size or zlib.crc32(out) != crc:
            raise ArchiveError(f"{self.name}: '{member}' açıldı ama denetim toplamı tutmuyor.")
        return out

    def rebuild(self, changes: dict[str, bytes]) -> tuple[bytes, bytes]:
        """Değişen üyelerle yeni (dizin, veri) çifti. Veri dosyası orijinal + eklenen üyelerdir."""
        unknown = [m for m in changes if m not in self.entries]
        if unknown:
            raise ArchiveError(f"{self.name} içinde olmayan dosyalar yazılmak istendi: {', '.join(unknown[:3])}")
        data = bytearray(self._data.read_all())
        toc = bytearray(self._toc)
        for member, content in sorted(changes.items()):
            entry = self.entries[member]
            blob = content
            if entry.compressed:
                blob = struct.pack("<II", zlib.crc32(content), len(content)) + zlib.compress(content, 9)
            offset = len(data)
            if offset + len(blob) > 0xFFFFFFFF:
                raise ArchiveError(f"{self.name}: veri dosyası 4 GB sınırını aşıyor.")
            data += blob
            base = entry.slot * _ENTRY.size
            struct.pack_into("<II", toc, base + 4, len(blob), offset)
        index = self._index[: _HEADER.size] + scramble(bytes(toc)) + self._names
        return index, bytes(data)
