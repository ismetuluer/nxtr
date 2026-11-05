"""Ys Origin metin eklentisi: harita betikleri (`.XSO`) ve arayüz dizgeleri (`loc/strings/*.xml`).

**XSO** (Falcom betik derlemesi, `data-<dil>.ni` arşivlerinin `LOC/<DİL>/` klasöründe):
- Başlık 0x24: `XSR\\0` | … | 0x1C: kod uzunluğu (u32 sayısı) | 0x20: dizge sayısı.
- 0x24'ten itibaren kod, ardından dizge sayısı × u32 ofset tablosu, ardından sıfırla biten UTF-8
  dizgeler. Kod dizgelere sıra numarasıyla başvurur; bu yüzden dizgeler serbestçe uzayıp kısalabilir.
- Dosya sonu 4 bayta sıfırla hizalanır.
- Dizge tablosunda diyalogların yanında betik kimlikleri de vardır (`V_180`, `OPEN`, `@Flag_Inv`).
  Kimlikler dillerde aynı kalır, metinler değişir: aynı betiğin Japonca kopyasıyla karşılaştırılarak
  yalnızca farklı olan dizgeler çevrilmek üzere alınır. Japonca kopya yoksa sezgisel bir kural
  kullanılır (boşluk, ASCII dışı harf veya cümle noktalaması içeren dizgeler).

**XML** (`<string id="…">metin</string>`): kimlik başına bir satır. XML varlıkları (`&amp;`) okunurken
çözülür, yazılırken yeniden kodlanır; değişmeyen satırların ham baytları korunur.

XSO'da `\\n` (ters bölü + n) satır sonudur ve tabloda gerçek satır sonu olarak gösterilir. XML'de satır sonu
zaten gerçek satır sonudur; ters bölü + n oyunda "¥n" olarak görünür, bu yüzden XML'de dönüştürülmez.
Kodlar: `<color:0xffff3232>`, `<color:>`, `<scale:1.3>`, `<ext:17>` (simge), `%s`, `%d`.
Ayrıntılar: docs/formats/ys-origin.md
"""

from __future__ import annotations

import re
import struct
from collections.abc import Mapping
from html import unescape

from nxceviri.core.formats.base import SOURCE_PATH, Context, ControlCode, FormatError, TextEntry
from nxceviri.core.formats.ysorigin.extras import derived_files
from nxceviri.core.translate import markup, placeholders

XSO_MAGIC = b"XSR\0"
_XSO_HEADER = 0x24
_XSO_ALIGN = 4
_XML_HEAD = re.compile(rb"\A(\xef\xbb\xbf)?\s*<\?xml[^>]*>\s*<dict>")
_XML_STRING = re.compile(r'<string id="([^"]*)">(.*?)</string>', re.DOTALL)
_CODE_RE = re.compile(r"<[a-z]+:[^<>\n]*>|%[-+0-9.]*[sdf]")
_IDENTIFIER = re.compile(r"[@$]?[A-Za-z0-9_\\]*")
_SENTENCE_END = re.compile(r"[.!?…]$")
_NEWLINE = "\\n"
#: Japonca betik kopyalarının bağlam anahtarı öneki (bağlam: ("ys-ja", "DATA/MAP/…/X.XSO") → dizgeler).
_REFERENCE = "ys-ja"
_REFERENCE_LANGUAGE = "JP"
_LOC_PATH = re.compile(r"(?:^|>)LOC/([A-Z]{2})/([^>]+)$", re.IGNORECASE)


def _label(code: str) -> str:
    if code.startswith("<color:"):
        return "Renk sonu <color:>" if code == "<color:>" else f"Renk {code}"
    if code.startswith("<scale:"):
        return f"Yazı boyutu {code}"
    if code.startswith("<ext:"):
        return f"Simge {code}"
    if code.startswith("%"):
        return f"Değişken {code}"
    return f"Kontrol kodu {code}"


def tokenize(text: str, *, escaped_newlines: bool = True) -> tuple[str, tuple[ControlCode, ...]]:
    """Oyun kodlarını ⟦n⟧ yer tutucularına çevirir; `escaped_newlines` ise `\\n` dizisini satır sonuna.

    XSO dizgelerinde satır sonu `\\n` yazılır. Arayüz XML'inde ise gerçek satır sonudur; oradaki `\\n`
    oyunda "¥n" olarak görünür, bu yüzden XML'de çevrilmez (`escaped_newlines=False`).
    """
    out: list[str] = []
    codes: list[ControlCode] = []
    pos = 0
    for m in _CODE_RE.finditer(text):
        out.append(text[pos : m.start()])
        codes.append(ControlCode(m.group().encode("utf-8"), _label(m.group())))
        out.append(placeholders.token(len(codes)))
        pos = m.end()
    out.append(text[pos:])
    joined = "".join(out)
    return (joined.replace(_NEWLINE, "\n") if escaped_newlines else joined.replace("\r\n", "\n")), tuple(codes)


