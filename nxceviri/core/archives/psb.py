"""PSB (M2 / E-mote "PSB") okuma ve dizge tablosunu yerinde yeniden yazma.

Başlık: "PSB\\0" | sürüm u16 | şifreleme u16 | başlık boyu u32 | adlar | dizge ofsetleri |
dizge verisi | parça ofsetleri | parça boyları | parça verisi | kök değer (hepsi u32 ofset).
Sürüm 3+: 0x28'de Adler-32 sağlama toplamı (0x08–0x28 aralığının).
Sürüm 4: 0x2C–0x38'de ek parça ofsetleri / boyları / verisi; sağlama toplamı 0x08–0x28 ve
0x2C–0x38 aralıklarını birlikte kapsar.

Bölümler dosyada şu sırayla durur: başlık, adlar, kök değer, dizge ofsetleri, dizge verisi,
(ek parça bölümleri), parça ofsetleri, parça boyları, parça verisi. Değerler dizgelere dizinle
başvurur; bu yüzden dizge tablosu yeniden yazılınca kök ağaç olduğu gibi kalır, yalnızca
sonraki bölümlerin ofsetleri kayar. Kayma, parça verisinin hizalamasını korumak için dizge
verisinin sonuna NUL dolgu eklenerek hizalamanın katına yuvarlanır. Hiçbir dizge değişmezse
çıktı orijinalle bayt bayt aynıdır.
Ayrıntılar: docs/formats/m2.md
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from nxceviri.core.errors import ArchiveError, UnsupportedFormatError

MAGIC = b"PSB\0"
_SUPPORTED_VERSIONS = (2, 3, 4)
_CHECKSUM_VERSION = 3
_EXTRA_CHUNK_VERSION = 4
_MAX_ALIGN = 0x1000

T_NULL = 0x01
T_FALSE, T_TRUE = 0x02, 0x03
T_INT0, T_INT8 = 0x04, 0x0C
T_ARRAY1, T_ARRAY8 = 0x0D, 0x14
T_STR1, T_STR4 = 0x15, 0x18
T_CHUNK1, T_CHUNK4 = 0x19, 0x1C
T_FLOAT0, T_FLOAT, T_DOUBLE = 0x1D, 0x1E, 0x1F
T_LIST, T_OBJECT = 0x20, 0x21
_MAX_DEPTH = 64


@dataclass(frozen=True)
class Chunk:
    """İkili veri parçasına başvuru (parça tablosundaki dizin)."""

    index: int


class IntArray(list[int]):
    """Tamsayı dizisi değeri (tür 0x0D–0x14); tamsayılardan oluşan listeden (0x20) ayrı kodlanır."""


PsbValue = None | bool | int | float | str | Chunk | IntArray | list["PsbValue"] | dict[str, "PsbValue"]


@dataclass(frozen=True)
class _Header:
    version: int
    names: int
    strings: int
    string_data: int
    chunk_offsets: int
    chunk_lengths: int
    chunk_data: int
    root: int
    extra: tuple[int, ...]  # sürüm 4: ek parça ofsetleri, boyları, verisi

    @property
    def after_strings(self) -> int:
        """Dizge verisinden sonraki ilk bölümün başı."""
        return min((self.chunk_offsets, *self.extra))


def is_psb(data: bytes) -> bool:
    return data[:4] == MAGIC


def _uint(data: bytes, pos: int, width: int) -> int:
    if pos + width > len(data):
        raise ArchiveError("PSB verisi kısa: değer dosyanın sonunu aşıyor.")
    return int.from_bytes(data[pos : pos + width], "little")


def _read_header(data: bytes) -> _Header:
    if len(data) < 0x28 or not is_psb(data):
        raise ArchiveError("PSB verisi geçersiz: imza yok.")
    version, encrypted = struct.unpack_from("<HH", data, 4)
    if version not in _SUPPORTED_VERSIONS:
        raise UnsupportedFormatError(f"PSB sürüm {version} henüz desteklenmiyor (desteklenen: 2–4).")
    if encrypted:
        raise UnsupportedFormatError("Şifreli PSB başlığı desteklenmiyor.")
    if len(data) < _header_size(version):
        raise ArchiveError("PSB verisi kısa: başlık eksik.")
    names, strings, string_data, c_off, c_len, c_data, root = struct.unpack_from("<7I", data, 0x0C)
    extra = struct.unpack_from("<3I", data, 0x2C) if version >= _EXTRA_CHUNK_VERSION else ()
    h = _Header(version, names, strings, string_data, c_off, c_len, c_data, root, extra)
    if max((c_data, *extra)) > len(data):
        raise ArchiveError("PSB verisi kısa: bölümler dosyanın sonunu aşıyor.")
    order = (names, root, strings, string_data, *extra, c_off, c_len, c_data)
    if list(order) != sorted(order):
        raise UnsupportedFormatError("PSB bölümleri beklenmeyen sırada; bu dosya güvenle yeniden yazılamaz.")
    return h


def _header_size(version: int) -> int:
    if version >= _EXTRA_CHUNK_VERSION:
        return 0x38
    return 0x2C if version >= _CHECKSUM_VERSION else 0x28


def read_int_array(data: bytes, pos: int) -> tuple[list[int], int]:
    """Tamsayı dizisini okur; (değerler, dizinin bittiği konum) döndürür."""
    t = _uint(data, pos, 1)
    if not T_ARRAY1 <= t <= T_ARRAY8:
        raise ArchiveError(f"PSB verisi bozuk: {pos:#x} konumunda dizi bekleniyordu.")
    count_width = t - T_ARRAY1 + 1
    count = _uint(data, pos + 1, count_width)
    pos += 1 + count_width
    et = _uint(data, pos, 1)
    if not T_ARRAY1 <= et <= T_ARRAY8:
        raise ArchiveError(f"PSB verisi bozuk: {pos:#x} konumunda dizi öğe türü geçersiz.")
    width = et - T_ARRAY1 + 1
    pos += 1
    end = pos + count * width
    if end > len(data):
        raise ArchiveError("PSB verisi kısa: dizi dosyanın sonunu aşıyor.")
    return [int.from_bytes(data[pos + i * width : pos + (i + 1) * width], "little") for i in range(count)], end


def _width(value: int) -> int:
    return max(1, (value.bit_length() + 7) // 8)


def int_array_bytes(values: list[int]) -> bytes:
    width = _width(max(values, default=0))
    count_width = _width(len(values))
    out = bytearray([T_ARRAY1 + count_width - 1]) + len(values).to_bytes(count_width, "little")
    out.append(T_ARRAY1 + width - 1)
    for v in values:
        out += v.to_bytes(width, "little")
    return bytes(out)


def _decode_names(charset: list[int], tree: list[int], tails: list[int]) -> list[str]:
    names = []
    for tail in tails:
        out = bytearray()
        cur = tree[tail]
        for _ in range(len(tree)):
            if cur == 0:
                break
            parent = tree[cur]
            out.append((cur - charset[parent]) & 0xFF)
            cur = parent
        else:
            raise ArchiveError("PSB ad ağacı bozuk (döngü).")
        names.append(bytes(reversed(out)).decode("utf-8"))
    return names


class Psb:
    """Ayrıştırılmış bir PSB: adlar, dizgeler ve kök değer."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self._h = _read_header(data)
        try:
            charset, pos = read_int_array(data, self._h.names)
            tree, pos = read_int_array(data, pos)
            tails, _ = read_int_array(data, pos)
            self.names = _decode_names(charset, tree, tails)
            offsets, _ = read_int_array(data, self._h.strings)
            self.strings = [self._string_at(o) for o in offsets]
            self.chunk_offsets, _ = read_int_array(data, self._h.chunk_offsets)
            self.chunk_lengths, _ = read_int_array(data, self._h.chunk_lengths)
        except (IndexError, UnicodeDecodeError) as exc:
            raise ArchiveError(f"PSB verisi bozuk: {exc}") from exc

    @property
    def version(self) -> int:
        return self._h.version

    def _string_at(self, offset: int) -> str:
        start = self._h.string_data + offset
        end = self.data.find(b"\0", start, self._h.after_strings)
        if end < 0:
            raise ArchiveError("PSB dizge tablosu bozuk: sonlandırıcı yok.")
        return self.data[start:end].decode("utf-8")

    def chunk(self, index: int) -> bytes:
        if not 0 <= index < len(self.chunk_offsets):
            raise ArchiveError(f"PSB parça dizini geçersiz: {index}")
        start = self._h.chunk_data + self.chunk_offsets[index]
        return self.data[start : start + self.chunk_lengths[index]]

    def root(self) -> PsbValue:
        try:
            return self._value(self._h.root, 0)
        except IndexError as exc:
            raise ArchiveError(f"PSB değer ağacı bozuk: {exc}") from exc

    def string_refs(self) -> list[tuple[tuple[str | int, ...], int]]:
        """Kök ağaçtaki her dizge başvurusu: (ağaçtaki yol, dizge dizini), ağaç sırasıyla.

        Yol; nesne anahtarlarını (ad) ve liste dizinlerini (int) içerir. Aynı dizin birden çok yerde
        geçebilir (dizge tablosu tekilleştirilmiştir); bir dizgeyi değiştirmek hepsini değiştirir.
        """
        out: list[tuple[tuple[str | int, ...], int]] = []
        try:
            self._refs(self._h.root, (), 0, out)
        except IndexError as exc:
            raise ArchiveError(f"PSB değer ağacı bozuk: {exc}") from exc
        for _path, index in out:
            if index >= len(self.strings):
                raise ArchiveError(f"PSB dizge dizini tabloyu aşıyor: {index}")
        return out

    def _refs(
        self, pos: int, path: tuple[str | int, ...], depth: int, out: list[tuple[tuple[str | int, ...], int]]
    ) -> None:
        if depth > _MAX_DEPTH:
            raise ArchiveError("PSB değer ağacı çok derin (bozuk dosya).")
        d = self.data
        t = _uint(d, pos, 1)
        if T_STR1 <= t <= T_STR4:
            out.append((path, _uint(d, pos + 1, t - T_STR1 + 1)))
        elif t == T_LIST:
            offsets, base = read_int_array(d, pos + 1)
            for i, o in enumerate(offsets):
                self._refs(base + o, (*path, i), depth + 1, out)
        elif t == T_OBJECT:
            keys, p = read_int_array(d, pos + 1)
            offsets, base = read_int_array(d, p)
            if len(keys) != len(offsets):
                raise ArchiveError("PSB nesnesi bozuk: anahtar ve değer sayısı farklı.")
            for k, o in zip(keys, offsets, strict=True):
                self._refs(base + o, (*path, self.names[k]), depth + 1, out)

    def _value(self, pos: int, depth: int) -> PsbValue:
        if depth > _MAX_DEPTH:
            raise ArchiveError("PSB değer ağacı çok derin (bozuk dosya).")
        d = self.data
        t = _uint(d, pos, 1)
        if t == T_NULL:
            return None
        if t in (T_FALSE, T_TRUE):
            return t == T_TRUE
        if T_INT0 <= t <= T_INT8:
            return int.from_bytes(d[pos + 1 : pos + 1 + t - T_INT0], "little", signed=True)
        if T_ARRAY1 <= t <= T_ARRAY8:
            return IntArray(read_int_array(d, pos)[0])
        if T_STR1 <= t <= T_STR4:
            return self.strings[_uint(d, pos + 1, t - T_STR1 + 1)]
        if T_CHUNK1 <= t <= T_CHUNK4:
            return Chunk(_uint(d, pos + 1, t - T_CHUNK1 + 1))
        if t == T_FLOAT0:
            return 0.0
        if t == T_FLOAT:
            return float(struct.unpack_from("<f", d, pos + 1)[0])
        if t == T_DOUBLE:
            return float(struct.unpack_from("<d", d, pos + 1)[0])
        if t == T_LIST:
            offsets, base = read_int_array(d, pos + 1)
            return [self._value(base + o, depth + 1) for o in offsets]
        if t == T_OBJECT:
            keys, p = read_int_array(d, pos + 1)
            offsets, base = read_int_array(d, p)
            if len(keys) != len(offsets):
                raise ArchiveError("PSB nesnesi bozuk: anahtar ve değer sayısı farklı.")
            return {self.names[k]: self._value(base + o, depth + 1) for k, o in zip(keys, offsets, strict=True)}
        raise UnsupportedFormatError(f"PSB değer türü {t:#x} desteklenmiyor ({pos:#x} konumunda).")


