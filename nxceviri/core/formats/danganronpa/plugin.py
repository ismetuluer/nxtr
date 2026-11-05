"""Danganronpa (Spike Chunsoft) metin eklentisi: `.lin` betikleri ve `.pak` metin tabloları.

Dosyalar `dr1_data.wad` arşivinin `Dr1/data/<dil>/script/` klasöründedir (`us`, `jp`, `ch`).

`.lin` (küçük sonlu):
- Başlık: tür u32 (1: metinsiz, 2: metinli) | başlık boyutu u32 | [tür 2] metin bloğu ofseti u32 |
  dosya boyutu u32. Ardından `0x70 <komut> <bağımsız değişkenler>` biçiminde betik komutları.
- Metin bloğu: dizge sayısı u32 | (sayı + 1) × ofset u32 (bloğun başına göre; sonuncusu bloğun sonu) |
  dizgeler. Blok sıfırlarla 4 bayta hizalanır. Komutlar dizgelere sıra numarasıyla başvurur; bu yüzden
  dizgelerin uzunluğu değişse de betik bölümüne dokunmak gerekmez.

`.pak`: öğe sayısı u32 | sayı × ofset u32 (dosyanın başına göre) | öğeler, boşluksuz art arda.
`script/` klasöründeki pak'lar ya metin tablosudur (her öğe bir dizge: `04_ItemName.pak`) ya da öğeleri
`.lin` betikleri olan betik paketidir (`script_pak_e01.pak`).

Dizgeler: UTF-16LE, `FF FE` BOM'u ile başlar ve `00 00` ile biter. Satır sonu metnin parçasıdır.
`<CLT 4>…<CLT>` biçim (renk) etiketleri kontrol kodudur (`⟦n⟧` olur).

Yazma: yalnızca dizgeler yeniden dizilir; ofsetler ve boyut alanları güncellenir. Ayrıntılar:
docs/formats/danganronpa.md
"""

from __future__ import annotations

import re
import struct
from collections.abc import Mapping

from nxceviri.core.formats.base import Context, ControlCode, FormatError, TextEntry
from nxceviri.core.translate import markup, placeholders

BOM = b"\xff\xfe"
_END = b"\0\0"
_LIN_PLAIN = 1
_LIN_TEXT = 2
_LIN_TEXT_HEADER = 16
_LIN_PLAIN_HEADER = 12
_U32 = struct.Struct("<I")
_TAG_RE = re.compile(r"<CLT(?: \d{1,3})?>")
#: Anahtarlarda betik paketinin öğe numarasıyla dizge numarasını ayıran işaret ("3.12").
_ITEM_SEPARATOR = "."


def _label(tag: str) -> str:
    return "Biçim/renk sonu <CLT>" if tag == "<CLT>" else f"Biçim/renk {tag}"


def tokenize(text: str) -> tuple[str, tuple[ControlCode, ...]]:
    return markup.tokenize(text, _TAG_RE, _label)


def decode(raw: bytes) -> str | None:
    """BOM'lu ve sonlandırılmış UTF-16LE dizge; bu biçimde değilse None."""
    if not raw.startswith(BOM) or not raw.endswith(_END) or len(raw) % 2:
        return None
    try:
        return raw[len(BOM) : -len(_END)].decode("utf-16-le")
    except UnicodeDecodeError:
        return None


def encode(text: str) -> bytes:
    return BOM + text.encode("utf-16-le", "surrogatepass") + _END


def _u32(data: bytes, pos: int, what: str) -> int:
    if pos + 4 > len(data):
        raise FormatError(f"{what} kesik: {pos:#x} konumunda veri bitiyor.")
    return int(_U32.unpack_from(data, pos)[0])


