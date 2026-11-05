"""I2 Localization kaynakları (LanguageSource) — ham bayttan okuma ve geri yazma.

I2 Localization, Unity için yaygın bir ticari yerelleştirme eklentisidir. Tüm dillerin
metinleri tek bir MonoBehaviour'da (`LanguageSource` / `LanguageSourceAsset`) durur:

    ... başlık alanları (Google ayarları vb.) ...
    mTerms: TermData[]      ← metinler
    ... (sürüme göre birkaç alan) ...
    mLanguages: LanguageData[] = {Name, Code, Flags}
    ...

Oyunların çoğunda bu nesne `resources.assets` içindedir ve tip ağacı (typetree) derlemede
silinmiştir; UnityPy alanları adlarıyla okuyamaz. Bu yüzden nesnenin ham baytları Unity'nin
serileştirme kurallarıyla (int32 uzunluklu UTF-8 dizgiler, 4 bayta hizalama) burada çözülür.
Yapı tahmin edilmez, doğrulanır: terim listesi baştan sona çözülmeli, her terimdeki dil
sayısı `mLanguages` listesindeki dil sayısına eşit olmalı ve dil kodları geçerli görünmelidir.

Geri yazmada yalnızca metni değişen terimler yeniden serileştirilir; diğer tüm baytlar
(başlık, değişmeyen terimler, terim listesinden sonrası) aynen korunur.
Ayrıntılar: docs/formats/unity.md
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, replace

#: MonoBehaviour'un ortak alanları: m_GameObject (PPtr 12), m_Enabled (4), m_Script (PPtr 12).
_BASE_FIELDS = 28
#: Terim listesinin, m_Name'den sonra aranacağı en uzak mesafe (başlık alanları).
_SEARCH_WINDOW = 0x400
#: Terim listesinden sonra mLanguages listesinin aranacağı en uzak mesafe.
_LANGUAGES_WINDOW = 0x100
_MAX_LANGUAGES = 100
_MAX_TERMS = 1_000_000
#: I2 dil kodları: "en", "pt-BR", "zh-CN"… (ilk kısım küçük harf).
_CODE_RE = re.compile(r"[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,4})?")
_NAME_RE = re.compile(r"[^\x00-\x1f]+")  # boş olmayan, kontrol karakteri içermeyen ad

#: eTermType.Text — yalnızca metin terimleri çevrilir (diğerleri font, görsel, ses başvurusu).
TERM_TEXT = 0

# Bilinen TermData alan dizilimleri:
# A: I2 2.6.x (Blasphemous ile doğrulandı) — Term, TermType, Description, Languages,
#    Languages_Touch, Flags.
# B: I2 2.8.x — Term, TermType, Languages, Flags, Languages_Touch (gerçek oyunda denenmedi).
LAYOUT_A = "A"
LAYOUT_B = "B"
_LAYOUTS = (LAYOUT_A, LAYOUT_B)


class _Bad(Exception):
    """Ham veri bu yapıya uymuyor (aramada sessizce bir sonraki aday denenir)."""


def _align(n: int) -> int:
    return (n + 3) & ~3


class _Reader:
    def __init__(self, data: bytes, pos: int) -> None:
        self.data = data
        self.pos = pos

    def i32(self) -> int:
        if self.pos + 4 > len(self.data):
            raise _Bad
        (v,) = struct.unpack_from("<i", self.data, self.pos)
        self.pos += 4
        return int(v)

    def raw(self) -> bytes:
        n = self.i32()
        if n < 0 or self.pos + n > len(self.data):
            raise _Bad
        v = self.data[self.pos : self.pos + n]
        self.pos = _align(self.pos + n)
        return v

    def string(self) -> str:
        try:
            return self.raw().decode("utf-8")
        except UnicodeDecodeError:
            raise _Bad from None

    def strings(self) -> list[str]:
        n = self.i32()
        if not 0 <= n <= _MAX_LANGUAGES:
            raise _Bad
        return [self.string() for _ in range(n)]


def _w_raw(v: bytes) -> bytes:
    return struct.pack("<i", len(v)) + v + b"\0" * (_align(len(v)) - len(v))


def _w_string(v: str) -> bytes:
    return _w_raw(v.encode("utf-8"))


def _w_strings(v: list[str]) -> bytes:
    return struct.pack("<i", len(v)) + b"".join(_w_string(s) for s in v)


@dataclass(frozen=True)
class Term:
    name: str
    term_type: int
    description: str
    languages: tuple[str, ...]
    touch: tuple[str, ...]
    flags: bytes
    raw: bytes  # dosyadaki özgün baytlar (değişmeyen terim aynen yazılır)


@dataclass(frozen=True)
class Language:
    name: str
    code: str


@dataclass(frozen=True)
class Source:
    layout: str
    prefix: bytes  # terim listesinden önceki her şey
    terms: tuple[Term, ...]
    suffix: bytes  # terim listesinden sonraki her şey (mLanguages dahil)
    languages: tuple[Language, ...]


def _read_term(r: _Reader, layout: str) -> Term:
    start = r.pos
    name = r.string()
    term_type = r.i32()
    if layout == LAYOUT_A:
        description = r.string()
        languages = r.strings()
        touch = r.strings()
        flags = r.raw()
    else:
        description = ""
        languages = r.strings()
        flags = r.raw()
        touch = r.strings()
    if not _NAME_RE.fullmatch(name):
        raise _Bad
    return Term(name, term_type, description, tuple(languages), tuple(touch), flags, r.data[start : r.pos])


def _write_term(t: Term, layout: str) -> bytes:
    head = _w_string(t.name) + struct.pack("<i", t.term_type)
    if layout == LAYOUT_A:
        return (
            head
            + _w_string(t.description)
            + _w_strings(list(t.languages))
            + _w_strings(list(t.touch))
            + _w_raw(t.flags)
        )
    return head + _w_strings(list(t.languages)) + _w_raw(t.flags) + _w_strings(list(t.touch))


def _read_languages(data: bytes, pos: int, count: int) -> tuple[Language, ...]:
    r = _Reader(data, pos)
    if r.i32() != count:
        raise _Bad
    out = []
    for _ in range(count):
        name, code = r.string(), r.string()
        if r.pos + 1 > len(data) or not _CODE_RE.fullmatch(code) or not _NAME_RE.fullmatch(name):
            raise _Bad
        r.pos = _align(r.pos + 1)  # Flags (bayt)
        out.append(Language(name, code))
    return tuple(out)


def _try_parse(data: bytes, pos: int, layout: str) -> Source:
    r = _Reader(data, pos)
    count = r.i32()
    if not 0 < count <= _MAX_TERMS:
        raise _Bad
    first = _read_term(r, layout)
    width = len(first.languages)
    if not 0 < width <= _MAX_LANGUAGES:
        raise _Bad
    terms = [first]
    for _ in range(count - 1):
        t = _read_term(r, layout)
        if len(t.languages) != width:  # Languages_Touch ve Flags eski kalmış olabilir; uzunlukları serbest
            raise _Bad
        terms.append(t)
    end = r.pos
    for gap in range(0, min(_LANGUAGES_WINDOW, len(data) - end - 4) + 1, 4):
        try:
            languages = _read_languages(data, end + gap, width)
        except _Bad:
            continue
        return Source(layout, data[:pos], tuple(terms), data[end:], languages)
    raise _Bad


def _name_end(data: bytes) -> int:
    r = _Reader(data, _BASE_FIELDS)
    r.raw()  # m_Name
    return r.pos


def parse_source(data: bytes) -> Source | None:
    """MonoBehaviour'un ham verisi bir I2 kaynağıysa çözer; değilse None."""
    try:
        start = _name_end(data)
    except _Bad:
        return None
    stop = min(start + _SEARCH_WINDOW, len(data) - 4)
    for pos in range(start, stop + 1, 4):
        # Hızlı eleme: makul bir terim sayısı ve ardından makul uzunlukta bir terim adı.
        count, name_len = struct.unpack_from("<ii", data, pos) if pos + 8 <= len(data) else (0, 0)
        if not (0 < count <= _MAX_TERMS and 0 < name_len <= 1024):
            continue
        for layout in _LAYOUTS:
            try:
                return _try_parse(data, pos, layout)
            except _Bad:
                continue
    return None


def serialize(source: Source) -> bytes:
    """Kaynağı ham bayta geri yazar; değişmeyen terimler özgün baytlarıyla yazılır."""
    out = bytearray(source.prefix)
    out += struct.pack("<i", len(source.terms))
    for t in source.terms:
        out += t.raw if t.raw else _write_term(t, source.layout)
    out += source.suffix
    return bytes(out)


def with_text(term: Term, column: int, text: str) -> Term:
    """Bir dil sütununun metnini değiştirilmiş terim (yeniden serileştirilmek üzere)."""
    langs = list(term.languages)
    langs[column] = text
    return replace(term, languages=tuple(langs), raw=b"")
