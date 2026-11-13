"""Güncelleme yamaları (BKTR): base RomFS + update → güncel RomFS.

Güncelleme paketindeki Program NCA'nın RomFS bölümü tam bir dosya sistemi değil,
bir yamadır:

- *Indirect* tablo, yamalanmış (sanal) bölümün her aralığının base bölümden mi
  (depo 0) yoksa yamanın kendi verisinden mi (depo 1) okunacağını söyler.
- *AesCtrEx* tablo, yama verisinin hangi aralığının hangi sayaç nesliyle (generation)
  şifrelendiğini söyler.

Her iki tablo da 0x4000 baytlık düğümlerden oluşan "bucket tree" yapısındadır ve
bölümün sonunda, standart AES-CTR ile şifreli durur. Ayrıntılar: docs/formats/bktr.md
"""

from __future__ import annotations

import bisect
import struct
from dataclasses import dataclass

from nxceviri.core.container.buckettree import IndirectStorage, read_bucket_tree
from nxceviri.core.container.crypto import aes_ctr
from nxceviri.core.container.nca import EncryptionType, FsHeader, FsType, Nca
from nxceviri.core.container.storage import Storage, SubStorage
from nxceviri.core.errors import ContainerError

_INDIRECT_ENTRY = 0x14
_CTR_EX_ENTRY = 0x10


@dataclass(frozen=True)
class _CtrExEntry:
    offset: int
    encrypted: bool
    generation: int


class AesCtrExStorage(Storage):
    """Yama verisini, aralık başına değişen sayaç nesliyle çözen görünüm."""

    def __init__(self, raw: Storage, key: bytes, fs: FsHeader, entries: list[_CtrExEntry], end: int) -> None:
        if end > raw.size:
            raise ContainerError("Güncelleme yaması bozuk: şifreleme tablosu bölümün dışına taşıyor.")
        self._raw = raw
        self._key = key
        self._fs = fs
        self._entries = entries
        self._starts = [e.offset for e in entries]
        self._end = end

    @property
    def size(self) -> int:
        return self._end

    def _read(self, offset: int, size: int) -> bytes:
        out = bytearray()
        pos = offset
        end = offset + size
        i = bisect.bisect_right(self._starts, pos) - 1
        if i < 0:
            raise ContainerError("Güncelleme yaması bozuk: şifreleme tablosu verinin başını kapsamıyor.")
        while pos < end:
            entry = self._entries[i]
            region_end = self._starts[i + 1] if i + 1 < len(self._entries) else self._end
            n = min(end, region_end) - pos
            if entry.encrypted:
                a = pos & ~0xF
                raw = self._raw.read(a, min(self._raw.size, (pos + n + 0xF) & ~0xF) - a)
                upper = self._fs.secure_value.to_bytes(4, "big") + entry.generation.to_bytes(4, "big")
                plain = aes_ctr(self._key, upper, self._fs.start + a, raw)
                out += plain[pos - a : pos - a + n]
            else:
                out += self._raw.read(pos, n)
            pos += n
            i += 1
        return bytes(out)


def open_patched_romfs_section(patch: Nca, fs: FsHeader, base: Nca) -> IndirectStorage:
    """Güncelleme NCA'sının yama bölümünü base NCA ile birleştirip sanal bölümü döndürür."""
    if fs.encryption_type not in (EncryptionType.CTR_EX, EncryptionType.CTR_EX_SKIP_LAYER_HASH):
        raise ContainerError(f"{patch.name}: bu bölüm bir yama değil.")
    if not fs.indirect.present or not fs.aes_ctr_ex.present:
        raise ContainerError(f"{patch.name}: yama tabloları eksik; dosya bozuk olabilir.")
    base_fs = base.find_section(FsType.ROMFS)
    if base_fs is None:
        raise ContainerError(f"{base.name}: ana oyunda veri bölümü yok; güncelleme uygulanamıyor.")

    tables = patch.ctr_section(fs)
    ind_raw, ind_end = read_bucket_tree(
        SubStorage(tables, fs.indirect.offset, fs.indirect.size), fs.indirect, _INDIRECT_ENTRY
    )
    ctr_raw, ctr_end = read_bucket_tree(
        SubStorage(tables, fs.aes_ctr_ex.offset, fs.aes_ctr_ex.size), fs.aes_ctr_ex, _CTR_EX_ENTRY
    )
    ctr_entries = []
    for e in ctr_raw:
        off, enc_flag, gen = struct.unpack("<qB3xi", e)
        ctr_entries.append(_CtrExEntry(off, enc_flag == 0, gen & 0xFFFFFFFF))
    if not ctr_entries or ctr_entries[0].offset != 0:
        raise ContainerError("Güncelleme yaması bozuk: şifreleme tablosu sıfırdan başlamıyor.")
    patch_data = AesCtrExStorage(patch.raw_section(fs), patch.content_key(), fs, ctr_entries, ctr_end)
    ind_entries = [struct.unpack("<qqi", e) for e in ind_raw]
    return IndirectStorage((base.decrypted_section(base_fs), patch_data), ind_entries, ind_end)
