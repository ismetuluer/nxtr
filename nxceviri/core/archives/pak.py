"""Unreal Engine .pak arşivi: okuma (sürüm 1–11) ve yama pak'ı yazma.

Okuma:
- Dosya sonundaki FPakInfo: [şifreleme anahtarı GUID 16 (v7+)] [dizin şifreli mi u8 (v4+)]
  sihirli değer 0x5A6F12E1 | sürüm i32 | dizin ofseti i64 | dizin boyutu i64 | dizin SHA-1 (20)
  [dizin donmuş mu u8 (yalnızca v9)] [sıkıştırma yöntemi adları 32 baytlık × 4–5 (v8+)].
- Eski dizin (v1–v9): bağlama noktası (mount point), girdi sayısı, her girdi: ad + FPakEntry.
- Yeni dizin (v10–11): bağlama noktası, girdi sayısı, yol özeti tohumu, [yol özeti dizini],
  [tam klasör dizini], kodlanmış girdiler (bit alanları), kodlanamayan girdiler. Dosya adları tam
  klasör dizininden okunur.
- Sıkıştırma: yok, Zlib, Gzip. Oodle ve şifreli pak'lar (oyunun AES anahtarı gerekir) desteklenmez;
  açık hata verilir.

Yazma: çeviriler orijinal (çok büyük) pak'ın içine yazılmaz. Değişen dosyalar, aynı bağlama
noktasıyla yeni ve sıkıştırmasız bir yama pak'ına konur (`<ad>_NXCeviri_P.pak`). Unreal, adı
`_P` ile biten pak'ları daha yüksek öncelikle bağlar; aynı yoldaki dosya yamadaki ile değişir.
Yazılan sürüm eski dizin biçimidir (en çok v7; motor eski sürümleri okumayı destekler).
Ayrıntılar: docs/formats/unreal.md
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass, field

from nxceviri.core.container.storage import Storage
from nxceviri.core.errors import ArchiveError, UnsupportedFormatError

MAGIC = 0x5A6F12E1
_MAGIC_BYTES = struct.pack("<I", MAGIC)
_V_NO_TIMESTAMPS = 2
_V_COMPRESSION_ENCRYPTION = 3
_V_INDEX_ENCRYPTION = 4
_V_RELATIVE_CHUNK_OFFSETS = 5
_V_ENCRYPTION_KEY_GUID = 7
_V_FNAME_COMPRESSION = 8
_V_FROZEN_INDEX = 9
_V_PATH_HASH_INDEX = 10
_LEGACY_COMPRESSION_FLAGS = {0x01: "Zlib", 0x02: "Gzip"}
_PATCH_VERSION = _V_ENCRYPTION_KEY_GUID


@dataclass(frozen=True)
class PakEntry:
    name: str  # bağlama noktasına göre yol ("Game/Content/…")
    offset: int  # girdi başlığının dosyadaki yeri
    size: int  # sıkıştırılmış boyut
    uncompressed_size: int
    compression: str  # "" = yok
    blocks: tuple[tuple[int, int], ...]  # mutlak (başlangıç, bitiş)
    encrypted: bool
    header_size: int


@dataclass
class _Cursor:
    data: bytes
    pos: int = 0

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise ArchiveError(".pak dosyası bozuk: dizin beklenenden önce bitti.")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def u32(self) -> int:
        return int(struct.unpack("<I", self.take(4))[0])

    def i32(self) -> int:
        return int(struct.unpack("<i", self.take(4))[0])

    def i64(self) -> int:
        return int(struct.unpack("<q", self.take(8))[0])

    def u64(self) -> int:
        return int(struct.unpack("<Q", self.take(8))[0])

    def fstring(self) -> str:
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            return self.take(n)[:-1].decode("latin-1")
        return self.take(-n * 2)[:-2].decode("utf-16-le", errors="replace")


def _entry_header_size(version: int, compressed: bool, block_count: int) -> int:
    size = 8 + 8 + 8 + 20 + 4
    if version >= _V_COMPRESSION_ENCRYPTION:
        size += 1 + 4
        if compressed:
            size += 4 + 16 * block_count
    if version < _V_NO_TIMESTAMPS:
        size += 8
    return size


@dataclass
class PakFile:
    storage: Storage
    name: str
    version: int = 0
    mount_point: str = ""
    compression_methods: list[str] = field(default_factory=list)
    entries: dict[str, PakEntry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._read_footer()

    # --- dizin ---------------------------------------------------------------------------

    def _read_footer(self) -> None:
        size = self.storage.size
        tail_len = min(size, 512)
        tail = self.storage.read(size - tail_len, tail_len)
        base = size - tail_len
        pos = tail.rfind(_MAGIC_BYTES)
        while pos >= 0:
            magic_at = base + pos
            version, index_offset, index_size = struct.unpack_from("<iqq", tail, pos + 4)
            if 1 <= version <= 11 and index_offset >= 0 and index_offset + index_size <= magic_at:
                self._parse_footer(tail, pos, version, index_offset, index_size)
                return
            pos = tail.rfind(_MAGIC_BYTES, 0, pos)
        raise ArchiveError(f"{self.name} geçerli bir Unreal .pak dosyası değil (pak bilgisi bulunamadı).")

    def _parse_footer(self, tail: bytes, pos: int, version: int, offset: int, size: int) -> None:
        self.version = version
        encrypted_index = version >= _V_INDEX_ENCRYPTION and tail[pos - 1] != 0
        if encrypted_index:
            raise UnsupportedFormatError(
                f"{self.name}: pak dizini şifreli.",
                "Bu oyunun pak dosyaları oyuna özgü bir AES anahtarıyla şifrelenmiş; bu desteklenmiyor.",
            )
        names_at = pos + 4 + 4 + 8 + 8 + 20 + (1 if version == _V_FROZEN_INDEX else 0)
        if version >= _V_FNAME_COMPRESSION:
            raw = tail[names_at:]
            for i in range(0, len(raw) - 31, 32):
                name = raw[i : i + 32].split(b"\0", 1)[0].decode("ascii", errors="replace")
                self.compression_methods.append(name)
        index = self.storage.read(offset, size)
        if version >= _V_PATH_HASH_INDEX:
            self._parse_index_v10(index)
        else:
            self._parse_index_legacy(index)

    def _method(self, value: int) -> str:
        if value == 0:
            return ""
        if self.version >= _V_FNAME_COMPRESSION:
            if value - 1 < len(self.compression_methods):
                return self.compression_methods[value - 1] or f"#{value}"
            return f"#{value}"
        return _LEGACY_COMPRESSION_FLAGS.get(value & 0x0F, f"bayrak {value:#x}")

    def _read_legacy_entry(self, c: _Cursor, name: str) -> PakEntry:
        offset, size, usize = c.i64(), c.i64(), c.i64()
        method = c.u32()
        if self.version < _V_NO_TIMESTAMPS:
            c.i64()
        c.take(20)
        blocks: list[tuple[int, int]] = []
        encrypted = False
        if self.version >= _V_COMPRESSION_ENCRYPTION:
            if method != 0:
                for _ in range(c.i32()):
                    blocks.append((c.i64(), c.i64()))
            encrypted = bool(c.u8() & 0x01)
            c.u32()  # sıkıştırma bloğu boyutu
        if self.version >= _V_RELATIVE_CHUNK_OFFSETS:
            blocks = [(offset + s, offset + e) for s, e in blocks]
        header = _entry_header_size(self.version, method != 0, len(blocks))
        return PakEntry(name, offset, size, usize, self._method(method), tuple(blocks), encrypted, header)

    def _normalize(self, name: str) -> str:
        full = (self.mount_point + name).replace("\\", "/")
        while full.startswith("../"):
            full = full[3:]
        return full.lstrip("/")

    def _parse_index_legacy(self, index: bytes) -> None:
        c = _Cursor(index)
        self.mount_point = c.fstring()
        count = c.i32()
        if not 0 <= count <= 5_000_000:
            raise ArchiveError(f"{self.name} bozuk: girdi sayısı mantıksız.")
        for _ in range(count):
            name = c.fstring()
            entry = self._read_legacy_entry(c, self._normalize(name))
            self.entries[entry.name] = entry

    def _decode_entry(self, buf: bytes, at: int) -> tuple[int, int, int, str, tuple[tuple[int, int], ...], bool, int]:
        c = _Cursor(buf, at)
        value = c.u32()
        if (value & 0x3F) == 0x3F:
            c.u32()  # açıkça yazılmış sıkıştırma bloğu boyutu (okumada gerekmez)
        method = (value >> 23) & 0x3F
        offset = c.u32() if value & (1 << 31) else c.i64()
        usize = c.u32() if value & (1 << 30) else c.i64()
        size = (c.u32() if value & (1 << 29) else c.i64()) if method else usize
        encrypted = bool(value & (1 << 22))
        count = (value >> 6) & 0xFFFF
        header = _entry_header_size(self.version, method != 0, count)
        base = 0 if self.version >= _V_RELATIVE_CHUNK_OFFSETS else offset
        blocks: list[tuple[int, int]] = []
        if count == 1 and not encrypted:
            blocks.append((base + header, base + header + size))
        elif count > 0:
            align = 16 if encrypted else 1
            start = base + header
            for _ in range(count):
                bsize = c.u32()
                blocks.append((start, start + bsize))
                start += (bsize + align - 1) // align * align
        if self.version >= _V_RELATIVE_CHUNK_OFFSETS:
            blocks = [(offset + s, offset + e) for s, e in blocks]
        return offset, size, usize, self._method(method), tuple(blocks), encrypted, header

    def _parse_index_v10(self, index: bytes) -> None:
        c = _Cursor(index)
        self.mount_point = c.fstring()
        c.i32()  # girdi sayısı
        c.u64()  # yol özeti tohumu
        if c.u32():
            c.i64()
            c.i64()
            c.take(20)
        if not c.u32():
            raise UnsupportedFormatError(f"{self.name}: pak'ta tam klasör dizini yok; dosya adları okunamıyor.")
        dir_offset, dir_size = c.i64(), c.i64()
        c.take(20)
        encoded = c.take(c.i32())
        plain: list[PakEntry] = []
        for _ in range(c.i32()):
            plain.append(self._read_legacy_entry(c, ""))
        d = _Cursor(self.storage.read(dir_offset, dir_size))
        for _ in range(d.i32()):
            directory = d.fstring()
            for _ in range(d.i32()):
                file_name = d.fstring()
                location = d.i32()
                path = self._normalize((directory if directory != "/" else "") + file_name)
                if location >= 0:
                    offset, size, usize, method, blocks, encrypted, header = self._decode_entry(encoded, location)
                    self.entries[path] = PakEntry(path, offset, size, usize, method, blocks, encrypted, header)
                else:
                    e = plain[-location - 1]
                    self.entries[path] = PakEntry(
                        path, e.offset, e.size, e.uncompressed_size, e.compression, e.blocks, e.encrypted, e.header_size
                    )

    # --- veri ----------------------------------------------------------------------------

    def read(self, name: str, max_size: int = 256 * 1024 * 1024) -> bytes:
        entry = self.entries.get(name)
        if entry is None:
            raise ArchiveError(f"{self.name} içinde dosya bulunamadı: {name}")
        if entry.encrypted:
            raise UnsupportedFormatError(f"{name}: pak içindeki dosya şifreli; desteklenmiyor.")
        if entry.uncompressed_size > max_size:
            raise ArchiveError(f"{name}: dosya çok büyük ({entry.uncompressed_size:,} bayt); atlanıyor.")
        if not entry.compression:
            return self.storage.read(entry.offset + entry.header_size, entry.size)
        if entry.compression not in ("Zlib", "Gzip"):
            raise UnsupportedFormatError(
                f"{name}: '{entry.compression}' sıkıştırması desteklenmiyor.",
                "Oodle gibi lisanslı sıkıştırmalar açılamaz.",
            )
        out = bytearray()
        wbits = 15 if entry.compression == "Zlib" else 31
        for start, end in entry.blocks:
            try:
                out += zlib.decompress(self.storage.read(start, end - start), wbits)
            except zlib.error:
                raise ArchiveError(f"{name}: sıkıştırılmış blok açılamadı; pak bozuk olabilir.") from None
        if len(out) != entry.uncompressed_size:
            raise ArchiveError(f"{name}: açılan boyut beklenenden farklı; pak bozuk olabilir.")
        return bytes(out)


def is_pak(storage: Storage) -> bool:
    tail_len = min(storage.size, 512)
    return _MAGIC_BYTES in storage.read(storage.size - tail_len, tail_len)


def _fstring(text: str) -> bytes:
    if not text:
        return struct.pack("<i", 0)
    if all(ord(c) < 0x80 for c in text):
        raw = text.encode("ascii") + b"\0"
        return struct.pack("<i", len(raw)) + raw
    raw = text.encode("utf-16-le") + b"\0\0"
    return struct.pack("<i", -(len(raw) // 2)) + raw


def _entry_bytes(version: int, offset: int, data: bytes) -> bytes:
    out = struct.pack("<qqqI", offset, len(data), len(data), 0)
    if version < _V_NO_TIMESTAMPS:
        out += struct.pack("<q", 0)
    out += hashlib.sha1(data).digest()
    if version >= _V_COMPRESSION_ENCRYPTION:
        out += struct.pack("<BI", 0, 0)
    return out


def build_patch_pak(mount_point: str, files: dict[str, bytes], version: int = _PATCH_VERSION) -> bytes:
    """Sıkıştırmasız, şifresiz bir yama pak'ı üretir (eski dizin biçimi, en çok v7)."""
    version = max(_V_COMPRESSION_ENCRYPTION, min(version, _PATCH_VERSION))
    body = bytearray()
    index = bytearray(_fstring(mount_point) + struct.pack("<i", len(files)))
    for name, data in sorted(files.items()):
        offset = len(body)
        # Veriden önceki başlık kopyasında ofset 0 yazılır (UnrealPak'ın yaptığı gibi); dizinde gerçek ofset.
        body += _entry_bytes(version, 0, data) + data
        index += _fstring(name) + _entry_bytes(version, offset, data)
    footer = bytearray()
    if version >= _V_ENCRYPTION_KEY_GUID:
        footer += b"\0" * 16
    if version >= _V_INDEX_ENCRYPTION:
        footer += b"\0"
    footer += struct.pack("<Iiqq", MAGIC, version, len(body), len(index))
    footer += hashlib.sha1(bytes(index)).digest()
    return bytes(body + index + footer)


def relative_to_mount(mount_point: str, path: str) -> str:
    """Normalleştirilmiş yolu (Game/Content/…) bağlama noktasına göre göreli ada çevirir."""
    mount = mount_point.replace("\\", "/")
    while mount.startswith("../"):
        mount = mount[3:]
    mount = mount.lstrip("/")
    if mount and not path.startswith(mount):
        raise ArchiveError(f"'{path}' pak'ın bağlama noktasının ({mount_point}) dışında.")
    return path[len(mount) :]
