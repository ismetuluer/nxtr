"""NCZ (sıkıştırılmış NCA) okuyucu ve NSZ → NSP dönüştürücü.

NCZ yapısı (nsz projesinin belgelediği biçim, bkz. docs/formats/nsz.md):

- İlk 0x4000 bayt: orijinal NCA'nın şifreli başlığı, olduğu gibi.
- "NCZSECTN" | bölüm sayısı u64 | bölümler (ofset u64, boyut u64, şifre türü u64,
  dolgu u64, anahtar 16 B, sayaç 16 B).
- Ardından ya "NCZBLOCK" başlığı + bağımsız zstd blokları (rastgele erişilebilir),
  ya da 0x4000'den sonrasının tek parça zstd akışı (yalnızca sırayla okunabilir).

Sıkıştırılmış veri, NCA'nın 0x4000 sonrasının *şifresi çözülmüş* hâlidir. Bu modül
veriyi bölüm bilgisiyle yeniden şifreleyerek orijinal NCA baytlarını üretir; böylece
NCA katmanı sıkıştırılmış ve sıkıştırılmamış dosyaları aynı kodla okur.
"""

from __future__ import annotations

import hashlib
import io
import os
import struct
import threading
from collections import OrderedDict
from collections.abc import Buffer, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import zstandard

from nxceviri.core.container.crypto import aes_ctr
from nxceviri.core.container.pfs0 import Pfs0
from nxceviri.core.container.storage import FileStorage, Storage, SubStorage
from nxceviri.core.errors import ContainerError, UnsupportedFormatError
from nxceviri.core.progress import TaskContext

NCZ_HEADER_SIZE = 0x4000
SECTION_MAGIC = b"NCZSECTN"
BLOCK_MAGIC = b"NCZBLOCK"
_CTR_TYPES = (3, 4)
_CACHED_BLOCKS = 16


@dataclass(frozen=True)
class NczSection:
    offset: int
    size: int
    crypto_type: int
    key: bytes
    counter: bytes

    def __repr__(self) -> str:  # anahtar değerini asla göstermez
        return f"NczSection(offset={self.offset:#x}, size={self.size:#x}, crypto_type={self.crypto_type})"


def _parse_sections(storage: Storage) -> tuple[list[NczSection], int]:
    head = storage.read(NCZ_HEADER_SIZE, 16)
    if head[:8] != SECTION_MAGIC:
        raise ContainerError("NCZ dosyası bozuk: NCZSECTN imzası bulunamadı.")
    (count,) = struct.unpack_from("<Q", head, 8)
    # Bölüm tablosu dosyaya sığmalı; bazı NCZ'lerde binlerce bölüm olur, sabit üst sınır yanlıştır.
    if count == 0 or NCZ_HEADER_SIZE + 16 + count * 0x40 > storage.size:
        raise ContainerError("NCZ dosyası bozuk: bölüm sayısı mantıksız.")
    raw = storage.read(NCZ_HEADER_SIZE + 16, count * 0x40)
    sections = []
    for i in range(count):
        off, size, ctype, _ = struct.unpack_from("<QQQQ", raw, i * 0x40)
        key = raw[i * 0x40 + 0x20 : i * 0x40 + 0x30]
        ctr = raw[i * 0x40 + 0x30 : i * 0x40 + 0x40]
        sections.append(NczSection(off, size, ctype, key, ctr))
    return sections, NCZ_HEADER_SIZE + 16 + count * 0x40


def _reencrypt(sections: list[NczSection], nca_offset: int, plain: bytes) -> bytes:
    """`nca_offset`'ten başlayan çözülmüş veriyi NCA'daki özgün şifreli hâline getirir."""
    out = bytearray(plain)
    end = nca_offset + len(plain)
    for s in sections:
        if s.crypto_type not in _CTR_TYPES:
            continue
        lo = max(nca_offset, s.offset)
        hi = min(end, s.offset + s.size)
        if lo >= hi:
            continue
        a_lo = lo & ~0xF
        a_hi = (hi + 0xF) & ~0xF
        # Hizalama için gereken baytlar bu parçanın dışında kalabilir; sıfırla doldurup
        # yalnızca [lo, hi) aralığını kullanırız (CTR'de bayt başına bağımsızdır).
        chunk = bytearray(a_hi - a_lo)
        src_lo = lo - nca_offset
        chunk[lo - a_lo : hi - a_lo] = out[src_lo : src_lo + (hi - lo)]
        enc = aes_ctr(s.key, s.counter, a_lo, bytes(chunk))
        out[src_lo : src_lo + (hi - lo)] = enc[lo - a_lo : hi - a_lo]
    return bytes(out)


