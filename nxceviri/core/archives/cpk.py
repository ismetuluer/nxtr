"""CRI Middleware CPK arşivi (Unicorn Overlord): okuma ve değişen dosyalarla yeniden kurma.

Yapı:
- Her tablo bölümü 16 baytlık bir başlıkla başlar: imza (`CPK `, `TOC `, `ETOC`…) | u32 | boyut u64,
  ardından bir `@UTF` tablosu. Tablo baytları çoğu zaman karıştırılmıştır: her bayt, 0x655F ile
  başlayıp her adımda 0x4115 ile çarpılan sayacın düşük baytıyla XOR'lanır.
- `@UTF` tablosu (büyük sonlu): satır/dizge/veri/ad ofsetleri, sütun sayısı, satır uzunluğu, satır
  sayısı; her sütun: bayrak (depolama | tür) + ad. Depolama 0x10 = boş, 0x30 = sabit, 0x50 = satırda.
- `CpkHeader` satırı TOC/ETOC/ITOC yerlerini, içerik ofsetini ve hizalamayı verir. TOC'ta her dosya:
  `DirName`, `FileName`, `FileSize` (arşivdeki), `ExtractSize` (açılmış), `FileOffset` (TOC başına göre).
- `FileSize < ExtractSize` ise dosya CRILAYLA ile sıkıştırılmıştır: `CRILAYLA` | açık boyut u32 |
  başlık ofseti u32 | sondan başa okunan LZ verisi | 0x100 baytlık sıkıştırılmamış baş kısım.

Yazma: değişen dosyalar sıkıştırılmadan (`FileSize == ExtractSize`) konur, diğerleri ham olarak
kopyalanır; dosyalar aynı sırayla ve aynı hizalamayla yeniden dizilir. TOC satırlarındaki boyut/ofset
alanları ve başlıktaki içerik/ETOC alanları yerinde güncellenir; tablolar aynı biçimde (gerekirse
yeniden karıştırılarak) yazılır. Yalnızca dosya adlı (TOC'lu) arşivler desteklenir.
Ayrıntılar: docs/formats/unicorn-overlord.md
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from nxceviri.core.container.storage import Storage
from nxceviri.core.errors import ArchiveError, UnsupportedFormatError

MAGIC = b"CPK "
UTF_MAGIC = b"@UTF"
SUFFIX = ".cpk"
LAYLA_MAGIC = b"CRILAYLA"
_CHUNK = struct.Struct("<4sIQ")
_UTF_HEAD = struct.Struct(">IIIIHHI")
_LAYLA_PREFIX = 0x100
_STORAGE_MASK = 0xF0
_TYPE_MASK = 0x0F
_ZERO, _CONSTANT, _PER_ROW = 0x10, 0x30, 0x50
_FORMATS = {0: ">B", 1: ">b", 2: ">H", 3: ">h", 4: ">I", 5: ">i", 6: ">Q", 7: ">q", 8: ">f", 9: ">d"}
_TYPE_STRING, _TYPE_DATA = 0x0A, 0x0B
#: Tek tablo ve tek dosya için üst sınırlar (bellek koruması).
MAX_TABLE = 64 * 1024 * 1024
MAX_MEMBER = 256 * 1024 * 1024
#: Yeniden kurulabilecek en büyük arşiv: tüm arşiv bellekte yeniden yazılır ve moda kopyalanır.
MAX_REBUILD = 512 * 1024 * 1024

Value = int | float | str | bytes | None


def _mask(data: bytes) -> bytes:
    out = bytearray(data)
    m = 0x655F
    for i in range(len(out)):
        out[i] ^= m & 0xFF
        m = (m * 0x4115) & 0xFFFFFFFF
    return bytes(out)


@dataclass(frozen=True)
class _Column:
    name: str
    storage: int
    type: int
    constant: Value
    row_offset: int  # satır içindeki yeri (yalnızca satırda saklananlar için)


class UtfTable:
    """Çözülmüş bir `@UTF` tablosu; sayısal hücreler yerinde değiştirilebilir."""

    def __init__(self, raw: bytes, where: str) -> None:
        self.masked = not raw.startswith(UTF_MAGIC)
        data = _mask(raw) if self.masked else raw
        if not data.startswith(UTF_MAGIC) or len(data) < 8 + _UTF_HEAD.size:
            raise ArchiveError(f"{where}: CPK tablosu okunamadı.")
        (size,) = struct.unpack_from(">I", data, 4)
        if 8 + size > len(data):
            raise ArchiveError(f"{where}: CPK tablosu kesik.")
        self._where = where
        self._data = bytearray(data)
        self._body = 8
        t = self._data
        rows_off, self._str_off, self._data_off, name_off, ncol, self.row_len, self.row_count = _UTF_HEAD.unpack_from(
            t, self._body
        )
        self._rows_off = rows_off
        self.name = self._string(name_off)
        self.columns: list[_Column] = []
        p = self._body + _UTF_HEAD.size
        row_pos = 0
        for _ in range(ncol):
            flag = t[p]
            (col_name,) = struct.unpack_from(">I", t, p + 1)
            p += 5
            storage, kind = flag & _STORAGE_MASK, flag & _TYPE_MASK
            constant: Value = None
            if storage == _CONSTANT:
                constant, width = self._value(p, kind)
                p += width
            column = _Column(self._string(col_name), storage, kind, constant, row_pos)
            if storage == _PER_ROW:
                row_pos += self._width(kind)
            elif storage not in (_ZERO, _CONSTANT):
                raise ArchiveError(f"{where}: CPK tablosunda bilinmeyen sütun türü ({flag:#x}).")
            self.columns.append(column)
        if row_pos != self.row_len:
            raise ArchiveError(f"{where}: CPK tablosunun satır uzunluğu sütunlarla uyuşmuyor.")

    def _width(self, kind: int) -> int:
        if kind in _FORMATS:
            return struct.calcsize(_FORMATS[kind])
        if kind == _TYPE_STRING:
            return 4
        if kind == _TYPE_DATA:
            return 8
        raise ArchiveError(f"{self._where}: CPK tablosunda bilinmeyen veri türü ({kind}).")

    def _string(self, offset: int) -> str:
        start = self._body + self._str_off + offset
        end = self._data.find(b"\0", start)
        if end < 0:
            raise ArchiveError(f"{self._where}: CPK dizge tablosu bozuk.")
        return self._data[start:end].decode("utf-8", errors="replace")

    def _value(self, pos: int, kind: int) -> tuple[Value, int]:
        width = self._width(kind)
        if kind in _FORMATS:
            return struct.unpack_from(_FORMATS[kind], self._data, pos)[0], width
        if kind == _TYPE_STRING:
            return self._string(struct.unpack_from(">I", self._data, pos)[0]), width
        off, length = struct.unpack_from(">II", self._data, pos)
        start = self._body + self._data_off + off
        return bytes(self._data[start : start + length]), width

    def _cell(self, row: int, column: str) -> tuple[_Column, int]:
        for col in self.columns:
            if col.name == column:
                return col, self._body + self._rows_off + row * self.row_len + col.row_offset
        raise KeyError(column)

    def get(self, row: int, column: str) -> Value:
        try:
            col, pos = self._cell(row, column)
        except KeyError:
            return None
        if col.storage == _CONSTANT:
            return col.constant
        if col.storage == _ZERO:
            return None
        return self._value(pos, col.type)[0]

    def set(self, row: int, column: str, value: int) -> None:
        col, pos = self._cell(row, column)
        if col.storage != _PER_ROW or col.type not in _FORMATS or col.type in (8, 9):
            if self.get(row, column) == value:
                return
            raise ArchiveError(f"{self._where}: '{column}' alanı değiştirilemiyor.")
        fmt = _FORMATS[col.type]
        try:
            struct.pack_into(fmt, self._data, pos, value)
        except struct.error:
            raise ArchiveError(f"{self._where}: '{column}' alanına {value} sığmıyor.") from None

    def to_bytes(self) -> bytes:
        data = bytes(self._data)
        return _mask(data) if self.masked else data


def _read_chunk(storage: Storage, offset: int, magic: bytes, where: str) -> tuple[bytes, UtfTable]:
    if offset + _CHUNK.size > storage.size:
        raise ArchiveError(f"{where}: CPK bölümü dosyanın dışında.")
    head = storage.read(offset, _CHUNK.size)
    got, _unknown, size = _CHUNK.unpack(head)
    if got != magic or size > MAX_TABLE or offset + _CHUNK.size + size > storage.size:
        raise ArchiveError(f"{where}: CPK '{magic.decode().strip()}' bölümü bozuk.")
    return head, UtfTable(storage.read(offset + _CHUNK.size, size), where)


def decompress_layla(src: bytes, limit: int = MAX_MEMBER) -> bytes:
    """CRILAYLA sıkıştırmasını açar (veri sondan başa doğru, bitler en anlamlıdan okunur)."""
    if not src.startswith(LAYLA_MAGIC) or len(src) < 16:
        raise ArchiveError("CRILAYLA verisi bozuk: başlık yok.")
    size, header_off = struct.unpack_from("<II", src, 8)
    prefix_at = 16 + header_off
    if size > limit or prefix_at + _LAYLA_PREFIX > len(src):
        raise ArchiveError("CRILAYLA verisi bozuk: boyutlar tutarsız.")
    out = bytearray(size)
    pos = prefix_at - 1
    pool = 0
    left = 0

    def bits(n: int) -> int:
        nonlocal pos, pool, left
        value = 0
        while n:
            if left == 0:
                if pos < 16:
                    raise ArchiveError("CRILAYLA verisi bozuk: veri erken bitti.")
                pool = src[pos]
                pos -= 1
                left = 8
            take = left if left < n else n
            value = (value << take) | ((pool >> (left - take)) & ((1 << take) - 1))
            left -= take
            n -= take
        return value

    w = size - 1
    while w >= 0:
        if bits(1):
            distance = bits(13) + 3
            length = 3
            for level in (2, 3, 5):
                v = bits(level)
                length += v
                if v != (1 << level) - 1:
                    break
            else:
                while True:
                    v = bits(8)
                    length += v
                    if v != 0xFF:
                        break
            if w + distance >= size or length > w + 1:
                raise ArchiveError("CRILAYLA verisi bozuk: geçersiz geri başvuru.")
            for _ in range(length):
                out[w] = out[w + distance]
                w -= 1
        else:
            out[w] = bits(8)
            w -= 1
    return src[prefix_at : prefix_at + _LAYLA_PREFIX] + bytes(out)


@dataclass(frozen=True)
class CpkEntry:
    name: str  # "Dir/File.ext"
    row: int  # TOC satırı
    offset: int  # dosyadaki mutlak konum
    size: int  # arşivdeki boyut
    extract_size: int


def is_cpk(path: str, head: bytes) -> bool:
    return path.lower().endswith(SUFFIX) and head.startswith(MAGIC)


class CpkFile:
    def __init__(self, storage: Storage, name: str) -> None:
        self.storage = storage
        self.name = name
        self._header_chunk, self.header = _read_chunk(storage, 0, MAGIC, name)
        h = self.header
        if h.get(0, "ItocOffset") and not h.get(0, "TocOffset"):
            raise UnsupportedFormatError(
                f"{name}: yalnızca kimlik numaralı (ITOC) CPK arşivleri desteklenmiyor.",
                "Bu arşivde dosya adları yok; metin dosyaları bulunamaz.",
            )
        toc_offset = h.get(0, "TocOffset")
        content_offset = h.get(0, "ContentOffset")
        if not isinstance(toc_offset, int) or not isinstance(content_offset, int):
            raise ArchiveError(f"{name}: CPK başlığında TOC veya içerik ofseti yok.")
        self.toc_offset = toc_offset
        self.content_offset = content_offset
        self._toc_chunk, self.toc = _read_chunk(storage, toc_offset, b"TOC ", name)
        self._base = min(toc_offset, content_offset)
        self.entries: dict[str, CpkEntry] = {}
        for row in range(self.toc.row_count):
            folder = str(self.toc.get(row, "DirName") or "")
            file_name = str(self.toc.get(row, "FileName") or "")
            size, extract, offset = (self.toc.get(row, c) for c in ("FileSize", "ExtractSize", "FileOffset"))
            if not isinstance(size, int) or not isinstance(extract, int) or not isinstance(offset, int):
                raise ArchiveError(f"{name}: CPK dosya kaydı {row} eksik.")
            member = f"{folder}/{file_name}" if folder else file_name
            absolute = self._base + offset
            if absolute + size > storage.size:
                raise ArchiveError(f"{name}: '{member}' arşivin dışına taşıyor.")
            self.entries[member] = CpkEntry(member, row, absolute, size, extract)

    def read(self, member: str) -> bytes:
        entry = self.entries.get(member)
        if entry is None:
            raise ArchiveError(f"{self.name} içinde '{member}' yok.")
        raw = self.storage.read(entry.offset, entry.size)
        if entry.size == entry.extract_size and not raw.startswith(LAYLA_MAGIC):
            return raw
        data = decompress_layla(raw)
        if len(data) != entry.extract_size:
            raise ArchiveError(f"{self.name}: '{member}' açıldı ama boyutu kayıtla uyuşmuyor.")
        return data

    def rebuild(self, changes: dict[str, bytes]) -> bytes:
        """Değişen dosyalar sıkıştırılmadan konmuş yeni arşiv baytları."""
        if self.storage.size > MAX_REBUILD:
            raise UnsupportedFormatError(
                f"{self.name} çok büyük ({self.storage.size / 1024**3:.1f} GB); yeniden yazılamaz.",
                "Bu arşivdeki metinler çevrilemez. Kaynak dil olarak oyunun dil arşivlerinden birini "
                "(ör. İngilizce) seçip metinleri yeniden aktarın.",
            )
        unknown = [m for m in changes if m not in self.entries]
        if unknown:
            raise ArchiveError(f"{self.name} içinde olmayan dosyalar yazılmak istendi: {', '.join(unknown[:3])}")
        h = self.header
        align = h.get(0, "Align")
        align = align if isinstance(align, int) and align > 0 else 1
        etoc = h.get(0, "EtocOffset")
        order = sorted(self.entries.values(), key=lambda e: e.offset)
        old_end = max((e.offset + e.size for e in order), default=self.content_offset)
        out = bytearray(self.storage.read(0, self.content_offset))
        toc = UtfTable(self.toc.to_bytes(), self.name)
        header = UtfTable(self.header.to_bytes(), self.name)
        packed = data_size = 0
        for entry in order:
            blob = changes.get(entry.name)
            extract = entry.extract_size
            if blob is None:
                blob = self.storage.read(entry.offset, entry.size)
            else:
                extract = len(blob)
            pad = (-len(out)) % align
            out += bytes(pad)
            toc.set(entry.row, "FileOffset", len(out) - self._base)
            toc.set(entry.row, "FileSize", len(blob))
            toc.set(entry.row, "ExtractSize", extract)
            out += blob
            packed += extract
            data_size += len(blob)
        new_end = len(out)
        tail_start = old_end
        if isinstance(etoc, int) and etoc:
            gap = etoc - (old_end + (-old_end) % align)
            out += bytes((-len(out)) % align + max(gap, 0))
            header.set(0, "EtocOffset", len(out))
            header.set(0, "ContentSize", len(out) - self.content_offset)
            tail_start = etoc
        elif h.get(0, "ContentSize") is not None:
            header.set(0, "ContentSize", new_end - self.content_offset)
        if h.get(0, "EnabledPackedSize") is not None:
            header.set(0, "EnabledPackedSize", packed)
        if h.get(0, "EnabledDataSize") is not None:
            header.set(0, "EnabledDataSize", data_size)
        out += self.storage.read(tail_start, self.storage.size - tail_start)
        header_bytes = header.to_bytes()
        toc_bytes = toc.to_bytes()
        out[_CHUNK.size : _CHUNK.size + len(header_bytes)] = header_bytes
        start = self.toc_offset + _CHUNK.size
        out[start : start + len(toc_bytes)] = toc_bytes
        return bytes(out)
