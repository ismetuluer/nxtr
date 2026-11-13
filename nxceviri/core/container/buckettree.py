"""NCA bucket tree tabloları (BKTR).

Yama (Indirect, AesCtrEx), seyrek bölüm ve sıkıştırma tabloları aynı yapıyı kullanır: 0x4000 baytlık
düğümler; önce kök (L1) ve gerekiyorsa L2 düğümleri, ardından girdi kümeleri.
Ayrıntılar: docs/formats/bktr.md
"""

from __future__ import annotations

import bisect
import struct
from typing import TYPE_CHECKING

from nxceviri.core.container.storage import Storage
from nxceviri.core.errors import ContainerError

if TYPE_CHECKING:
    from nxceviri.core.container.nca import BucketTreeHeader

NODE_SIZE = 0x4000
_NODE_HEADER = 16


def read_bucket_tree(table: Storage, header: BucketTreeHeader, entry_size: int) -> tuple[list[bytes], int]:
    """Bir bucket tree'nin tüm girdilerini sırayla ve ağacın bitiş ofsetini döndürür.

    Girdi kümeleri, düğüm deposundan (L1 + gerekiyorsa L2 düğümleri) sonra ardışık
    durur; arama için düğümlere ihtiyaç duymadan hepsini sırayla okuruz.
    """
    if header.magic != b"BKTR":
        raise ContainerError("Güncelleme dosyası bozuk: tablo imzası bulunamadı.")
    l1_index, l1_count, end_offset = struct.unpack("<iiq", table.read(0, _NODE_HEADER))
    if l1_index != 0 or l1_count <= 0:
        raise ContainerError("Güncelleme dosyası bozuk: tablo kök düğümü geçersiz.")
    per_set = (NODE_SIZE - _NODE_HEADER) // entry_size
    offsets_per_node = (NODE_SIZE - _NODE_HEADER) // 8
    set_count = -(-header.entry_count // per_set)
    l2_count = 0
    if set_count > offsets_per_node:
        l2_total = -(-set_count // offsets_per_node)
        l2_count = -(-(set_count - (offsets_per_node - (l2_total - 1))) // offsets_per_node)
    entry_base = NODE_SIZE * (1 + l2_count)
    entries: list[bytes] = []
    for i in range(set_count):
        node = table.read(entry_base + i * NODE_SIZE, NODE_SIZE)
        index, count, _set_end = struct.unpack_from("<iiq", node)
        if index != i or not 0 < count <= per_set:
            raise ContainerError("Güncelleme dosyası bozuk: tablo girdi kümesi geçersiz.")
        entries.extend(node[_NODE_HEADER + j * entry_size : _NODE_HEADER + (j + 1) * entry_size] for j in range(count))
    if len(entries) != header.entry_count:
        raise ContainerError("Güncelleme dosyası bozuk: tablo girdi sayısı tutmuyor.")
    return entries, end_offset


class IndirectStorage(Storage):
    """Sanal bölüm: her aralık iki kaynaktan birinden okunur.

    Yamada kaynak 0 base bölüm, 1 yama verisidir; seyrek bölümde 0 fiziksel veri, 1 sıfırlardır.
    """

    def __init__(self, sources: tuple[Storage, Storage], entries: list[tuple[int, int, int]], end: int) -> None:
        self._sources = sources
        self._virt = [e[0] for e in entries]
        self._entries = entries
        self._end = end
        if not entries or entries[0][0] != 0:
            raise ContainerError("Güncelleme dosyası bozuk: eşleme tablosu sıfırdan başlamıyor.")
        for _virt, _phys, idx in entries:
            if idx not in (0, 1):
                raise ContainerError("Güncelleme dosyası bozuk: eşleme tablosunda bilinmeyen kaynak.")

    @property
    def size(self) -> int:
        return self._end

    def _read(self, offset: int, size: int) -> bytes:
        out = bytearray()
        pos = offset
        end = offset + size
        i = bisect.bisect_right(self._virt, pos) - 1
        while pos < end:
            virt, phys, idx = self._entries[i]
            region_end = self._virt[i + 1] if i + 1 < len(self._virt) else self._end
            n = min(end, region_end) - pos
            out += self._sources[idx].read(phys + (pos - virt), n)
            pos += n
            i += 1
        return bytes(out)

    def touches_patch(self, offset: int, size: int) -> bool:
        """[offset, offset+size) aralığının herhangi bir kısmı 1. kaynaktan (yamadan) mı geliyor?"""
        end = offset + max(size, 1)
        i = max(0, bisect.bisect_right(self._virt, offset) - 1)
        while i < len(self._entries) and self._virt[i] < end:
            if self._entries[i][2] == 1:
                return True
            i += 1
        return False


class ZeroStorage(Storage):
    """Yalnızca sıfırlardan oluşan veri (seyrek bölümlerin boş aralıkları)."""

    def __init__(self, size: int) -> None:
        self._size = size

    @property
    def size(self) -> int:
        return self._size

    def _read(self, offset: int, size: int) -> bytes:
        return bytes(size)
