"""Devil May Cry (Switch) mesaj tabloları ve karakter kodlaması.

Ayrıntılar: docs/formats/dmc1.md.

- Mesaj tablosu: `u32 adet | adet × (u32 ofset, u32 uzunluk) | dizgiler`; ofsetler tablo başına göredir.
- Metin tek baytlık oyun tablosuyla kodlanır (ASCII değil). `0x7E xx` bir kontrol kodudur;
  bazı kodların ardından parametre baytları gelir. Dizgi `7E 0E p p` (konuşma süresi) ile biter,
  ardından sıfır dolgusu olabilir.
- Tabloda olmayan her bayt kayıpsız bir kontrol kodu olarak korunur.
"""

from __future__ import annotations

import struct
import unicodedata
from dataclasses import dataclass

from nxceviri.core.formats.base import ControlCode, FormatError
from nxceviri.core.translate import placeholders

ESCAPE = 0x7E
#: `.atm` dosyaları (başarım, galeri, gizlilik ekranı) aynı harf tablosunu ama `0x80` kaçış baytını kullanır.
ATM_ESCAPE = 0x80
CODE_SPACE = 0x05
CODE_NEWLINE = 0x0C
CODE_END = 0x0E
#: Kod → parametre bayt sayısı (belirtilmeyenler 0).
PARAMS = {0x08: 3, 0x09: 1, 0x0A: 1, 0x0B: 1, 0x0D: 2, 0x0E: 2}
_CODE_LABELS = {
    0x08: "Yazı kodu",
    0x09: "Yazı stili",
    0x0A: "Yazı stili",
    0x0B: "Yazı stili",
    0x0D: "Bekleme",
    0x0E: "Konuşma süresi / sayfa sonu",
    0x0F: "Seçenek işareti",
    0x10: "Düzen kodu",
    0x12: "Düzen kodu",
    0x13: "Düzen kodu",
}

_CHARS: dict[int, str] = {}
for _i, _c in enumerate("0123456789"):
    _CHARS[_i] = _c
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _CHARS[0x0E + _i] = _c
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _CHARS[0x28 + _i] = _c
_CHARS.update(
    {
        0x0A: "/",
        0x0B: "“",  # “
        0x0C: "”",  # ”
        0x0D: "'",
        0x43: ".",
        0x44: ",",
        0x45: ":",
        0x46: ";",
        0x49: "&",
        0x4A: "!",
        0x4B: "?",
        0x4C: "(",
        0x4D: ")",
        0x4E: "+",
        0x4F: "-",
    }
)
#: Türkçe harfler iki baytlık çiftlerle yazılır: `0x72` + yazı dokusundaki hücre kodu (`.atm` dosyalarında
#: yalnızca hücre kodu; cihazda görüldü). Bu düzen, Steam'deki
#: topluluk Türkçe yamasında (PC sürümü, aynı oyun motoru) kullanılan ve çalıştığı bilinen düzendir.
#: Sağdaki hücreler özgün (Switch) fontta zaten ç Ç ü Ü ö Ö glifini taşır; ğ Ğ ı İ ş Ş hücreleri başka
#: harflere (á í ú Ñ Ú …) aittir ve dokuya glif eklenmeden kullanılamaz.
PAIR_PREFIX = 0x72
PAIR_CHARS = {
    0x61: "ç",
    0x53: "Ç",
    0x6C: "ü",
    0x5E: "Ü",
    0x7A: "ö",
    0x78: "Ö",
    0x73: "ğ",
    0x60: "Ğ",
    0x74: "ı",
    0x6F: "İ",
    0x75: "ş",
    0x70: "Ş",
    0x46: ";",
}
#: Yamada geçen ama bu projenin yazmadığı çift.
_READ_ONLY_PAIRS = {0x79: "ä"}
#: Özgün yazı dokusunda glifi bulunmayan, font yamasız dışa aktarmada dönüştürülmesi gereken harfler.
UNSUPPORTED_LETTERS = "ğĞıİşŞ"
#: Tek baytlık kodlar (`;` yalnızca çiftle yazılır).
CHARS = {code: char for code, char in _CHARS.items() if char != ";"}
_BYTES = {c: b for b, c in CHARS.items()}
_PAIR_BYTES = {c: bytes((PAIR_PREFIX, b)) for b, c in PAIR_CHARS.items()}
_PAIR_DECODE = {**_READ_ONLY_PAIRS, **PAIR_CHARS}
#: Fontta olmayan tipografik işaretlerin en yakın karşılıkları (makine çevirisi bunları sık üretir).
_NORMALIZE = str.maketrans({"\u2019": "'", "\u2018": "'", "\u2013": "-", "\u2014": "-", "\u00a0": " "})
#: Yazı dokusunun hücreleri (kod → karakter): tek baytlık kodlar ve çiftlerin ikinci baytı.
#: Özgün yazı dokusundaki diğer hücreler (Switch `etc_u/msg_tex.t32`'den okundu). Oyun dokudaki her hücreyi
#: ölçtüğü için bunların da dolu olması gerekir: yalnızca kullanılan harfleri içeren bir doku oyunu
#: açılışta çökertti (yalnızca 0x47 boş olabilir; özgün dokuda da boştur).
ORIGINAL_CELLS = dict(
    zip(
        range(0x50, 0x80),
        "*ÀÂÇÉÈËÊÎÏÔŒÙÛÜàâçéèëêîïôœùûüÑÁÍÚÓñáíúóÄÖäöÌÒìò£",
        strict=True,
    )
)
ORIGINAL_CELLS.update({0x42: "ß", 0x46: ";", 0x48: "`"})
FONT_CELLS = {**ORIGINAL_CELLS, **CHARS, **PAIR_CHARS}