def checksum(data: bytes) -> int:
    """Sürüm 3+ başlık sağlama toplamı (0x28'deki değerin kendisi hariç)."""
    covered = data[0x08:0x28]
    if struct.unpack_from("<H", data, 4)[0] >= _EXTRA_CHUNK_VERSION:
        covered += data[0x2C:0x38]
    return zlib.adler32(covered)


def _alignment(offset: int) -> int:
    return min(offset & -offset, _MAX_ALIGN) if offset else _MAX_ALIGN


def replace_strings(data: bytes, replacements: dict[int, str]) -> bytes:
    """Dizge tablosunda verilen dizinleri değiştirir; başka hiçbir değeri değiştirmez."""
    psb = Psb(data)
    strings = list(psb.strings)
    for index, text in replacements.items():
        if not 0 <= index < len(strings):
            raise ArchiveError(f"PSB dizge dizini geçersiz: {index}")
        if "\0" in text:
            raise ArchiveError("PSB dizgesi NUL karakteri içeremez.")
        strings[index] = text
    if strings == psb.strings:
        return data
    h = psb._h
    return _rebuild(data, h, data[h.root : h.strings], strings)


def replace_root(data: bytes, root: PsbValue) -> bytes:
    """Kök değer ağacını yeniden kodlar; ad ve dizge tabloları olduğu gibi kalır.

    Ağaç yalnızca dosyada zaten var olan adları ve dizgeleri kullanabilir (ör. arşiv dizininden
    girdi çıkarmak). Ağaç değişmediyse orijinal baytlar döner.
    """
    psb = Psb(data)
    if root == psb.root() and _same_kinds(root, psb.root()):
        return data
    blob = _Encoder(psb.names, psb.strings).encode(root, 0)
    out = _rebuild(data, psb._h, blob, psb.strings)
    if Psb(out).root() != root:
        raise ArchiveError("PSB yeniden kodlanamadı: okunan ağaç verilenle aynı değil.")
    return out


