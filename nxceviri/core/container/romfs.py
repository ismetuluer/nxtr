"""RomFS okuyucu.

Başlık (0x50): başlık boyutu ve dizin hash/meta, dosya hash/meta tablolarının
ofset/boyutları (hepsi u64) ile dosya verisi ofseti. Dizin girdisi: üst, kardeş,
ilk alt dizin, ilk dosya, hash zinciri, ad uzunluğu (u32) + ad. Dosya girdisi: üst,
kardeş (u32), veri ofseti, boyut (u64), hash zinciri, ad uzunluğu (u32) + ad.
"Yok" değeri 0xFFFFFFFF'dir. Ayrıntılar: docs/formats/romfs.md
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from nxceviri.core.container.storage import Storage, SubStorage
from nxceviri.core.errors import ContainerError

ROMFS_HEADER_SIZE = 0x50
_NONE = 0xFFFFFFFF
_MAX_TABLE = 512 * 1024 * 1024


@dataclass(frozen=True)
class RomFsFile:
    path: str  # "/" ile ayrılmış, başında "/" olmayan yol
    offset: int  # RomFS başına göre mutlak veri ofseti
    size: int


class RomFs:
    def __init__(self, storage: Storage, name: str = "RomFS") -> None:
        self.storage = storage
        if storage.size < ROMFS_HEADER_SIZE:
            raise ContainerError(f"{name} bozuk: başlık için veri çok kısa.")
        fields = struct.unpack("<10Q", storage.read(0, ROMFS_HEADER_SIZE))
        header_size, _dh_off, _dh_size, dm_off, dm_size, _fh_off, _fh_size, fm_off, fm_size, data_off = fields
        if header_size != ROMFS_HEADER_SIZE:
            raise ContainerError(
                f"{name} okunamadı: oyun dosyası başlığı geçersiz.",
                "İçerik yanlış bir anahtarla çözülmüş olabilir veya dosya bozuk.",
            )
        for off, size in ((dm_off, dm_size), (fm_off, fm_size)):
            if size > _MAX_TABLE or off + size > storage.size:
                raise ContainerError(f"{name} bozuk: dizin/dosya tablosu verinin dışına taşıyor.")
        self._dirs = storage.read(dm_off, dm_size)
        self._files = storage.read(fm_off, fm_size)
        self._data_off = data_off
        self.files: dict[str, RomFsFile] = {}
        self._walk(0, "", set())

    def _name(self, table: bytes, name_field: int, length_limit: int) -> str:
        (length,) = struct.unpack_from("<I", table, name_field)
        if length > length_limit or name_field + 4 + length > len(table):
            raise ContainerError("Oyun dosyaları bozuk: girdi adı tablonun dışına taşıyor.")
        return table[name_field + 4 : name_field + 4 + length].decode("utf-8", errors="replace")

    def _walk(self, dir_off: int, prefix: str, seen: set[int]) -> None:
        if dir_off in seen or dir_off + 0x18 > len(self._dirs):
            raise ContainerError("Oyun dosyaları bozuk: dizin ağacında döngü veya geçersiz bağlantı var.")
        seen.add(dir_off)
        _parent, _sibling, child, file_off, _hash, _nlen = struct.unpack_from("<6I", self._dirs, dir_off)
        fseen: set[int] = set()
        while file_off != _NONE:
            if file_off in fseen or file_off + 0x20 > len(self._files):
                raise ContainerError("Oyun dosyaları bozuk: dosya listesinde döngü veya geçersiz bağlantı var.")
            fseen.add(file_off)
            _fp, sibling, data, size, _fh = struct.unpack_from("<IIQQI", self._files, file_off)
            name = self._name(self._files, file_off + 0x1C, 0x300)
            abs_off = self._data_off + data
            if abs_off + size > self.storage.size:
                raise ContainerError(f"Oyun dosyaları bozuk: '{prefix}{name}' verinin dışına taşıyor.")
            self.files[prefix + name] = RomFsFile(prefix + name, abs_off, size)
            file_off = sibling
        while child != _NONE:
            if child + 0x18 > len(self._dirs):
                raise ContainerError("Oyun dosyaları bozuk: alt dizin bağlantısı geçersiz.")
            (child_sibling,) = struct.unpack_from("<I", self._dirs, child + 4)
            name = self._name(self._dirs, child + 0x14, 0x300)
            self._walk(child, f"{prefix}{name}/", seen)
            child = child_sibling

    def open(self, path: str) -> Storage:
        entry = self.files.get(path)
        if entry is None:
            raise ContainerError(f"Oyun dosyaları içinde dosya bulunamadı: {path}")
        return SubStorage(self.storage, entry.offset, entry.size)
