"""İçerik meta verileri: CNMT (TitleID, sürüm, içerik listesi), NACP (oyun adı) ve biletler.

Ayrıntılar: docs/formats/cnmt-nacp-ticket.md
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from nxceviri.core.errors import ContainerError, UnsupportedFormatError


class MetaType(IntEnum):
    APPLICATION = 0x80
    PATCH = 0x81
    ADD_ON_CONTENT = 0x82
    DELTA = 0x83


class CnmtContentType(IntEnum):
    META = 0
    PROGRAM = 1
    DATA = 2
    CONTROL = 3
    HTML_DOCUMENT = 4
    LEGAL_INFORMATION = 5
    DELTA_FRAGMENT = 6


@dataclass(frozen=True)
class ContentRecord:
    content_id: str  # 32 karakter küçük harf onaltılık
    size: int
    content_type: int
    id_offset: int


@dataclass(frozen=True)
class Cnmt:
    title_id: int
    version: int
    meta_type: int
    application_id: int  # yama ve DLC için ait olduğu ana oyun; ana oyun için kendisi
    contents: tuple[ContentRecord, ...]

    @property
    def title_id_hex(self) -> str:
        return f"{self.title_id:016X}"

    @property
    def application_id_hex(self) -> str:
        return f"{self.application_id:016X}"


def parse_cnmt(data: bytes) -> Cnmt:
    if len(data) < 0x20:
        raise ContainerError("İçerik meta verisi (CNMT) bozuk: çok kısa.")
    title_id, version, meta_type = struct.unpack_from("<QIB", data, 0)
    ext_size, content_count, _meta_count = struct.unpack_from("<HHH", data, 0x0E)
    if meta_type not in (MetaType.APPLICATION, MetaType.PATCH, MetaType.ADD_ON_CONTENT):
        if meta_type == MetaType.DELTA:
            raise UnsupportedFormatError("Delta güncelleme paketleri desteklenmiyor; tam güncelleme paketini kullanın.")
        raise UnsupportedFormatError(f"Bu paket bir oyun, güncelleme veya DLC değil (tür {meta_type:#x}).")
    if len(data) < 0x20 + ext_size + content_count * 0x38:
        raise ContainerError("İçerik meta verisi (CNMT) bozuk: içerik listesi eksik.")
    application_id = title_id
    if meta_type in (MetaType.PATCH, MetaType.ADD_ON_CONTENT) and ext_size >= 8:
        (application_id,) = struct.unpack_from("<Q", data, 0x20)
    contents = []
    base = 0x20 + ext_size
    for i in range(content_count):
        rec = data[base + i * 0x38 : base + (i + 1) * 0x38]
        content_id = rec[0x20:0x30].hex()
        size = int.from_bytes(rec[0x30:0x36], "little")
        contents.append(ContentRecord(content_id, size, rec[0x36], rec[0x37]))
    return Cnmt(title_id, version, meta_type, application_id, tuple(contents))


#: NACP dil sırası; arayüzde gösterilecek ad için önce İngilizce kayıtlara bakılır.
_NACP_LANG_PRIORITY = (0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 15, 2, 12, 13, 14)


@dataclass(frozen=True)
class Nacp:
    name: str
    publisher: str
    display_version: str


def parse_nacp(data: bytes) -> Nacp:
    if len(data) < 0x3070:
        raise ContainerError("Oyun bilgi dosyası (control.nacp) bozuk: çok kısa.")

    def text(raw: bytes) -> str:
        return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()

    name = publisher = ""
    for lang in _NACP_LANG_PRIORITY:
        entry = data[lang * 0x300 : (lang + 1) * 0x300]
        name = text(entry[:0x200])
        if name:
            publisher = text(entry[0x200:0x300])
            break
    return Nacp(name, publisher, text(data[0x3060:0x3070]))


_SIG_SIZES = {
    0x010000: 0x200 + 0x3C,
    0x010001: 0x100 + 0x3C,
    0x010002: 0x3C + 0x40,
    0x010003: 0x200 + 0x3C,
    0x010004: 0x100 + 0x3C,
    0x010005: 0x3C + 0x40,
}


@dataclass(frozen=True)
class Ticket:
    rights_id: bytes
    title_key_block: bytes  # şifreli başlık anahtarı (common bilette ilk 16 bayt)
    personalized: bool

    def __repr__(self) -> str:  # anahtar değerini asla göstermez
        return f"Ticket(rights_id={self.rights_id.hex().upper()}, personalized={self.personalized})"


def parse_ticket(data: bytes) -> Ticket:
    if len(data) < 4:
        raise ContainerError("Bilet (.tik) dosyası bozuk.")
    (sig_type,) = struct.unpack_from("<I", data, 0)
    skip = _SIG_SIZES.get(sig_type)
    if skip is None:
        raise ContainerError("Bilet (.tik) dosyası bozuk: imza türü tanınmıyor.")
    body = 4 + skip
    if len(data) < body + 0x180:
        raise ContainerError("Bilet (.tik) dosyası bozuk: çok kısa.")
    key_block = data[body + 0x40 : body + 0x140]
    key_type = data[body + 0x141]
    rights_id = data[body + 0x160 : body + 0x170]
    return Ticket(rights_id, key_block[:16], key_type == 1)
