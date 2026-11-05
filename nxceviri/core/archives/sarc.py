"""SARC arşivi okuma ve yeniden kurma.

Başlık (0x14): "SARC" | başlık boyutu u16 | BOM u16 (FEFF) | dosya boyutu u32 |
veri ofseti u32 | sürüm u16 | ayrılmış u16. Ardından SFAT (düğüm tablosu: ad hash'i,
öznitelik, veri başı, veri sonu) ve SFNT (4 bayta hizalı adlar).

Yeniden kurarken her dosyanın orijinal hizalaması (ofsetini bölen en büyük ikinin
kuvveti) korunur; hiçbir dosya değişmediyse çıktı orijinalle bayt bayt aynıdır.
Ayrıntılar: docs/formats/archives.md
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from nxceviri.core.errors import ArchiveError

MAGIC = b"SARC"
_MAX_ALIGN = 0x10000


@dataclass(frozen=True)
class SarcEntry:
    name: str
    data: bytes


@dataclass
class _Node:
    name_hash: int
    attrs: int
    name: str
    data: bytes
    alignment: int


@dataclass
class SarcArchive:
    """Bir SARC'ın yeniden kurulabilmesi için gereken tüm bilgisi."""

    endian: str
    version: int
    hash_key: int
    names_raw: bytes
    data_alignment: int
    trailing: bytes
    nodes: list[_Node] = field(default_factory=list)

    @property
    def entries(self) -> list[SarcEntry]:
        return [SarcEntry(n.name, n.data) for n in self.nodes]

    def get(self, name: str) -> bytes:
        for n in self.nodes:
            if n.name == name:
                return n.data
        raise ArchiveError(f"SARC içinde dosya bulunamadı: {name}")

    def replace(self, name: str, data: bytes) -> None:
        for n in self.nodes:
            if n.name == name:
                n.data = data
                return
        raise ArchiveError(f"SARC içinde dosya bulunamadı: {name}")


def _alignment(offset: int) -> int:
    if offset == 0:
        return _MAX_ALIGN
    return min(offset & -offset, _MAX_ALIGN)


def _align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


def read(data: bytes) -> SarcArchive:
    if len(data) < 0x14 or data[:4] != MAGIC:
        raise ArchiveError("SARC verisi geçersiz: imza yok.")
    bom = data[6:8]
    if bom == b"\xfe\xff":
        e = ">"
    elif bom == b"\xff\xfe":
        e = "<"
    else:
        raise ArchiveError("SARC verisi bozuk: bayt sırası işareti geçersiz.")
    header_size, _bom, _file_size, data_offset, version = struct.unpack_from(e + "HHIIH", data, 4)
    sfat = header_size
    if data[sfat : sfat + 4] != b"SFAT":
        raise ArchiveError("SARC verisi bozuk: SFAT tablosu yok.")
    sfat_header, node_count, hash_key = struct.unpack_from(e + "HHI", data, sfat + 4)
    nodes_start = sfat + sfat_header
    sfnt = nodes_start + node_count * 16
    if data[sfnt : sfnt + 4] != b"SFNT":
        raise ArchiveError("SARC verisi bozuk: SFNT tablosu yok.")
    (sfnt_header,) = struct.unpack_from(e + "H", data, sfnt + 4)
    names_start = sfnt + sfnt_header
    if not names_start <= data_offset <= len(data):
        raise ArchiveError("SARC verisi bozuk: veri ofseti geçersiz.")
    arc = SarcArchive(
        endian=e,
        version=version,
        hash_key=hash_key,
        names_raw=data[names_start:data_offset],
        data_alignment=_alignment(data_offset),
        trailing=b"",
    )
    last_end = data_offset
    for i in range(node_count):
        name_hash, attrs, start, end = struct.unpack_from(e + "IIII", data, nodes_start + i * 16)
        if attrs >> 24:
            name_off = names_start + (attrs & 0xFFFFFF) * 4
            name_end = data.find(b"\0", name_off)
            if name_end < 0 or name_off >= data_offset:
                raise ArchiveError("SARC verisi bozuk: dosya adı okunamadı.")
            name = data[name_off:name_end].decode("utf-8", errors="replace")
        else:
            name = f"{name_hash:08x}.bin"
        if not data_offset + start <= data_offset + end <= len(data):
            raise ArchiveError(f"SARC verisi bozuk: '{name}' arşivin dışına taşıyor.")
        arc.nodes.append(
            _Node(
                name_hash, attrs, name, data[data_offset + start : data_offset + end], _alignment(data_offset + start)
            )
        )
        last_end = max(last_end, data_offset + end)
    arc.trailing = data[last_end:]
    return arc


def parse(data: bytes) -> list[SarcEntry]:
    return read(data).entries


def build(arc: SarcArchive) -> bytes:
    """Arşivi yeniden kurar. Dosyalar orijinal sırayla ve orijinal hizalamalarıyla yerleşir."""
    e = arc.endian
    sfat = b"SFAT" + struct.pack(e + "HHI", 0xC, len(arc.nodes), arc.hash_key)
    sfnt = b"SFNT" + struct.pack(e + "HH", 8, 0)
    header_len = 0x14 + len(sfat) + len(arc.nodes) * 16 + len(sfnt) + len(arc.names_raw)
    data_offset = _align(header_len, arc.data_alignment) if arc.nodes else header_len
    body = bytearray()
    node_table = bytearray()
    pos = data_offset
    for n in arc.nodes:
        start = _align(pos, n.alignment)
        body += b"\0" * (start - pos)
        body += n.data
        node_table += struct.pack(
            e + "IIII", n.name_hash, n.attrs, start - data_offset, start - data_offset + len(n.data)
        )
        pos = start + len(n.data)
    total = pos + len(arc.trailing)
    head = MAGIC + struct.pack(e + "HHIIHH", 0x14, 0xFEFF, total, data_offset, arc.version, 0)
    out = head + sfat + bytes(node_table) + sfnt + arc.names_raw
    out += b"\0" * (data_offset - len(out))
    return bytes(out + body + arc.trailing)
