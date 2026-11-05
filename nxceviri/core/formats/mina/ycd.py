"""Yacht Club "YCD" paketleri (Mina the Hollower `.yc`) — yalnızca okuma.

Yapı (ayrıntılar: docs/formats/mina-ycd.md):

- Dosya `YCD\\0` ile başlar. Metin tabloları dosyanın içinde, kendi kendini tarif eden
  nesneler olarak durur: önce sütun adlarını taşıyan bir **başlık satırı** (`ID`, `English`,
  `French`…), ardından her biri tek bir tablo satırı olan nesneler.
- Bir satır, sütun başına 16 baytlık bir **betimleyici**dir: `u32 0 | u32 uzunluk | u32 tür |
  i32 ofset`. Tür 0x10 ise ofset, betimleyicinin başından 8 bayt ilerisine göre işaretli bir
  konumdur ve orada `uzunluk` baytlık UTF-8 dizgi ile sonunda bir 0 bayt bulunur. Ofset −1 ise
  dizgi boştur. Satırın **son** betimleyicisinin türü negatif bir sayıdır (satır başına geri
  işaret); dizgi ofseti yine aynı biçimdedir.
- Aynı dizgi birden çok sütunda (ör. dile bağlı olmayan özel adlar) ortak havuzdan gösterilir;
  bu yüzden dizgiler betimleyicilerden okunur, bayt konumundan tahmin edilmez.

Bu modül dosyaya hiçbir şey yazmaz. Geri yazma henüz çözülmediği için yoktur.
"""

from __future__ import annotations

import re
import struct
from bisect import bisect_left
from dataclasses import dataclass

from nxceviri.core.formats.base import FormatError

MAGIC = b"YCD\0"
NUL = b"\0"
_ITEM = struct.Struct("<IIIi")
_ITEM_SIZE = _ITEM.size
_STRING = 0x10
_MAX_STRING = 0x4000
_NEGATIVE = 0x80000000
_NULL_OFFSET = -1
#: Dizgi betimleyicisi adayları: 0 | uzunluk | 0x10 | ofset.
_CANDIDATE = re.compile(rb"(?s)(?=\x00\x00\x00\x00.{4}\x10\x00\x00\x00)")
_LANGUAGE_COLUMNS = ("English", "French")


def is_ycd(head: bytes) -> bool:
    return head.startswith(MAGIC)


@dataclass(frozen=True)
class Row:
    offset: int
    cells: tuple[str, ...]


@dataclass(frozen=True)
class Table:
    offset: int
    header: tuple[str, ...]
    rows: tuple[Row, ...]

    @property
    def kind(self) -> str:
        """Tablonun türü: diyalog satırları, konuşmacı adları veya arayüz metinleri."""
        if "Trigger" in self.header:
            return "dialogue"
        if "Gender" in self.header:
            return "names"
        return "ui"

    def column(self, name: str) -> int:
        return self.header.index(name)


def _cell(data: bytes, pos: int, *, last: bool) -> str | None:
    """`pos`taki betimleyicinin dizgisi; betimleyici geçerli değilse None."""
    zero, length, kind, rel = _ITEM.unpack_from(data, pos)
    if zero or (kind < _NEGATIVE if last else kind != _STRING):
        return None
    if rel == _NULL_OFFSET:
        return "" if length == 0 else None
    target = pos + 8 + rel
    if length > _MAX_STRING or target < 0 or target + length >= len(data) or data[target + length] != 0:
        return None
    try:
        return data[target : target + length].decode("utf-8")
    except UnicodeDecodeError:
        return None


def _row(data: bytes, pos: int, width: int) -> tuple[str, ...] | None:
    if pos < 0 or pos + width * _ITEM_SIZE > len(data):
        return None
    cells = []
    for i in range(width):
        cell = _cell(data, pos + i * _ITEM_SIZE, last=i == width - 1)
        if cell is None:
            return None
        cells.append(cell)
    return tuple(cells)


def _header_at(data: bytes, pos: int) -> tuple[str, ...] | None:
    if _cell(data, pos, last=False) != "ID":
        return None
    width = 1
    while width < 64 and _cell(data, pos + width * _ITEM_SIZE, last=False) is not None:
        width += 1
    header = _row(data, pos, width + 1)  # son betimleyici özel türdedir
    if header is None or not all(name in header for name in _LANGUAGE_COLUMNS):
        return None
    return header


def _candidates(data: bytes) -> list[int]:
    return [m.start() for m in _CANDIDATE.finditer(data) if m.start() % 4 == 0]