def _same_kinds(a: PsbValue, b: PsbValue) -> bool:
    """`==` IntArray ile listeyi ayırt etmez; kodlamayı değiştiren tür farkını ayrıca arar."""
    if isinstance(a, list) and isinstance(b, list):
        return isinstance(a, IntArray) == isinstance(b, IntArray) and all(
            _same_kinds(x, y) for x, y in zip(a, b, strict=True)
        )
    if isinstance(a, dict) and isinstance(b, dict):
        return all(_same_kinds(a[k], b[k]) for k in a)
    return type(a) is type(b)


class _Encoder:
    def __init__(self, names: list[str], strings: list[str]) -> None:
        self.names = {n: i for i, n in reversed(list(enumerate(names)))}
        self.strings = {s: i for i, s in reversed(list(enumerate(strings)))}

    def encode(self, v: PsbValue, depth: int) -> bytes:
        if depth > _MAX_DEPTH:
            raise ArchiveError("PSB değer ağacı çok derin.")
        if v is None:
            return bytes([T_NULL])
        if isinstance(v, bool):
            return bytes([T_TRUE if v else T_FALSE])
        if isinstance(v, int):
            if v == 0:
                return bytes([T_INT0])
            width = (v.bit_length() + 8) // 8  # işaretli
            if width > T_INT8 - T_INT0:
                raise ArchiveError(f"PSB tamsayısı 8 bayta sığmıyor: {v}")
            return bytes([T_INT0 + width]) + v.to_bytes(width, "little", signed=True)
        if isinstance(v, float):
            if v == 0.0:
                return bytes([T_FLOAT0])
            single = struct.pack("<f", v)
            if struct.unpack("<f", single)[0] == v:
                return bytes([T_FLOAT]) + single
            return bytes([T_DOUBLE]) + struct.pack("<d", v)
        if isinstance(v, str):
            index = self.strings.get(v)
            if index is None:
                raise ArchiveError("PSB ağacına yeni dizge eklenemez; dizgeleri replace_strings ile değiştirin.")
            return self._ref(T_STR1, index)
        if isinstance(v, Chunk):
            return self._ref(T_CHUNK1, v.index)
        if isinstance(v, IntArray):
            return int_array_bytes(v)
        if isinstance(v, list):
            return bytes([T_LIST]) + self._items([self.encode(x, depth + 1) for x in v])
        missing = [k for k in v if k not in self.names]
        if missing:
            raise ArchiveError(f"PSB ağacına yeni ad eklenemez: {missing[0]}")
        keys = int_array_bytes([self.names[k] for k in v])
        return bytes([T_OBJECT]) + keys + self._items([self.encode(x, depth + 1) for x in v.values()])

    @staticmethod
    def _ref(base: int, index: int) -> bytes:
        raw = index.to_bytes(_width(index), "little")
        if len(raw) > 4:
            raise ArchiveError(f"PSB dizini çok büyük: {index}")
        return bytes([base + len(raw) - 1]) + raw

    @staticmethod
    def _items(parts: list[bytes]) -> bytes:
        offsets, pos = [], 0
        for part in parts:
            offsets.append(pos)
            pos += len(part)
        return int_array_bytes(offsets) + b"".join(parts)