def parse_lin(data: bytes) -> tuple[int, list[bytes]] | None:
    """Metinli betik için (metin bloğu ofseti, ham dizgeler); metinsiz betik için None."""
    kind = _u32(data, 0, "LIN başlığı")
    if kind == _LIN_PLAIN:
        return None
    if kind != _LIN_TEXT:
        raise FormatError(f"LIN betiği değil (tür {kind}).")
    header = _u32(data, 4, "LIN başlığı")
    text_offset = _u32(data, 8, "LIN başlığı")
    size = _u32(data, 12, "LIN başlığı")
    if size != len(data) or not header <= text_offset <= len(data) - 4:
        raise FormatError("LIN başlığı dosya boyutuyla uyuşmuyor.")
    count = _u32(data, text_offset, "LIN metin bloğu")
    offsets = [_u32(data, text_offset + 4 + 4 * i, "LIN metin bloğu") for i in range(count + 1)]
    if offsets != sorted(offsets) or offsets[0] != 8 + 4 * count or text_offset + offsets[-1] > len(data):
        raise FormatError("LIN metin bloğunun ofset tablosu bozuk.")
    strings = [data[text_offset + offsets[i] : text_offset + offsets[i + 1]] for i in range(count)]
    if data[text_offset + offsets[-1] :].strip(b"\0"):
        raise FormatError("LIN metin bloğundan sonra beklenmeyen veri var.")
    return text_offset, strings


def build_lin(data: bytes, text_offset: int, strings: list[bytes]) -> bytes:
    first = 8 + 4 * len(strings)
    offsets = [first]
    for s in strings:
        offsets.append(offsets[-1] + len(s))
    block = struct.pack(f"<I{len(offsets)}I", len(strings), *offsets) + b"".join(strings)
    out = bytearray(data[:text_offset] + block)
    out += bytes(-len(out) % 4)
    struct.pack_into("<I", out, 12, len(out))
    return bytes(out)


def parse_pak(data: bytes) -> list[bytes]:
    count = _u32(data, 0, "PAK başlığı")
    first = 4 + 4 * count
    if count == 0 or first > len(data):
        raise FormatError("PAK başlığı bozuk.")
    offsets = [_u32(data, 4 + 4 * i, "PAK başlığı") for i in range(count)] + [len(data)]
    if offsets[0] != first or offsets != sorted(offsets):
        raise FormatError("PAK ofset tablosu bozuk veya öğeler arasında boşluk var.")
    return [data[offsets[i] : offsets[i + 1]] for i in range(count)]


def build_pak(items: list[bytes]) -> bytes:
    offsets = [4 + 4 * len(items)]
    for item in items[:-1]:
        offsets.append(offsets[-1] + len(item))
    return struct.pack(f"<I{len(offsets)}I", len(items), *offsets) + b"".join(items)


def is_text_lin(data: bytes) -> bool:
    """Metinli LIN başlığı: tür 2, başlık 16 bayt, boyut alanı dosyanın boyutu.

    PAK ile karışmaz: iki öğeli bir PAK'ın ikinci alanı (ilk ofset) 16 değil 12'dir.
    """
    if len(data) < _LIN_TEXT_HEADER:
        return False
    kind, header, _text, size = struct.unpack_from("<IIII", data)
    return bool(kind == _LIN_TEXT and header == _LIN_TEXT_HEADER and size == len(data))


def is_plain_lin(data: bytes) -> bool:
    """Metinsiz LIN başlığı: tür 1, başlık 12 bayt, boyut alanı dosyanın boyutu (tek öğeli PAK'ta ikinci alan 8'dir)."""
    if len(data) < _LIN_PLAIN_HEADER:
        return False
    kind, header, size = struct.unpack_from("<III", data)
    return bool(kind == _LIN_PLAIN and header == _LIN_PLAIN_HEADER and size == len(data))


def _is_lin(item: bytes) -> bool:
    return is_text_lin(item) or is_plain_lin(item)


def _translatable(text: str | None) -> bool:
    return bool(text) and any(ch.isalpha() for ch in _TAG_RE.sub("", text or ""))