def detokenize(display: str, codes: tuple[ControlCode, ...], *, escaped_newlines: bool = True) -> str:
    display = display.replace("\r\n", "\n")
    return markup.detokenize(display.replace("\n", _NEWLINE) if escaped_newlines else display, codes)


def _translatable(text: str) -> bool:
    return any(ch.isalpha() for ch in _CODE_RE.sub("", text))


def _looks_like_text(text: str) -> bool:
    """Japonca kopya olmadığında: dizge bir betik kimliği değil, oyuncuya gösterilen metin mi?"""
    if not _translatable(text):
        return False
    if " " in text or any(ord(ch) > 0x7F for ch in text):
        return True
    return _SENTENCE_END.search(text) is not None and _IDENTIFIER.fullmatch(text) is None


def _decode(raw: bytes) -> str | None:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


# --- XSO -------------------------------------------------------------------------------------


def parse_xso(data: bytes) -> tuple[list[bytes], int]:
    """Dizgeler ve dizge tablosunun başladığı yer."""
    if len(data) < _XSO_HEADER or not data.startswith(XSO_MAGIC):
        raise FormatError("XSO dosyası değil veya kesik.")
    code_words, count = struct.unpack_from("<II", data, 0x1C)
    table = _XSO_HEADER + code_words * 4
    pool = table + count * 4
    if pool > len(data):
        raise FormatError("XSO dizge tablosu dosyanın dışına taşıyor.")
    offsets = struct.unpack_from(f"<{count}I", data, table)
    strings: list[bytes] = []
    expected = 0
    for i, off in enumerate(offsets):
        if off != expected:
            raise FormatError(f"XSO dizgesi {i} beklenmeyen yerde; dosya bozuk olabilir.")
        end = data.find(b"\0", pool + off)
        if end < 0:
            raise FormatError(f"XSO dizgesi {i} sonlanmamış.")
        strings.append(data[pool + off : end])
        expected = end + 1 - pool
    if count and data[pool + expected :].strip(b"\0"):
        raise FormatError("XSO dosyasında dizgelerden sonra beklenmeyen veri var.")
    return strings, table


def build_xso(data: bytes, strings: list[bytes]) -> bytes:
    _strings, table = parse_xso(data)
    out = bytearray(data[:table])
    offsets = bytearray()
    pool = bytearray()
    for s in strings:
        offsets += struct.pack("<I", len(pool))
        pool += s + b"\0"
    out += offsets + pool
    out += bytes((-len(out)) % _XSO_ALIGN)
    return bytes(out)


def _loc_key(path: str) -> tuple[str, str] | None:
    """`…data-en.ni>LOC/EN/DATA/MAP/X.XSO` → ("EN", "DATA/MAP/X.XSO")."""
    m = _LOC_PATH.search(path)
    return (m.group(1).upper(), m.group(2).upper()) if m else None


def _xso_rows(data: bytes, context: Context | None) -> list[tuple[int, str]]:
    strings = [_decode(s) for s in parse_xso(data)[0]]
    if context is None:
        # Dışa aktarma doğrulaması: tüm metin dizgeleri okunur.
        return [(i, t) for i, t in enumerate(strings) if t is not None and _translatable(t)]
    loc = _loc_key(str(context.get(SOURCE_PATH) or ""))
    reference = context.get((_REFERENCE, loc[1])) if loc and loc[0] != _REFERENCE_LANGUAGE else None
    rows: list[tuple[int, str]] = []
    for i, text in enumerate(strings):
        if text is None or not _translatable(text):
            continue
        if isinstance(reference, tuple) and len(reference) == len(strings):
            if reference[i] != text:
                rows.append((i, text))
        elif _looks_like_text(text):
            rows.append((i, text))
    return rows


