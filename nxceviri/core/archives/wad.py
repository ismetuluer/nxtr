"""Spike Chunsoft WAD arşivi (Danganronpa: `dr1_data.wad`), imzası `AGAR`.

Yapı (küçük sonlu):
- Başlık: `AGAR` | sürüm u32 | alt sürüm u32 | ek başlık boyutu u32 | ek başlık.
- Dosya tablosu: sayı u32, her dosya için ad uzunluğu u32 | UTF-8 ad (`Dr1/data/us/script/x.lin`) |
  boyut u64 | ofset u64. Ofsetler veri bölümünün başına göredir.
- Klasör tablosu: sayı u32, her klasör için ad uzunluğu u32 | ad | çocuk sayısı u32 | her çocuk için
  ad uzunluğu u32 | ad | klasör mü u8. Veri bölümü klasör tablosunun hemen ardından başlar.

Yazma: başlık ve klasör tablosu aynen kalır; üyeler orijinal ofset sırasıyla, aralarındaki boşluk
baytları korunarak yeniden dizilir ve dosya tablosundaki boyut/ofset alanları güncellenir. Değişiklik
yoksa çıktı orijinalle bayt bayt aynıdır. Ayrıntılar: docs/formats/danganronpa.md
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from nxceviri.core.container.storage import Storage
from nxceviri.core.errors import ArchiveError, UnsupportedFormatError

MAGIC = b"AGAR"
SUFFIX = ".wad"
_HEADER = struct.Struct("<4sIII")
_U32 = struct.Struct("<I")
_SIZE_OFFSET = struct.Struct("<QQ")
#: Dizinin okunması için ilk denemede okunan bayt (DR1'de dizin ~580 KB); yetmezse ikiye katlanır.
_FIRST_READ = 1024 * 1024
#: Yeniden kurulacak arşivin üst sınırı: tamamı bellekte kurulur.
MAX_REBUILD = 1024 * 1024 * 1024


def is_wad(path: str, head: bytes) -> bool:
    return path.lower().endswith(SUFFIX) and head.startswith(MAGIC)


@dataclass(frozen=True)
class WadEntry:
    name: str
    slot: int  # dosya tablosundaki sıra
    offset: int  # veri bölümünün başına göre
    size: int
    #: Dosya tablosunda boyut alanının arşiv başından ofseti (boyut u64 + ofset u64 burada).
    field: int


class _Incomplete(Exception):
    """Okunan baş kısım dizinin tamamını içermiyor."""


def _parse_index(buf: bytes) -> tuple[list[tuple[str, int, int, int]], int]:
    """(ad, boyut, ofset, alan konumu) listesi ve veri bölümünün başlangıcı."""

    def u32(pos: int) -> int:
        if pos + 4 > len(buf):
            raise _Incomplete
        return int(_U32.unpack_from(buf, pos)[0])

    def name(pos: int) -> tuple[str, int]:
        n = u32(pos)
        if pos + 4 + n > len(buf):
            raise _Incomplete
        try:
            return buf[pos + 4 : pos + 4 + n].decode("utf-8"), pos + 4 + n
        except UnicodeDecodeError:
            raise ArchiveError("WAD dizininde okunamayan bir dosya adı var.") from None

    _magic, _major, _minor, extra = _HEADER.unpack_from(buf)
    pos = _HEADER.size + extra
    count = u32(pos)
    pos += 4
    files = []
    for _ in range(count):
        member, pos = name(pos)
        if pos + _SIZE_OFFSET.size > len(buf):
            raise _Incomplete
        size, offset = _SIZE_OFFSET.unpack_from(buf, pos)
        files.append((member, size, offset, pos))
        pos += _SIZE_OFFSET.size
    dirs = u32(pos)
    pos += 4
    for _ in range(dirs):
        _dir, pos = name(pos)
        children = u32(pos)
        pos += 4
        for _ in range(children):
            _child, pos = name(pos)
            if pos + 1 > len(buf):
                raise _Incomplete
            pos += 1
    return files, pos


class WadArchive:
    def __init__(self, storage: Storage, name: str) -> None:
        self.storage = storage
        self.name = name
        if storage.size < _HEADER.size or storage.read(0, 4) != MAGIC:
            raise ArchiveError(f"{name} bir WAD (AGAR) arşivi değil.")
        length = min(_FIRST_READ, storage.size)
        while True:
            buf = storage.read(0, length)
            try:
                files, data_start = _parse_index(buf)
                break
            except _Incomplete:
                if length == storage.size:
                    raise ArchiveError(f"{name} bozuk: dizin dosyanın sonunu aşıyor.") from None
                length = min(length * 2, storage.size)
        self.index = buf[:data_start]
        self.data_start = data_start
        self.entries: dict[str, WadEntry] = {}
        for slot, (member, size, offset, field) in enumerate(files):
            if data_start + offset + size > storage.size:
                raise ArchiveError(f"{name} bozuk: '{member}' arşivin dışına taşıyor.")
            self.entries[member] = WadEntry(member, slot, offset, size, field)

    def read(self, member: str) -> bytes:
        entry = self.entries.get(member)
        if entry is None:
            raise ArchiveError(f"{self.name} içinde '{member}' yok.")
        return self.storage.read(self.data_start + entry.offset, entry.size)

    def rebuild(self, changes: dict[str, bytes]) -> bytes:
        """Değişen üyelerle arşivin tamamı. Üye sırası ve aradaki boşluklar korunur."""
        unknown = [m for m in changes if m not in self.entries]
        if unknown:
            raise ArchiveError(f"{self.name} içinde olmayan dosyalar yazılmak istendi: {', '.join(unknown[:3])}")
        if self.storage.size > MAX_REBUILD:
            raise UnsupportedFormatError(
                f"{self.name} yeniden kurulamayacak kadar çok büyük ({self.storage.size:,} bayt).",
                "Bu boyuttaki WAD arşivleri henüz desteklenmiyor.",
            )
        index = bytearray(self.index)
        body = bytearray()
        previous_end = 0
        for entry in sorted(self.entries.values(), key=lambda e: (e.offset, e.slot)):
            if entry.offset > previous_end:
                body += self.storage.read(self.data_start + previous_end, entry.offset - previous_end)
            content = changes[entry.name] if entry.name in changes else self.read(entry.name)
            struct.pack_into("<QQ", index, entry.field, len(content), len(body))
            body += content
            previous_end = max(previous_end, entry.offset + entry.size)
        tail = self.storage.size - self.data_start - previous_end
        if tail > 0:
            body += self.storage.read(self.data_start + previous_end, tail)
        return bytes(index) + bytes(body)