class NczBlockStorage(Storage):
    """Blok kipindeki bir NCZ'yi, orijinal NCA gibi rastgele erişimle okur."""

    def __init__(self, ncz: Storage, sections: list[NczSection], block_header_offset: int) -> None:
        self._ncz = ncz
        self._sections = sections
        hdr = ncz.read(block_header_offset, 24)
        _magic, _ver, _type, _unused, exp, count, dsize = struct.unpack("<8sBBBBIQ", hdr)
        if not 14 <= exp <= 32:
            raise ContainerError("NCZ dosyası bozuk: blok boyutu geçersiz.")
        self._block_size = 1 << exp
        self._dsize = int(dsize)
        if count != (dsize + self._block_size - 1) // self._block_size:
            raise ContainerError("NCZ dosyası bozuk: blok sayısı veri boyutuyla uyuşmuyor.")
        sizes = struct.unpack(f"<{count}I", ncz.read(block_header_offset + 24, 4 * count))
        offsets = []
        pos = block_header_offset + 24 + 4 * count
        for s in sizes:
            offsets.append(pos)
            pos += s
        if pos > ncz.size:
            raise ContainerError("NCZ dosyası eksik: sıkıştırılmış bloklar dosyanın sonunu aşıyor.")
        self._sizes = sizes
        self._offsets = offsets
        self._header = ncz.read(0, NCZ_HEADER_SIZE)
        self._cache: OrderedDict[int, bytes] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return NCZ_HEADER_SIZE + self._dsize

    def _block(self, index: int) -> bytes:
        with self._lock:
            cached = self._cache.get(index)
            if cached is not None:
                self._cache.move_to_end(index)
                return cached
        expected = self._block_size
        if index == len(self._sizes) - 1 and self._dsize % self._block_size:
            expected = self._dsize % self._block_size
        raw = self._ncz.read(self._offsets[index], self._sizes[index])
        if self._sizes[index] < expected:
            try:
                data = zstandard.ZstdDecompressor().decompress(raw, max_output_size=expected)
            except zstandard.ZstdError:
                raise ContainerError("NCZ dosyası bozuk: bir blok açılamadı.") from None
        else:
            data = raw[:expected]
        if len(data) != expected:
            raise ContainerError("NCZ dosyası bozuk: blok boyutu beklenenden farklı.")
        with self._lock:
            self._cache[index] = data
            while len(self._cache) > _CACHED_BLOCKS:
                self._cache.popitem(last=False)
        return data

    def _read(self, offset: int, size: int) -> bytes:
        out = bytearray()
        end = offset + size
        if offset < NCZ_HEADER_SIZE:
            out += self._header[offset : min(end, NCZ_HEADER_SIZE)]
            offset = NCZ_HEADER_SIZE
        if offset < end:
            rel = offset - NCZ_HEADER_SIZE
            rel_end = end - NCZ_HEADER_SIZE
            plain = bytearray()
            first = rel // self._block_size
            last = (rel_end - 1) // self._block_size
            for b in range(first, last + 1):
                plain += self._block(b)
            skip = rel - first * self._block_size
            plain_bytes = bytes(plain[skip : skip + (rel_end - rel)])
            out += _reencrypt(self._sections, offset, plain_bytes)
        return bytes(out)


def is_block_mode(ncz: Storage) -> bool:
    _sections, after = _parse_sections(ncz)
    return ncz.read(after, 8) == BLOCK_MAGIC


def open_ncz_random_access(ncz: Storage) -> Storage:
    """Blok kipindeki NCZ için rastgele erişimli NCA görünümü döndürür."""
    sections, after = _parse_sections(ncz)
    if ncz.read(after, 8) != BLOCK_MAGIC:
        raise UnsupportedFormatError(
            "Bu NCZ tek parça (akış) kipinde sıkıştırılmış; doğrudan okunamaz.",
            "Dosya önce önbelleğe açılmalıdır (uygulama bunu otomatik yapar).",
        )
    return NczBlockStorage(ncz, sections, after)


def iter_ncz_as_nca(ncz: Storage, ctx: TaskContext) -> Iterator[bytes]:
    """NCZ'yi (her iki kip) baştan sona orijinal NCA baytları olarak üretir."""
    sections, after = _parse_sections(ncz)
    yield ncz.read(0, NCZ_HEADER_SIZE)
    if ncz.read(after, 8) == BLOCK_MAGIC:
        view = NczBlockStorage(ncz, sections, after)
        for chunk in SubStorage(view, NCZ_HEADER_SIZE, view.size - NCZ_HEADER_SIZE).iter_chunks():
            ctx.check()
            yield chunk
        return
    # Akış kipi: zstd akışı NCZSECTN tablosundan hemen sonra başlar.
    compressed = SubStorage(ncz, after, ncz.size - after)
    dctx = zstandard.ZstdDecompressor()
    reader = dctx.stream_reader(io.BufferedReader(_StorageRaw(compressed), 1024 * 1024), read_across_frames=True)
    pos = NCZ_HEADER_SIZE
    try:
        while True:
            chunk = reader.read(4 * 1024 * 1024)
            if not chunk:
                break
            ctx.check()
            yield _reencrypt(sections, pos, chunk)
            pos += len(chunk)
    except zstandard.ZstdError:
        raise ContainerError("NCZ dosyası bozuk: sıkıştırılmış akış açılamadı.") from None


