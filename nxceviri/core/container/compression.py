"""NCA sıkıştırma katmanı (CompressedStorage).

Yeni SDK'larla üretilen bazı oyunlarda RomFS verisi bloklar hâlinde LZ4 ile
sıkıştırılmıştır. Katman, hash katmanları (IVFC) atlanmış veri bölgesinin üzerindedir:
bölgenin sonundaki bucket tree tablosu, açılmış verinin (RomFS) her aralığının bölgedeki
hangi fiziksel aralıktan ve nasıl (ham, sıfır, LZ4) üretileceğini söyler.
Ayrıntılar: docs/formats/nca.md
"""

from __future__ import annotations

import bisect
import struct
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import lz4.block

from nxceviri.core.container.buckettree import read_bucket_tree
from nxceviri.core.container.storage import Storage, SubStorage
from nxceviri.core.errors import ContainerError, UnsupportedFormatError

if TYPE_CHECKING:
    from nxceviri.core.container.nca import BucketTreeHeader

ENTRY_SIZE = 0x18
TYPE_NONE = 0
TYPE_ZEROS = 1
TYPE_LZ4 = 3
_CACHE_BLOCKS = 16


@dataclass(frozen=True)
class CompressionEntry:
    virtual_offset: int
    physical_offset: int
    kind: int
    physical_size: int


def parse_entries(raw: list[bytes]) -> list[CompressionEntry]:
    entries = []
    for e in raw:
        virt, phys, kind, _level, size = struct.unpack("<qqBb2xI", e)
        entries.append(CompressionEntry(virt, phys, kind, size))
    return entries


class CompressedStorage(Storage):
    """Sıkıştırılmış veri bölgesinin açılmış görünümü; son açılan bloklar önbellekte tutulur."""

    def __init__(self, data: Storage, entries: list[CompressionEntry], end: int) -> None:
        if not entries or entries[0].virtual_offset != 0:
            raise ContainerError("NCA bölümü bozuk: sıkıştırma tablosu sıfırdan başlamıyor.")
        self._data = data
        self._entries = entries
        self._starts = [e.virtual_offset for e in entries]
        self._end = end
        for i, e in enumerate(entries):
            if e.kind not in (TYPE_NONE, TYPE_ZEROS, TYPE_LZ4):
                raise UnsupportedFormatError(f"NCA bölümünde bilinmeyen sıkıştırma türü ({e.kind}).")
            if e.physical_offset + self._physical_length(i) > data.size:
                raise ContainerError("NCA bölümü bozuk: sıkıştırılmış blok veri bölgesinin dışına taşıyor.")
        self._cache: OrderedDict[int, bytes] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return self._end

    def _region_end(self, i: int) -> int:
        return self._starts[i + 1] if i + 1 < len(self._starts) else self._end

    def _physical_length(self, i: int) -> int:
        """Bloğun bölgede kapladığı bayt. Ham bloklarda boyut alanı kullanılmaz (0xFFFFFFFF
        yazılır); uzunluk sanal aralığınkiyle aynıdır."""
        e = self._entries[i]
        if e.kind == TYPE_ZEROS:
            return 0
        if e.kind == TYPE_NONE:
            return self._region_end(i) - e.virtual_offset
        return e.physical_size

    def _block(self, i: int) -> bytes:
        with self._lock:
            cached = self._cache.get(i)
            if cached is not None:
                self._cache.move_to_end(i)
                return cached
        e = self._entries[i]
        length = self._region_end(i) - e.virtual_offset
        try:
            packed = self._data.read(e.physical_offset, e.physical_size)
            block: bytes = lz4.block.decompress(packed, uncompressed_size=length)
        except lz4.block.LZ4BlockError:
            raise ContainerError(
                "NCA bölümü bozuk: sıkıştırılmış blok açılamadı.",
                "Dosya eksik veya bozuk olabilir. Dosyayı kendi konsolunuzdan yeniden çıkarın.",
            ) from None
        if len(block) != length:
            raise ContainerError("NCA bölümü bozuk: açılan blok beklenen boyutta değil.")
        with self._lock:
            self._cache[i] = block
            if len(self._cache) > _CACHE_BLOCKS:
                self._cache.popitem(last=False)
        return block

    def _read(self, offset: int, size: int) -> bytes:
        out = bytearray()
        pos = offset
        end = offset + size
        i = bisect.bisect_right(self._starts, pos) - 1
        while pos < end:
            e = self._entries[i]
            n = min(end, self._region_end(i)) - pos
            rel = pos - e.virtual_offset
            if e.kind == TYPE_NONE:
                out += self._data.read(e.physical_offset + rel, n)
            elif e.kind == TYPE_ZEROS:
                out += bytes(n)
            else:
                out += self._block(i)[rel : rel + n]
            pos += n
            i += 1
        return bytes(out)

    def physical_span(self, offset: int, size: int) -> tuple[int, int]:
        """Açılmış [offset, offset+size) aralığını üreten fiziksel aralık (başlangıç, uzunluk)."""
        end = offset + max(size, 1)
        i = max(0, bisect.bisect_right(self._starts, offset) - 1)
        lo: int | None = None
        hi = 0
        while i < len(self._entries) and self._starts[i] < end:
            e = self._entries[i]
            if e.kind == TYPE_NONE:
                a = e.physical_offset + max(0, offset - e.virtual_offset)
                b = e.physical_offset + min(end, self._region_end(i)) - e.virtual_offset
            elif e.kind == TYPE_LZ4:
                a, b = e.physical_offset, e.physical_offset + e.physical_size
            else:
                i += 1
                continue
            lo = a if lo is None else min(lo, a)
            hi = max(hi, b)
            i += 1
        if lo is None:
            return 0, 0
        return lo, hi - lo


def open_compressed(region: Storage, info: BucketTreeHeader) -> CompressedStorage:
    """Çözülmüş (gerekiyorsa yamalanmış) veri bölgesinin sıkıştırma katmanını açar; tablo bölgenin sonundadır."""
    if info.offset + info.size > region.size:
        raise ContainerError("NCA bölümü bozuk: sıkıştırma tablosu veri bölgesinin dışına taşıyor.")
    raw, end = read_bucket_tree(SubStorage(region, info.offset, info.size), info, ENTRY_SIZE)
    return CompressedStorage(SubStorage(region, 0, info.offset), parse_entries(raw), end)
