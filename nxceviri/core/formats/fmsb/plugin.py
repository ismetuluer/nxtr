"""Vanillaware FMSB "MsgSheet" eklentisi (Unicorn Overlord `MsgSheet/*.fms`).

Yapı (küçük sonlu):
- Başlık 0x20: `FMSB` | veri boyutu u32 (dosya − 0x30) | başlık boyutu u32 (0x20) | 0 | 0 |
  dizge sayısı u32 | 3 | 0.
- Dizge sayısı × 8 baytlık tablo: dosyada sıfırdır, oyun yüklerken işaretçilerle doldurur.
- Dizgeler: sırayla, sıfırla biten UTF-8. Sıra numarası dizgenin kimliğidir; boş dizgeler boş yuvadır.
- Sıfır dolgu (16 bayta hizalı), sonra 16 baytlık `FEOC` sonu.

Metin kodları (`⟦n⟧` olur): `#c(12)…#/c` renk, `#s(0.8)…#/s` boyut, `#i…#/i` eğik, `#b` kalın,
`#w(40)` bekleme, `#(56)` simge, `#FN(…)`/`#CN(…)` yer/karakter adı, `@c(18)…@/c`, `^1/…^`
vurgu, `%s`/`%d` değişken, `<br>`, `<1>` gibi yerleşim etiketleri. Satır sonu metnin parçasıdır.

Yazma: dizgeler yeniden dizilir, tablo (sıfırlar) ve `FEOC` sonu korunur, boyut alanı güncellenir.
Ayrıntılar: docs/formats/unicorn-overlord.md
"""

from __future__ import annotations

import re
import struct
from collections.abc import Mapping

from nxceviri.core.formats.base import Context, ControlCode, FormatError, TextEntry
from nxceviri.core.translate import markup, placeholders

MAGIC = b"FMSB"
FOOTER = b"FEOC"
_HEADER_SIZE = 0x20
_FOOTER_SIZE = 0x10
_ALIGN = 16

_CODE_RE = re.compile(
    r"[#@]/[A-Za-z]"  # kapanış: #/c, #/i, @/c
    r"|[#@][A-Za-z]{0,3}\([^()\n]*\)"  # #c(12), #s(0.8), #(56), #FN(…), @c(18)
    r"|#[ib](?=\S)"  # #iyou#/i, #bCAST
    r"|\^\d+/|\^"  # ^1/Liberation^
    r"|%[-+0-9.]*[sdf]"
    r"|<[A-Za-z0-9/]{1,8}>"  # <br>, <1>, <C>
)
#: Bölüm işaretleri (`##(START)`): oyun içi kimliktir, çevrilmez.
_SECTION_RE = re.compile(r"##\([^()]*\)")
#: Kana ve kanji (kodlar çıkarıldıktan sonra; `#FN(…町)` gibi ad kodları İngilizce metinde de geçer).
_JAPANESE = re.compile("[\\u3040-\\u30ff\\u4e00-\\u9fff]")

_LABELS = {
    "#/c": "Renk sonu",
    "@/c": "Renk sonu",
    "#/i": "Eğik yazı sonu",
    "#/s": "Boyut sonu",
    "#/b": "Kalın yazı sonu",
    "#i": "Eğik yazı",
    "#b": "Kalın yazı",
    "^": "Vurgu sonu",
    "<br>": "Satır sonu <br>",
}


def _label(code: str) -> str:
    if code in _LABELS:
        return f"{_LABELS[code]} {code}"
    if code.startswith(("#c(", "@c(")):
        return f"Renk {code}"
    if code.startswith("#s("):
        return f"Yazı boyutu {code}"
    if code.startswith("#w("):
        return f"Bekleme {code}"
    if code.startswith("#("):
        return f"Simge {code}"
    if code.startswith(("#FN(", "#CN(")):
        return f"Ad değişkeni {code}"
    if code.startswith("^"):
        return f"Vurgu {code}"
    if code.startswith("%"):
        return f"Değişken {code}"
    if code.startswith("<"):
        return f"Yerleşim etiketi {code}"
    return f"Kontrol kodu {code}"


def tokenize(text: str) -> tuple[str, tuple[ControlCode, ...]]:
    out: list[str] = []
    codes: list[ControlCode] = []
    pos = 0
    for m in _CODE_RE.finditer(text):
        out.append(text[pos : m.start()])
        codes.append(ControlCode(m.group().encode("utf-8"), _label(m.group())))
        out.append(placeholders.token(len(codes)))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out), tuple(codes)


def _translatable(text: str) -> bool:
    if not text or _SECTION_RE.fullmatch(text):
        return False
    return any(ch.isalpha() for ch in _CODE_RE.sub("", text))