class _StorageRaw(io.RawIOBase):
    """`Storage`'ı zstandard'ın beklediği dosya benzeri nesneye çevirir."""

    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self._s = storage
        self._pos = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Buffer) -> int:
        view = memoryview(buffer).cast("B")
        n = min(len(view), self._s.size - self._pos)
        view[:n] = self._s.read(self._pos, n)
        self._pos += n
        return n


def _write_pfs0_header(names_sizes: list[tuple[str, int]]) -> bytes:
    strtab = bytearray()
    name_offsets = []
    for name, _ in names_sizes:
        name_offsets.append(len(strtab))
        strtab += name.encode("utf-8") + b"\0"
    # Veri bölgesi 0x20 sınırına hizalansın diye ad tablosunu doldur.
    header_len = 16 + 24 * len(names_sizes) + len(strtab)
    strtab += b"\0" * ((-header_len) % 0x20)
    out = bytearray(struct.pack("<4sIII", b"PFS0", len(names_sizes), len(strtab), 0))
    off = 0
    for (_, size), name_off in zip(names_sizes, name_offsets, strict=True):
        out += struct.pack("<QQII", off, size, name_off, 0)
        off += size
    return bytes(out + strtab)


def _ncz_nca_size(ncz: Storage) -> int | None:
    sections, after = _parse_sections(ncz)
    if ncz.read(after, 8) == BLOCK_MAGIC:
        return NczBlockStorage(ncz, sections, after).size
    return None


def nsz_to_nsp(src: Path, dst: Path, ctx: TaskContext | None = None) -> None:
    """NSZ dosyasını orijinal NSP'ye açar. Her NCA'nın SHA-256'sı adıyla doğrulanır.

    Çıktı önce geçici dosyaya yazılır, doğrulama geçerse yerine taşınır. Kaynak dosya
    yalnızca okunur. Akış kipindeki NCZ'lerin boyutu önceden bilinmediğinden önce
    geçici bir yan dosyaya açılırlar.
    """
    ctx = ctx or TaskContext()
    if src.resolve() == dst.resolve():
        raise ContainerError("Çıktı dosyası kaynak dosyayla aynı olamaz.")
    tmp = dst.with_name(dst.name + ".yaziliyor")
    side_files: list[Path] = []
    with FileStorage(src) as fs:
        pfs = Pfs0(fs, src.name)
        plan: list[tuple[str, int, Callable[[], Iterator[bytes]]]] = []
        try:
            for entry in pfs.entries:
                storage = pfs.open(entry)
                if not entry.name.lower().endswith(".ncz"):
                    plan.append((entry.name, entry.size, storage.iter_chunks))
                    continue
                out_name = entry.name[:-4] + ".nca"
                size = _ncz_nca_size(storage)
                if size is None:
                    ctx.report(0, 0, f"{out_name} açılıyor (akış kipi)")
                    side = dst.with_name(f"{dst.name}.{out_name}.gecici")
                    side_files.append(side)
                    _write_verified(iter_ncz_as_nca(storage, ctx), side, out_name)
                    plan.append((out_name, side.stat().st_size, _file_chunks(side)))
                else:
                    plan.append((out_name, size, _ncz_chunks(storage, ctx)))

            total = sum(size for _, size, _ in plan)
            with open(tmp, "wb") as out:
                out.write(_write_pfs0_header([(n, s) for n, s, _ in plan]))
                written = 0
                for name, size, chunks in plan:
                    hasher = hashlib.sha256()
                    n = 0
                    for chunk in chunks():
                        hasher.update(chunk)
                        out.write(chunk)
                        n += len(chunk)
                        ctx.report(written + n, total, name)
                    if n != size:
                        raise ContainerError(f"'{name}' açılırken boyut uyuşmadı; kaynak dosya bozuk olabilir.")
                    verify_nca_hash(name, hasher.digest())
                    written += size
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, dst)
        finally:
            tmp.unlink(missing_ok=True)
            for side in side_files:
                side.unlink(missing_ok=True)


def verify_nca_hash(name: str, digest: bytes) -> None:
    stem = name.split(".", maxsplit=1)[0].lower()
    if name.lower().endswith(".nca") and len(stem) == 32 and digest[:16].hex() != stem:
        raise ContainerError(
            f"'{name}' doğrulanamadı: içerik özeti dosya adıyla eşleşmiyor.",
            "NSZ dosyası bozuk olabilir. Dosyayı yeniden oluşturun veya kopyalayın.",
        )


def _write_verified(chunks: Iterator[bytes], path: Path, name: str) -> None:
    hasher = hashlib.sha256()
    with open(path, "wb") as out:
        for chunk in chunks:
            hasher.update(chunk)
            out.write(chunk)
    verify_nca_hash(name, hasher.digest())


def _file_chunks(path: Path) -> Callable[[], Iterator[bytes]]:
    def gen() -> Iterator[bytes]:
        with FileStorage(path) as fs:
            yield from fs.iter_chunks()

    return gen


def _ncz_chunks(storage: Storage, ctx: TaskContext) -> Callable[[], Iterator[bytes]]:
    def gen() -> Iterator[bytes]:
        yield from iter_ncz_as_nca(storage, ctx)

    return gen