_ALIGN = 16


@dataclass(frozen=True)
class MessageTable:
    offset: int  # dosyadaki konum
    strings: tuple[tuple[int, int], ...]  # (mutlak ofset, uzunluk)
    first: int = 0  # ilk dizginin tabloya göre ofseti (başlık dolgusunu korumak için)

    @property
    def count(self) -> int:
        return len(self.strings)

    @property
    def end(self) -> int:
        off, length = self.strings[-1]
        return off + length


@dataclass(frozen=True)
class Message:
    text: str  # görünen metin (boşluk ve satır sonu düz; diğer kodlar ⟦n⟧)
    codes: tuple[ControlCode, ...]
    tail: bytes  # dizgiyi bitiren `7E 0E p p` ve sıfır dolgusu
    escape: int = ESCAPE  # kontrol kodlarının kaçış baytı (`.atm` dosyalarında 0x80)


def _align(value: int) -> int:
    return (value + _ALIGN - 1) & ~(_ALIGN - 1)


def parse_table(data: bytes, offset: int) -> MessageTable | None:
    """`offset`teki mesaj tablosu geçerliyse okur."""
    if offset < 0 or offset + 12 > len(data):
        return None
    count = struct.unpack_from("<I", data, offset)[0]
    base = 4 + 8 * count
    if not 1 <= count <= 4000 or offset + base > len(data):
        return None
    first = struct.unpack_from("<I", data, offset + 4)[0]
    # Başlık dolgusu 16 bayta hizalıdır; bazı tablolarda bir hizalama bloğu fazladır (r00e.fsd: 0x90, beklenen 0x80).
    if first not in (base, _align(base), _align(base) + _ALIGN):
        return None
    strings = []
    pos = first
    for k in range(count):
        off, length = struct.unpack_from("<II", data, offset + 4 + 8 * k)
        if length > 0x4000 or off not in (pos, _align(pos)):
            return None
        strings.append((offset + off, length))
        pos = off + length
    if offset + pos > len(data):
        return None
    return MessageTable(offset, tuple(strings), first)