def read_tables(data: bytes) -> list[Table]:
    """Dosyadaki dil tablolarını (başlık + satırlar) dosyadaki sırayla döndürür."""
    if not is_ycd(data[:4]):
        raise FormatError("Bu bir Yacht Club YCD dosyası değil.", "Mina the Hollower'ın .yc dosyalarını seçin.")
    if b"\0English\0" not in data:
        return []
    candidates = _candidates(data)
    headers = [(pos, hdr) for pos in candidates if (hdr := _header_at(data, pos)) is not None]
    tables = []
    for i, (pos, header) in enumerate(headers):
        width = len(header)
        end = headers[i + 1][0] if i + 1 < len(headers) else len(data)
        rows: list[Row] = []
        next_ok = pos + width * _ITEM_SIZE
        for j in range(bisect_left(candidates, next_ok), len(candidates)):
            cand = candidates[j]
            if cand >= end:
                break
            if cand < next_ok:
                continue
            cells = _row(data, cand, width)
            if cells is not None and cells[0] != "":
                rows.append(Row(cand, cells))
                next_ok = cand + width * _ITEM_SIZE
        tables.append(Table(pos, header, tuple(rows)))
    return tables


def _target(data: bytes, pos: int) -> tuple[int, int]:
    """Betimleyicinin (dizgi konumu, uzunluk); boş dizgide konum -1."""
    _zero, length, _kind, rel = _ITEM.unpack_from(data, pos)
    return (-1 if rel == _NULL_OFFSET else pos + 8 + rel), length


def _owners(data: bytes, tables: list[Table]) -> dict[int, set[int]]:
    """Dizgi konumu → o dizgiyi gösteren tüm betimleyicilerin konumları (dosyanın her yerinden)."""
    owners: dict[int, set[int]] = {}
    for pos in _candidates(data):
        if _cell(data, pos, last=False) is None:
            continue
        target, _length = _target(data, pos)
        if target >= 0:
            owners.setdefault(target, set()).add(pos)
    for table in tables:  # son betimleyiciler adaylar arasında değildir
        for offset in (table.offset, *(row.offset for row in table.rows)):
            pos = offset + (len(table.header) - 1) * _ITEM_SIZE
            target, _length = _target(data, pos)
            if target >= 0:
                owners.setdefault(target, set()).add(pos)
    return owners


def _free_run(data: bytes, row_positions: list[int], owners: dict[int, set[int]]) -> tuple[int, int]:
    """Yalnızca bu satırın kullandığı dizgilerin birleşik en uzun bitişik bölgesi: (başlangıç, uzunluk)."""
    mine = set(row_positions)
    blocks = []
    for pos in row_positions:
        target, length = _target(data, pos)
        if target >= 0 and owners.get(target, set()) <= mine:
            blocks.append((target, length + 1))
    blocks = sorted(set(blocks))
    best = (0, 0)
    run_start = run_end = -1
    for start, size in blocks:
        if start <= run_end:  # örtüşen veya bitişik
            run_end = max(run_end, start + size)
        else:
            run_start, run_end = start, start + size
        if run_end - run_start > best[1]:
            best = (run_start, run_end - run_start)
    return best


def replace_language_texts(
    data: bytes, table: Table, tables: list[Table], edits: dict[int, str]
) -> tuple[bytes, list[int]]:
    """Seçilen satırların tüm dil sütunlarını verilen metinle değiştirir; dosya boyutu aynı kalır.

    Metin, satırın yalnızca kendisinin kullandığı dizgilerin boşalttığı bölgeye yazılır. Başka
    satırlarla paylaşılan kısa dizgilerde (ör. "Yes") bu bölge yetmez; o satırların metni, çevrilen
    diğer satırlarda artakalan boş yerlere yazılır. Hiçbir işaretçi taşınmaz, yalnızca çevrilen
    satırın betimleyicileri güncellenir. Yer bulunamayan satırlar değişmez ve ikinci değer olarak döner.
    """
    owners = _owners(data, tables)
    buf = bytearray(data)
    first_language = table.column(_LANGUAGE_COLUMNS[0])
    spare: list[tuple[int, int]] = []  # boşta kalan (başlangıç, uzunluk) parçaları
    late: list[int] = []

    def point(index: int, start: int, raw: bytes) -> None:
        buf[start : start + len(raw) + 1] = raw + NUL
        for pos in positions_of(index):
            struct.pack_into("<I", buf, pos + 4, len(raw))
            struct.pack_into("<i", buf, pos + 12, start - (pos + 8))

    def positions_of(index: int) -> list[int]:
        offset = table.rows[index].offset
        return [offset + i * _ITEM_SIZE for i in range(first_language, len(table.header))]

    for index, text in edits.items():
        raw = text.encode("utf-8")
        start, room = _free_run(data, positions_of(index), owners)
        if len(raw) + 1 > room:
            late.append(index)
            continue
        point(index, start, raw)
        if room > len(raw) + 1:
            spare.append((start + len(raw) + 1, room - len(raw) - 1))
    failed = []
    for index in sorted(late, key=lambda i: -len(edits[i])):
        raw = edits[index].encode("utf-8")
        fits = [s for s in spare if s[1] >= len(raw) + 1]
        if not fits:
            failed.append(index)
            continue
        start, room = min(fits, key=lambda s: s[1])
        spare.remove((start, room))
        point(index, start, raw)
        if room > len(raw) + 1:
            spare.append((start + len(raw) + 1, room - len(raw) - 1))
    return bytes(buf), failed