def parse(data: bytes) -> tuple[list[bytes], int]:
    """Dizgeler ve dizge bölümünün bittiği yer."""
    if len(data) < _HEADER_SIZE + _FOOTER_SIZE or not data.startswith(MAGIC):
        raise FormatError("FMSB dosyası değil veya kesik.")
    size, header_size = struct.unpack_from("<II", data, 4)
    (count,) = struct.unpack_from("<I", data, 0x14)
    footer = len(data) - _FOOTER_SIZE
    if header_size != _HEADER_SIZE or size + _HEADER_SIZE + _FOOTER_SIZE != len(data):
        raise FormatError("FMSB başlığı dosya boyutuyla uyuşmuyor.")
    if data[footer : footer + 4] != FOOTER:
        raise FormatError("FMSB dosyasının sonu (FEOC) yok.")
    pos = _HEADER_SIZE + count * 8
    if pos > footer:
        raise FormatError("FMSB dizge tablosu dosyanın dışına taşıyor.")
    strings: list[bytes] = []
    for i in range(count):
        end = data.find(b"\0", pos, footer)
        if end < 0:
            raise FormatError(f"FMSB dizgesi {i} sonlanmamış.")
        strings.append(data[pos:end])
        pos = end + 1
    if data[pos:footer].strip(b"\0"):
        raise FormatError("FMSB dosyasında dizgelerden sonra beklenmeyen veri var.")
    return strings, pos


def build(data: bytes, strings: list[bytes]) -> bytes:
    (count,) = struct.unpack_from("<I", data, 0x14)
    table_end = _HEADER_SIZE + count * 8
    body = bytearray(data[:table_end])
    for s in strings:
        body += s + b"\0"
    body += bytes((-len(body)) % _ALIGN)
    body += data[-_FOOTER_SIZE:]
    struct.pack_into("<I", body, 4, len(body) - _HEADER_SIZE - _FOOTER_SIZE)
    return bytes(body)


def _decode(raw: bytes) -> str | None:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


class FmsbPlugin:
    name = "fmsb"
    label = "Vanillaware MsgSheet (Unicorn Overlord)"
    candidates_only = True
    path_suffixes: tuple[str, ...] = (".fms",)
    #: Oyunun fontları yalnızca Batı Avrupa harflerini (Latin-1) içeriyor: Rusça topluluk yaması Kiril
    #: harflerini Latin-1 karakterlerinin yerine yazmak zorunda kalmış. ç ö ü Latin-1'dedir; bu harfler
    #: değildir ve dışa aktarmada ğ→g, ş→s, ı→i, İ→I dönüştürülür (font yaması gelene kadar).
    unsupported_letters = "ğĞşŞıİ"

    def detect(self, path: str, head: bytes) -> bool:
        return head.startswith(MAGIC)

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        return {}

    def language(self, data: bytes) -> str | None:
        """Ana arşivlerdeki (`Unicorn.CPK`) sayfalar Japoncadır; dil CPK'larınınki yol adından anlaşılır.

        Japonca sayfalarda da Latin harfli satırlar (platform adları, kadro listesi) olduğundan ölçüt,
        dizgelerin %10'undan fazlasında kana/kanji bulunmasıdır (gerçek oyunda Japonca sayfalarda en az
        %24, İngilizce ve Fransızcada en çok %3).
        """
        try:
            strings, _end = parse(data)
        except FormatError:
            return None
        texts = [t for t in (_decode(s) for s in strings if s) if t]
        japanese = sum(1 for t in texts if _JAPANESE.search(_CODE_RE.sub("", t)))
        return "ja" if texts and japanese * 10 > len(texts) else None

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        strings, _end = parse(data)
        entries: list[TextEntry] = []
        for i, raw in enumerate(strings):
            text = _decode(raw)
            if text is None or not _translatable(text):
                continue
            source, codes = tokenize(text)
            entries.append(TextEntry(str(i), len(entries), source, codes))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        if not translations:
            return data
        strings, _end = parse(data)
        for key, new in translations.items():
            index = int(key) if key.isdigit() else -1
            original = _decode(strings[index]) if 0 <= index < len(strings) else None
            if original is None or not _translatable(original):
                raise FormatError(f"Dosyada olmayan satır için çeviri verildi: {key}")
            source, codes = tokenize(original)
            issues = placeholders.problems(source, new)
            if issues:
                raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
            text = markup.detokenize(new, codes)
            if "\0" in text:
                raise FormatError(f"'{key}' çevirisinde boş karakter (NUL) olamaz.")
            strings[index] = text.encode("utf-8")
        return build(data, strings)