def find_tables(data: bytes) -> list[MessageTable]:
    """Dosyada (4 bayta hizalı yerlerde) geçerli tüm mesaj tablolarını bulur."""
    n = len(data) // 4
    words = memoryview(data[: n * 4]).cast("I")
    tables = []
    i = 0
    while i < n - 3:
        count = words[i]
        if 1 <= count <= 4000 and words[i + 1] in (4 + 8 * count, _align(4 + 8 * count)):
            table = parse_table(data, i * 4)
            if table is not None:
                tables.append(table)
                i = max(i + 1, (table.end - 1) // 4)
                continue
        i += 1
    return tables


def decode(seg: bytes, escape: int = ESCAPE) -> Message:
    """Dizgiyi görünen metne ve kontrol kodlarına ayırır; `encode` ile birebir geri çevrilebilir."""
    tail_at = _tail_start(seg, escape)
    body, tail = seg[:tail_at], seg[tail_at:]
    out: list[str] = []
    codes: list[ControlCode] = []
    i = 0
    while i < len(body):
        b = body[i]
        if b == escape and i + 1 < len(body):
            code = body[i + 1]
            if code == CODE_SPACE:
                out.append(" ")
                i += 2
                continue
            if code == CODE_NEWLINE:
                out.append("\n")
                i += 2
                continue
            size = 2 + PARAMS.get(code, 0)
            raw = body[i : i + size]
            codes.append(ControlCode(raw, _CODE_LABELS.get(code, f"Kod 0x{code:02X}")))
            out.append(placeholders.token(len(codes)))
            i += size
            continue
        if escape == ATM_ESCAPE and b in PAIR_CHARS:
            out.append(PAIR_CHARS[b])
            i += 1
            continue
        if escape != ATM_ESCAPE and b == PAIR_PREFIX and i + 1 < len(body) and body[i + 1] in _PAIR_DECODE:
            out.append(_PAIR_DECODE[body[i + 1]])
            i += 2
            continue
        char = CHARS.get(b)
        if char is not None:
            out.append(char)
        else:
            codes.append(ControlCode(bytes((b,)), f"Bilinmeyen karakter 0x{b:02X}"))
            out.append(placeholders.token(len(codes)))
        i += 1
    return Message("".join(out), tuple(codes), tail, escape)


def _tail_start(seg: bytes, escape: int = ESCAPE) -> int:
    """Bitiş kodunun (`7E 0E p p` + yalnızca sıfırlar) konumu; yoksa sondaki sıfır dolgusunun başı."""
    i = 0
    while i < len(seg):
        if seg[i] == escape and i + 1 < len(seg):
            code = seg[i + 1]
            if code == CODE_END and not seg[i + 4 :].strip(b"\0"):
                return i
            i += 2 + PARAMS.get(code, 0)
        else:
            i += 1
    return len(seg.rstrip(b"\0"))


_KEEP = frozenset(" \n\u27e6\u27e7")  # boşluk, satır sonu ve ⟦ ⟧ yer tutucu işaretleri


def normalize(text: str) -> str:
    """Fontta olmayan işaretleri en yakın karşılıklarına çevirir: ’ – — … ve sert boşluk, ayrıca aksanlı harfler
    (â → a, é → e …; makine çevirisi bunları sık üretir). Karşılığı olmayan karakter olduğu gibi kalır."""
    text = text.translate(_NORMALIZE).replace("…", "...")
    out: list[str] = []
    for ch in text:
        if ch in _BYTES or ch in _PAIR_BYTES or ch in _KEEP:
            out.append(ch)
            continue
        base = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode("ascii")
        out.append(base or ch)
    return "".join(out)


def encode(message: Message, text: str | None = None, *, pad_to: int | None = None) -> bytes:
    """Metni (varsayılan: `message.text`) oyun baytlarına çevirir; kontrol kodları ve bitiş geri konur.

    `pad_to` verilirse bitiş kodu korunur ama sıfır dolgusu yeniden hesaplanır (uzunluk `pad_to`nun katı
    olur); verilmezse özgün kuyruk aynen eklenir (değişmemiş dizgide bayt bayt aynı sonuç).
    """
    text = message.text if text is None else text
    out = bytearray()
    for piece in placeholders.split(text):
        if isinstance(piece, int):
            if not 1 <= piece <= len(message.codes):
                raise FormatError(f"Bilinmeyen kontrol kodu ⟦{piece}⟧.")
            out += message.codes[piece - 1].raw
            continue
        for ch in normalize(piece):
            if ch == " ":
                out += bytes((message.escape, CODE_SPACE))
            elif ch == "\n":
                out += bytes((message.escape, CODE_NEWLINE))
            elif ch in _BYTES:
                out.append(_BYTES[ch])
            elif ch in _PAIR_BYTES:
                # `.atm` ekranları çifti tanımaz (0x72'yi "ñ" olarak çizer); harf, dokudaki hücresiyle tek bayt yazılır.
                out += _PAIR_BYTES[ch][1:] if message.escape == ATM_ESCAPE else _PAIR_BYTES[ch]
            else:
                raise FormatError(
                    f"'{ch}' karakteri oyunun fontunda yok.",
                    "Bu harf oyunun yazı tablosunda yok; harf dönüştürmeyi veya font yamasını kullanın.",
                )
    if pad_to is None:
        return bytes(out) + message.tail
    if message.tail[:2] == bytes((message.escape, CODE_END)):
        out += message.tail[: 2 + PARAMS[CODE_END]]
    out += bytes(-len(out) % pad_to)
    return bytes(out)


def build_table(strings: list[bytes], first: int | None = None) -> bytes:
    """Mesaj tablosu üretir: `adet | (ofset, uzunluk)… | dizgiler` (dizgiler ardışık, dolgu dizgilerin içinde)."""
    base = 4 + 8 * len(strings)
    pos = _align(base) if first is None else first
    head = bytearray(struct.pack("<I", len(strings)))
    for s in strings:
        head += struct.pack("<II", pos, len(s))
        pos += len(s)
    head += bytes(_align(base) - len(head) if first is None else first - len(head))
    return bytes(head) + b"".join(strings)
