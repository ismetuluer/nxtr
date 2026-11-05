"""MSBT (Nintendo LMS "MsgStdBn") okuma ve geri yazma.

Yapı (ayrıntılar: docs/formats/msbt.md):

- Başlık 0x20: "MsgStdBn" | BOM u16 | ? u16 | kodlama u8 (0 UTF-8, 1 UTF-16, 2 UTF-32) |
  sürüm u8 | bölüm sayısı u16 | ? u16 | dosya boyutu u32 | 10 bayt dolgu.
- Bölümler: imza(4) | veri boyutu u32 | 8 bayt | veri | 0x10'a kadar 0xAB dolgusu.
  LBL1 (etiketler), ATR1 (öznitelikler), TSY1 (stil), NLI1, TXT2 (metinler)…
- TXT2: metin sayısı u32 | ofsetler u32[] (bölüm verisinin başına göre) | metinler.
  Metin içinde 0x0E = kontrol etiketi (grup u16, tür u16, parametre boyutu u16,
  parametreler), 0x0F = kapanış etiketi (grup u16, tür u16), 0x00 = metin sonu.

Geri yazarken yalnızca TXT2 yeniden kurulur; diğer bölümlerin baytları, dolgular ve
metin sonlarından sonra kalan baytlar aynen korunur.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from dataclasses import dataclass, field

from nxceviri.core.formats.base import Context, ControlCode, FormatError, TextEntry
from nxceviri.core.translate import placeholders

MAGIC = b"MsgStdBn"
_HEADER_SIZE = 0x20
_PAD = 0xAB

_ENCODINGS = {0: ("utf-8", 1), 1: ("utf-16", 2)}

#: Bilinen sistem etiketleri (grup 0). Diğerleri oyuna özgüdür.
_SYSTEM_TAGS = {0: "Okunuş (ruby)", 1: "Yazı tipi", 2: "Yazı boyutu", 3: "Renk", 4: "Sayfa sonu"}


@dataclass
class _Section:
    magic: bytes
    data: bytes
    header_pad: bytes  # bölüm başlığındaki 8 bayt
    trailing: bytes  # 0x10 hizalaması için eklenmiş dolgu


@dataclass
class _Text:
    segments: list[str | ControlCode]
    tail: bytes  # metin sonu işaretinden sonra, bir sonraki metne kadar kalan baytlar


@dataclass
class MsbtFile:
    endian: str  # "<" veya ">"
    encoding: int
    header: bytes
    sections: list[_Section]
    texts: list[_Text] = field(default_factory=list)
    labels: dict[int, str] = field(default_factory=dict)

    @property
    def codec(self) -> str:
        name, width = _ENCODINGS[self.encoding]
        if width == 2:
            return "utf-16-le" if self.endian == "<" else "utf-16-be"
        return name

    @property
    def width(self) -> int:
        return _ENCODINGS[self.encoding][1]


def _tag_label(group: int, tag: int, closing: bool) -> str:
    if closing:
        return f"Etiket sonu ({group}:{tag})"
    if group == 0 and tag in _SYSTEM_TAGS:
        return _SYSTEM_TAGS[tag]
    return f"Oyun etiketi {group}:{tag}"


def _decode_text(raw: bytes, f: MsbtFile) -> _Text:
    """Bir metin dilimini (sonraki metnin ofsetine kadar) çözümler."""
    e, w, codec = f.endian, f.width, f.codec
    segments: list[str | ControlCode] = []
    run = bytearray()
    pos = 0

    def unit(at: int) -> int:
        if at + w > len(raw):
            raise FormatError("MSBT metni bozuk: metin beklenenden önce bitti.")
        return raw[at] if w == 1 else int(struct.unpack_from(e + "H", raw, at)[0])

    def u16(at: int) -> int:
        if at + 2 > len(raw):
            raise FormatError("MSBT metni bozuk: kontrol etiketi yarım kalmış.")
        return int(struct.unpack_from(e + "H", raw, at)[0])

    def flush() -> None:
        if run:
            try:
                segments.append(run.decode(codec))
            except UnicodeDecodeError:
                raise FormatError("MSBT metni bozuk: geçersiz karakter kodlaması.") from None
            run.clear()

    while True:
        c = unit(pos)
        if c == 0:
            flush()
            return _Text(segments, raw[pos + w :])
        if c in (0x0E, 0x0F):
            flush()
            start = pos
            pos += w
            group, tag = u16(pos), u16(pos + 2)
            pos += 4
            if c == 0x0E:
                size = u16(pos)
                pos += 2 + size
                if pos > len(raw):
                    raise FormatError("MSBT metni bozuk: etiket parametreleri metnin dışına taşıyor.")
            segments.append(ControlCode(raw[start:pos], _tag_label(group, tag, c == 0x0F)))
            continue
        run += raw[pos : pos + w]
        pos += w


def read(data: bytes) -> MsbtFile:
    if len(data) < _HEADER_SIZE or not data.startswith(MAGIC):
        raise FormatError("Dosya bir MSBT değil (MsgStdBn imzası yok).")
    bom = data[8:10]
    if bom == b"\xff\xfe":
        e = "<"
    elif bom == b"\xfe\xff":
        e = ">"
    else:
        raise FormatError("MSBT bozuk: bayt sırası işareti geçersiz.")
    encoding = data[0x0C]
    if encoding not in _ENCODINGS:
        raise FormatError(f"MSBT metin kodlaması desteklenmiyor (kod {encoding}).")
    (count,) = struct.unpack_from(e + "H", data, 0x0E)
    f = MsbtFile(e, encoding, data[:_HEADER_SIZE], [])
    pos = _HEADER_SIZE
    for _ in range(count):
        if pos + 0x10 > len(data):
            raise FormatError("MSBT bozuk: bölüm başlığı dosyanın dışında.")
        magic = data[pos : pos + 4]
        (size,) = struct.unpack_from(e + "I", data, pos + 4)
        body = pos + 0x10
        end = body + size
        if end > len(data):
            raise FormatError(f"MSBT bozuk: {magic.decode(errors='replace')} bölümü dosyanın dışına taşıyor.")
        padded = min(len(data), (end + 0xF) & ~0xF)
        f.sections.append(_Section(magic, data[body:end], data[pos + 8 : body], data[end:padded]))
        pos = padded
    txt = _section(f, b"TXT2")
    if txt is None:
        raise FormatError("MSBT bozuk: metin bölümü (TXT2) yok.")
    f.texts = _parse_txt2(txt.data, f)
    lbl = _section(f, b"LBL1")
    if lbl is not None:
        f.labels = _parse_lbl1(lbl.data, e)
    return f


def _section(f: MsbtFile, magic: bytes) -> _Section | None:
    return next((s for s in f.sections if s.magic == magic), None)


def _parse_txt2(body: bytes, f: MsbtFile) -> list[_Text]:
    if len(body) < 4:
        raise FormatError("MSBT bozuk: TXT2 bölümü çok kısa.")
    (n,) = struct.unpack_from(f.endian + "I", body, 0)
    if 4 + 4 * n > len(body):
        raise FormatError("MSBT bozuk: TXT2 ofset tablosu bölümün dışına taşıyor.")
    offsets = list(struct.unpack_from(f"{f.endian}{n}I", body, 4))
    bounds = [*offsets, len(body)]
    if any(not 4 + 4 * n <= bounds[i] <= bounds[i + 1] <= len(body) for i in range(n)):
        raise FormatError("MSBT bozuk veya desteklenmeyen düzen: metin ofsetleri sıralı değil.")
    return [_decode_text(body[bounds[i] : bounds[i + 1]], f) for i in range(n)]


def _parse_lbl1(body: bytes, e: str) -> dict[int, str]:
    (buckets,) = struct.unpack_from(e + "I", body, 0)
    labels: dict[int, str] = {}
    for b in range(buckets):
        count, offset = struct.unpack_from(e + "II", body, 4 + b * 8)
        pos = offset
        for _ in range(count):
            if pos >= len(body):
                raise FormatError("MSBT bozuk: etiket tablosu bölümün dışına taşıyor.")
            length = body[pos]
            name = body[pos + 1 : pos + 1 + length].decode("utf-8", errors="replace")
            (index,) = struct.unpack_from(e + "I", body, pos + 1 + length)
            labels[index] = name
            pos += 1 + length + 4
    return labels


def _key(f: MsbtFile, index: int) -> str:
    return f.labels.get(index, f"#{index}")


def _display(text: _Text) -> tuple[str, tuple[ControlCode, ...]]:
    parts: list[str] = []
    codes: list[ControlCode] = []
    for seg in text.segments:
        if isinstance(seg, str):
            parts.append(seg)
        else:
            codes.append(seg)
            parts.append(placeholders.token(len(codes)))
    return "".join(parts), tuple(codes)


def _encode(f: MsbtFile, text: str, codes: tuple[ControlCode, ...], tail: bytes) -> bytes:
    out = bytearray()
    for piece in placeholders.split(text):
        if isinstance(piece, int):
            if not 1 <= piece <= len(codes):
                raise FormatError(f"Çeviride geçersiz kontrol kodu: {placeholders.token(piece)}")
            out += codes[piece - 1].raw
        else:
            try:
                out += piece.encode(f.codec)
            except UnicodeEncodeError:
                raise FormatError("Çeviride bu dosyanın kodlamasıyla yazılamayan karakter var.") from None
    out += b"\0" * f.width
    return bytes(out + tail)


def _build(f: MsbtFile, txt2: bytes) -> bytes:
    e = f.endian
    out = bytearray(f.header)
    for s in f.sections:
        data = txt2 if s.magic == b"TXT2" else s.data
        trailing = s.trailing
        if data is not s.data:
            # Orijinal bölüm dolgulanmışsa (son bölümde bazen dolgu yoktur) aynı baytla dolgula.
            was_padded = bool(s.trailing) or len(s.data) % 0x10 == 0
            trailing = (s.trailing[:1] or bytes([_PAD])) * ((-len(data)) % 0x10) if was_padded else b""
        out += s.magic + struct.pack(e + "I", len(data)) + s.header_pad + data + trailing
    struct.pack_into(e + "I", out, 0x12, len(out))
    return bytes(out)


class MsbtPlugin:
    name = "msbt"
    label = "MSBT (Nintendo LMS)"
    candidates_only = False
    path_suffixes: tuple[str, ...] = ()

    def detect(self, path: str, head: bytes) -> bool:
        return head.startswith(MAGIC)

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        return {}  # MSBT etiketleri dosyanın içinde; ek bağlam gerekmez

    def language(self, data: bytes) -> str | None:
        return None  # dil, dosyanın yolundan (ör. Mals/USen…) anlaşılır; içinde yazmaz

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        f = read(data)
        entries = []
        seen: set[str] = set()
        for i, text in enumerate(f.texts):
            key = _key(f, i)
            if key in seen:
                key = f"{key}#{i}"
            seen.add(key)
            source, codes = _display(text)
            entries.append(TextEntry(key, i, source, codes))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        f = read(data)
        entries = self.extract(data)
        known = {e.key for e in entries}
        unknown = [k for k in translations if k not in known]
        if unknown:
            raise FormatError(f"MSBT'de olmayan girdiler için çeviri verildi: {', '.join(unknown[:5])}")
        if not translations:
            return data
        e = f.endian
        n = len(f.texts)
        blobs = []
        for entry, text in zip(entries, f.texts, strict=True):
            new = translations.get(entry.key)
            if new is None:
                new = entry.source
            else:
                issues = placeholders.problems(entry.source, new)
                if issues:
                    raise FormatError(f"'{entry.key}' çevirisi yazılamadı: {' '.join(issues)}")
            blobs.append(_encode(f, new, entry.codes, text.tail))
        offsets = []
        pos = 4 + 4 * n
        for b in blobs:
            offsets.append(pos)
            pos += len(b)
        txt2 = struct.pack(f"{e}I{n}I", n, *offsets) + b"".join(blobs)
        return _build(f, txt2)
