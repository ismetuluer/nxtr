"""PFS0 (Partition FS) okuyucu — NSP/NSZ dosyalarının ve ExeFS/meta bölümlerinin biçimi.

Yapı: "PFS0" | dosya sayısı u32 | metin tablosu boyutu u32 | 0 u32 |
dosya girdileri (ofset u64, boyut u64, ad ofseti u32, 0 u32) | ad tablosu | veri.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from nxceviri.core.container.storage import Storage, SubStorage
from nxceviri.core.errors import ContainerError

PFS0_MAGIC = b"PFS0"
_MAX_ENTRIES = 0x10000


@dataclass(frozen=True)
class PfsEntry:
    name: str
    offset: int  # PFS0 başlangıcına göre mutlak ofset
    size: int


class Pfs0:
    def __init__(self, storage: Storage, what: str = "Dosya") -> None:
        self.storage = storage
        if storage.size < 16:
            raise ContainerError(f"{what} bir NSP/PFS0 dosyası değil (çok kısa).")
        magic, count, strtab_size, _ = struct.unpack("<4sIII", storage.read(0, 16))
        if magic != PFS0_MAGIC:
            raise ContainerError(
                f"{what} geçerli bir NSP/NSZ değil (PFS0 imzası yok).",
                "Yalnızca .nsp ve .nsz dosyaları desteklenir. Dosyanın bozuk olmadığından emin olun.",
            )
        if count > _MAX_ENTRIES:
            raise ContainerError(f"{what} bozuk: dosya tablosu mantıksız büyüklükte.")
        table = storage.read(16, count * 24 + strtab_size)
        strtab = table[count * 24 :]
        data_start = 16 + count * 24 + strtab_size
        entries: list[PfsEntry] = []
        for i in range(count):
            off, size, name_off, _ = struct.unpack_from("<QQII", table, i * 24)
            end = strtab.find(b"\0", name_off)
            if name_off >= len(strtab) or end < 0:
                raise ContainerError(f"{what} bozuk: dosya adı tablosu okunamadı.")
            name = strtab[name_off:end].decode("utf-8", errors="replace")
            if data_start + off + size > storage.size:
                raise ContainerError(
                    f"{what} eksik: '{name}' dosyanın sonunun ötesine uzanıyor.",
                    "Dosya eksik kopyalanmış veya indirilmiş olabilir.",
                )
            entries.append(PfsEntry(name, data_start + off, size))
        self.entries = entries

    def find(self, name: str) -> PfsEntry | None:
        return next((e for e in self.entries if e.name == name), None)

    def open(self, entry: PfsEntry) -> Storage:
        return SubStorage(self.storage, entry.offset, entry.size)