def _apply(key: str, raw: bytes, new: str) -> bytes:
    original = decode(raw)
    if not _translatable(original):
        raise FormatError(f"Dosyada olmayan satır için çeviri verildi: {key}")
    source, codes = tokenize(original or "")
    issues = placeholders.problems(source, new)
    if issues:
        raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
    text = markup.detokenize(new, codes)
    if "\0" in text:
        raise FormatError(f"'{key}' çevirisinde boş karakter (NUL) olamaz.")
    return encode(text)


class _Document:
    """Bir dosyadaki dizge grupları: (anahtar öneki, ham dizgeler) ve geri kurma işlevi."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.lin = is_text_lin(data)
        self.groups: list[tuple[str, list[bytes]]] = []
        self._lins: list[tuple[bytes, int] | None] = []  # betik paketinde öğe başına (veri, metin ofseti)
        if self.lin:
            parsed = parse_lin(data)
            assert parsed is not None  # is_text_lin tür 2'yi doğruladı
            self._text_offset = parsed[0]
            self.groups.append(("", parsed[1]))
            return
        items = parse_pak(data)
        if all(item.startswith(BOM) for item in items):
            self.groups.append(("", items))
            self._items = items
            return
        if not all(_is_lin(item) for item in items):
            raise FormatError("Bu PAK dosyası metin tablosu veya betik paketi değil.")
        self._items = items
        for i, item in enumerate(items):
            parsed = parse_lin(item)
            self._lins.append(None if parsed is None else (item, parsed[0]))
            if parsed is not None:
                self.groups.append((f"{i}{_ITEM_SEPARATOR}", parsed[1]))

    def build(self) -> bytes:
        if self.lin:
            return build_lin(self.data, self._text_offset, self.groups[0][1])
        if not self._lins:
            return build_pak(self.groups[0][1])
        strings = dict(self.groups)
        items = []
        for i, lin in enumerate(self._lins):
            group = strings.get(f"{i}{_ITEM_SEPARATOR}")
            items.append(self._items[i] if lin is None or group is None else build_lin(lin[0], lin[1], group))
        return build_pak(items)


class DanganronpaPlugin:
    name = "danganronpa"
    label = "Danganronpa (.lin betikleri, .pak metin tabloları)"
    candidates_only = True
    path_suffixes: tuple[str, ...] = (".lin", ".pak")

    def detect(self, path: str, head: bytes) -> bool:
        if len(head) < 8:
            return False
        first, second = struct.unpack_from("<II", head)
        if path.lower().endswith(".lin"):
            return first in (_LIN_PLAIN, _LIN_TEXT)
        return path.lower().endswith(".pak") and first > 0 and second == 4 + 4 * first

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        return {}

    def language(self, data: bytes) -> str | None:
        return None  # dil klasör adından anlaşılır (`Dr1/data/us/`)

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        if is_plain_lin(data):
            return []  # metinsiz betik
        doc = _Document(data)
        entries: list[TextEntry] = []
        for prefix, strings in doc.groups:
            for i, raw in enumerate(strings):
                text = decode(raw)
                if text is None or not _translatable(text):
                    continue
                source, codes = tokenize(text)
                note = f"Betik {prefix[:-1]}" if prefix else ""
                entries.append(TextEntry(f"{prefix}{i}", len(entries), source, codes, context=note))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        if not translations:
            return data
        doc = _Document(data)
        groups = dict(doc.groups)
        for key, new in translations.items():
            prefix, _, index = key.rpartition(_ITEM_SEPARATOR)
            group = groups.get(f"{prefix}{_ITEM_SEPARATOR}" if prefix else "")
            if group is None or not index.isdigit() or int(index) >= len(group):
                raise FormatError(f"Dosyada olmayan satır için çeviri verildi: {key}")
            group[int(index)] = _apply(key, group[int(index)], new)
        return doc.build()