def _rebuild(data: bytes, h: _Header, root_blob: bytes, strings: list[str]) -> bytes:
    """Başlık ve adlar aynen; kök, dizge tablosu yeni; sonraki bölümler hizalamayı koruyarak kayar."""
    blob = bytearray()
    offsets = []
    for s in strings:
        offsets.append(len(blob))
        blob += s.encode("utf-8") + b"\0"
    table = int_array_bytes(offsets)
    new_strings = h.root + len(root_blob)
    new_string_data = new_strings + len(table)
    align = _alignment(h.chunk_data)
    blob += b"\0" * ((h.after_strings - (new_string_data + len(blob))) % align)
    shift = new_string_data + len(blob) - h.after_strings
    head = bytearray(data[: h.root])
    struct.pack_into(
        "<5I",
        head,
        0x10,
        new_strings,
        new_string_data,
        h.chunk_offsets + shift,
        h.chunk_lengths + shift,
        h.chunk_data + shift,
    )
    if h.extra:
        struct.pack_into("<3I", head, 0x2C, *(o + shift for o in h.extra))
    if h.version >= _CHECKSUM_VERSION:
        struct.pack_into("<I", head, 0x28, checksum(bytes(head)))
    return bytes(head) + root_blob + table + bytes(blob) + data[h.after_strings :]