def _inject_xso(data: bytes, translations: Mapping[str, str]) -> bytes:
    raw, _table = parse_xso(data)
    original_raw = list(raw)
    for key, new in translations.items():
        index = int(key) if key.isdigit() else -1
        original = _decode(raw[index]) if 0 <= index < len(raw) else None
        if original is None or not _translatable(original):
            raise FormatError(f"Dosyada olmayan satır için çeviri verildi: {key}")
        raw[index] = _encode(key, original, new)
    return data if raw == original_raw else build_xso(data, raw)


def _encode(key: str, original: str, new: str, *, escaped_newlines: bool = True) -> bytes:
    source, codes = tokenize(original, escaped_newlines=escaped_newlines)
    issues = placeholders.problems(source, new)
    if issues:
        raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
    text = detokenize(new, codes, escaped_newlines=escaped_newlines)
    if "\0" in text:
        raise FormatError(f"'{key}' çevirisinde boş karakter (NUL) olamaz.")
    return text.encode("utf-8")


# --- XML -------------------------------------------------------------------------------------


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _xml_rows(data: bytes) -> list[tuple[str, re.Match[str]]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FormatError("XML dosyası UTF-8 değil.") from None
    rows: list[tuple[str, re.Match[str]]] = []
    seen: dict[str, int] = {}
    for m in _XML_STRING.finditer(text):
        ident = m.group(1)
        n = seen.get(ident, 0)
        seen[ident] = n + 1
        rows.append((ident if n == 0 else f"{ident}#{n + 1}", m))
    return rows


def _inject_xml(data: bytes, translations: Mapping[str, str]) -> bytes:
    rows = dict(_xml_rows(data))
    unknown = [k for k in translations if k not in rows or not _translatable(unescape(rows[k].group(2)))]
    if unknown:
        raise FormatError(f"Dosyada olmayan satırlar için çeviri verildi: {', '.join(unknown[:5])}")
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    pieces: list[str] = []
    pos = 0
    for key, m in sorted(((k, rows[k]) for k in translations), key=lambda kv: kv[1].start(2)):
        original = unescape(m.group(2))
        source, _codes = tokenize(original, escaped_newlines=False)
        new = translations[key]
        if new == source:
            continue  # değişmeyen satırın ham baytları (varlık yazımı dahil) korunur
        pieces.append(text[pos : m.start(2)])
        encoded = _encode(key, original, new, escaped_newlines=False).decode("utf-8")
        eol = "\r\n" if "\r\n" in m.group(2) else "\n"  # satır sonu, değişen dizgenin kendi biçiminde yazılır
        pieces.append(_xml_escape(encoded.replace("\n", eol)))
        pos = m.end(2)
    pieces.append(text[pos:])
    out = "".join(pieces).encode("utf-8")
    return (b"\xef\xbb\xbf" + out) if bom else out


class YsOriginPlugin:
    name = "ysorigin"
    label = "Ys Origin betik ve arayüz metinleri"
    candidates_only = True
    path_suffixes: tuple[str, ...] = (".xso", ".xml")
    #: Oyunun Latin BMFont yazı tiplerinde (`extension/font/*.fnt`) ç ö ü var, ğ ş ı İ Ğ Ş yok; dışa aktarma bu harfleri
    #: yazı tiplerine ekler (`derived_files`), bu yüzden hiçbir harf dönüştürülmez.
    unsupported_letters = ""

    derived_files = staticmethod(derived_files)

    def detect(self, path: str, head: bytes) -> bool:
        return head.startswith(XSO_MAGIC) or _XML_HEAD.match(head) is not None

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        loc = _loc_key(path)
        if loc is None or loc[0] != _REFERENCE_LANGUAGE or not data.startswith(XSO_MAGIC):
            return {}
        try:
            strings = parse_xso(data)[0]
        except FormatError:
            return {}
        return {(_REFERENCE, loc[1]): tuple(_decode(s) for s in strings)}

    def language(self, data: bytes) -> str | None:
        return None  # dil, arşiv ve dosya adından anlaşılır (pipeline.path_language)

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        entries: list[TextEntry] = []
        if data.startswith(XSO_MAGIC):
            for index, text in _xso_rows(data, context):
                source, codes = tokenize(text)
                entries.append(TextEntry(str(index), len(entries), source, codes))
            return entries
        for key, m in _xml_rows(data):
            text = unescape(m.group(2))
            if not _translatable(text):
                continue
            source, codes = tokenize(text, escaped_newlines=False)
            entries.append(TextEntry(key, len(entries), source, codes, context=m.group(1)))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        if not translations:
            return data
        if data.startswith(XSO_MAGIC):
            return _inject_xso(data, translations)
        return _inject_xml(data, translations)
