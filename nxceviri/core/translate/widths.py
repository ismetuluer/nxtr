"""Piksel genişliği ölçümü: fontun harf genişlikleriyle metnin ekranda kaplayacağı yeri tahmin eder.

Karakter sayısı ("M" ile "i" aynı sayılır) menü ve düğme gibi kısa metinlerde yetersizdir. Bu modül:

- bir **genişlik tablosu** (`WidthTable`) tutar: karakter → ilerleme genişliği. Eksik Türkçe harf temel harfinin
  genişliğini (ş→s, ı→i …), bilinmeyen karakter tablonun ortalamasını kullanır;
- tabloyu fontlardan çıkarır: TTF/OTF (`table_from_ttf`), TextMeshPro (`table_from_tmp`, `table_from_tmp_legacy`) ve
  ikili BMFont (`table_from_bmfont`); font yoksa yerleşik **yaklaşık tablo** (`approximate_table`) kullanılır;
- tabloyu proje ayarında saklanacak JSON metnine çevirir ve geri okur (`dump` / `load`; bozuk veri çökertmez);
- kontrol kodlarını `fit.visible_width` ile aynı kuralla sayarak görünen genişliği ölçer (`visible_pixels`);
- **bağıl denetim** yapar (`width_problem`): kutunun gerçek boyutu bilinmediği için ölçüt, oyunun kutuya sığdırdığı
  orijinal metnin aynı fontla ölçülen genişliğidir. Yalnızca tek satırlı orijinal için anlamlıdır (çok satırlı
  diyalogda satırlar yeniden bölündüğü için karakter sınırı kuralları sürer). `group_boxes` aynı gruptaki
  (menü öğeleri gibi) metinlerin paylaştığı kutuyu orijinalin en geniş satırından kestirir.

Modül saftır; arayüz veya veritabanı bilmez. Genişlikler yalnızca kendi tablosunun biriminde anlamlıdır (TTF: em
kesri, TMP/BMFont: font pikseli); iki tablo birbirine karıştırılmaz.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from nxceviri.core.fontpatch import ttf as ttf_reader
from nxceviri.core.fontpatch.bmfont import BmFont
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.codekinds import KIND_PAGE_BREAK, KIND_SYMBOL, KIND_VARIABLE, KindOf
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH, split_lines

log = logging.getLogger(__name__)

#: Varsayılan tolerans: Türkçe satır, orijinalin (ya da kutunun) bu kadar fazlasına kadar uyarısız geçer.
DEFAULT_TOLERANCE = 0.15

#: Eksik Türkçe harf → temel harf (genişlik ondan alınır).
_BASE_LETTER = {
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
    "Ç": "C",
    "Ğ": "G",
    "İ": "I",
    "Ö": "O",
    "Ş": "S",
    "Ü": "U",
}

#: TTF tablosuna alınan en büyük kod noktası: Latin, Yunan, Kiril ve noktalama yeter; Çince/Japonca/Korece harfler
#: tabloyu şişirir ve Türkçe çeviride görünmez (eksik karakter ortalamaya düşer).
_TTF_MAX_CODEPOINT = 0x3000

#: Yaklaşık tablo: yazdırılabilir ASCII için genel orantılı (proportional) sans-serif genişlikleri, em kesri olarak.
#: Elle yazılmış sabitlerdir; belirli bir fontun ölçüsü ya da kopyası değildir, yalnızca "M geniş, i dar" oranını verir.
_APPROX_ASCII = " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
_APPROX_WIDTHS = (
    # boşluk ! " # $ % & ' ( ) * + , - . /
    (0.28, 0.28, 0.36, 0.56, 0.56, 0.89, 0.67, 0.19, 0.33, 0.33, 0.39, 0.58, 0.28, 0.33, 0.28, 0.28)
    # 0-9 : ; < = > ? @
    + (0.56,) * 10
    + (0.28, 0.28, 0.58, 0.58, 0.58, 0.56, 1.0)
    # A-Z
    + (0.67, 0.67, 0.72, 0.72, 0.67, 0.61, 0.78, 0.72, 0.28, 0.50, 0.67, 0.56, 0.83)
    + (0.72, 0.78, 0.67, 0.78, 0.72, 0.67, 0.61, 0.72, 0.67, 0.94, 0.67, 0.67, 0.61)
    # [ \ ] ^ _ `
    + (0.28, 0.28, 0.28, 0.47, 0.56, 0.33)
    # a-z
    + (0.56, 0.56, 0.50, 0.56, 0.56, 0.28, 0.56, 0.56, 0.22, 0.22, 0.50, 0.22, 0.83)
    + (0.56, 0.56, 0.56, 0.56, 0.33, 0.50, 0.28, 0.56, 0.50, 0.72, 0.50, 0.50, 0.50)
    # { | } ~
    + (0.33, 0.26, 0.33, 0.58)
)


@dataclass(frozen=True)
class WidthTable:
    """Karakter → ilerleme genişliği. `approximate`: font tablosu değil, yerleşik yaklaşık tablo."""

    advances: Mapping[str, float]
    name: str
    approximate: bool

    average: float = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Ortalama harf genişliği: ASCII harflerin ortalaması, yoksa tüm girdilerin ortalaması, tablo boşsa 0."""
        letters = [w for c, w in self.advances.items() if c.isascii() and c.isalpha()]
        pool = letters or list(self.advances.values())
        object.__setattr__(self, "average", sum(pool) / len(pool) if pool else 0.0)

    def advance(self, ch: str) -> float:
        """Tek karakterin genişliği; eksikse Türkçe harf için temel harf, sonra ortalama (boşlukta yarısı)."""
        found = self.advances.get(ch)
        if found is not None:
            return found
        base = _BASE_LETTER.get(ch)
        if base is not None and base in self.advances:
            return self.advances[base]
        if ch.isspace():
            space = self.advances.get(" ")
            return space if space is not None else self.average / 2
        return self.average

    def measure(self, text: str) -> float:
        """Düz metnin genişliği (kod ve kenar boşluğu işlemi yok; satır sonu karakterleri sayılmaz)."""
        return sum(self.advance(ch) for ch in text if ch not in "\r\n")


def approximate_table() -> WidthTable:
    """Yerleşik yaklaşık tablo: yazdırılabilir ASCII ve Türkçe harfler (aksan genişliği değiştirmez)."""
    advances = dict(zip(_APPROX_ASCII, _APPROX_WIDTHS, strict=True))
    for turkish, base in _BASE_LETTER.items():
        advances[turkish] = advances[base]
    advances["ı"] = advances["i"]
    advances["İ"] = advances["I"]
    return WidthTable(advances, name="Yaklaşık", approximate=True)


# --- fontlardan tablo -------------------------------------------------------------------------------------------


def table_from_ttf(data: bytes, name: str) -> WidthTable | None:
    """TTF/OTF'tan tablo (`hmtx` ilerlemeleri, em'e bölünmüş). Okunamayan ya da boş fontta `None`."""
    font = ttf_reader._open(data)
    if font is None:
        return None
    cmap = ttf_reader._unicode_cmap(font)
    if cmap is None or "hmtx" not in font or "head" not in font:
        return None
    upm = int(font["head"].unitsPerEm)
    if upm <= 0:
        return None
    hmtx = font["hmtx"].metrics
    advances = {
        chr(code): hmtx[glyph][0] / upm for code, glyph in cmap.items() if code < _TTF_MAX_CODEPOINT and glyph in hmtx
    }
    return WidthTable(advances, name=name, approximate=False) if advances else None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def table_from_tmp(
    glyph_table: Sequence[Mapping[str, Any]], character_table: Sequence[Mapping[str, Any]], name: str
) -> WidthTable | None:
    """TextMeshPro (`TMP_FontAsset`) tablosu: `m_GlyphTable` + `m_CharacterTable` (UnityPy tip ağacı biçimi).

    Genişlik font pikselidir (`m_Metrics.m_HorizontalAdvance`). Glifi olmayan karakter atlanır; girdi yoksa `None`.
    """
    advance_of: dict[int, float] = {}
    for glyph in glyph_table:
        metrics = glyph.get("m_Metrics")
        advance = _number(metrics.get("m_HorizontalAdvance")) if isinstance(metrics, Mapping) else None
        index = glyph.get("m_Index")
        if advance is not None and isinstance(index, int):
            advance_of[index] = advance
    advances: dict[str, float] = {}
    for character in character_table:
        code, index = character.get("m_Unicode"), character.get("m_GlyphIndex")
        if isinstance(code, int) and isinstance(index, int) and index in advance_of and 0 <= code <= 0x10FFFF:
            advances[chr(code)] = advance_of[index]
    return WidthTable(advances, name=name, approximate=False) if advances else None


def table_from_tmp_legacy(glyph_info_list: Sequence[Mapping[str, Any]], name: str) -> WidthTable | None:
    """Eski TextMeshPro (`m_glyphInfoList`: `id` = karakter kodu, `xAdvance`)."""
    advances: dict[str, float] = {}
    for info in glyph_info_list:
        code, advance = info.get("id"), _number(info.get("xAdvance"))
        if isinstance(code, int) and advance is not None and 0 <= code <= 0x10FFFF:
            advances[chr(code)] = advance
    return WidthTable(advances, name=name, approximate=False) if advances else None


def table_from_bmfont(font: BmFont, name: str) -> WidthTable | None:
    """İkili BMFont: her karakterin `xadvance` değeri (font pikseli)."""
    advances = {chr(c.id): float(c.xadvance) for c in font.chars.values() if 0 <= c.id <= 0x10FFFF}
    return WidthTable(advances, name=name, approximate=False) if advances else None


# --- JSON -------------------------------------------------------------------------------------------------------

_JSON_VERSION = 1


def dump(table: WidthTable) -> str:
    """Tabloyu proje ayarında saklanacak JSON metnine çevirir."""
    return json.dumps(
        {"v": _JSON_VERSION, "name": table.name, "approximate": table.approximate, "advances": dict(table.advances)},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def load(text: str) -> WidthTable | None:
    """`dump` çıktısını okur. Bozuk ya da uyumsuz veri çökertmez: uyarı günlüğe yazılır, `None` döner."""
    try:
        raw = json.loads(text)
    except ValueError as exc:
        log.warning("Genişlik tablosu okunamadı (bozuk JSON): %s", exc)
        return None
    if not isinstance(raw, dict) or raw.get("v") != _JSON_VERSION:
        log.warning("Genişlik tablosu okunamadı: biçim ya da sürüm tanınmıyor.")
        return None
    name, approximate, raw_advances = raw.get("name"), raw.get("approximate"), raw.get("advances")
    if not isinstance(name, str) or not isinstance(approximate, bool) or not isinstance(raw_advances, dict):
        log.warning("Genişlik tablosu okunamadı: alanlar eksik ya da yanlış türde.")
        return None
    advances: dict[str, float] = {}
    for key, value in raw_advances.items():
        number = _number(value)
        if len(key) != 1 or number is None:
            log.warning("Genişlik tablosu okunamadı: geçersiz girdi %r.", key)
            return None
        advances[key] = number
    return WidthTable(advances, name=name, approximate=approximate)


# --- ölçüm ------------------------------------------------------------------------------------------------------


def visible_pixels(
    line: str, kind_of: KindOf, table: WidthTable, *, variable_width: int = DEFAULT_VARIABLE_WIDTH
) -> float:
    """Satırın ekranda kaplayacağı genişlik; kodlar `fit.visible_width` ile aynı kuralla sayılır.

    Kenar boşlukları atılır, sonra kodlar çıkarılır; `değişken` kodu `variable_width` ortalama harf, `sembol` kodu bir
    ortalama harf genişliğinde sayılır.
    """
    line = line.strip()
    extra = 0.0
    parts: list[str] = []
    pos = 0
    for m in placeholders.TOKEN_RE.finditer(line):
        parts.append(line[pos : m.start()])
        pos = m.end()
        kind = kind_of(int(m.group(1)))
        if kind == KIND_VARIABLE:
            extra += variable_width * table.average
        elif kind == KIND_SYMBOL:
            extra += table.average
    parts.append(line[pos:])
    return table.measure("".join(parts)) + extra


class WidthProblem(NamedTuple):
    """Çeviri satırı kutudan geniş. `measured`: çevirinin en geniş satırı; `limit`: tolerans dahil üst sınır;
    `ratio`: `measured` / kutu (kutu verilmediyse orijinalin genişliği); 1.12 = %112."""

    measured: float
    limit: float
    ratio: float


def _is_single_line(source: str, kind_of: KindOf) -> bool:
    """Orijinal tek satır mı: satır sonu (`\\n` ya da satır sonu kodu) ve sayfa sonu kodu yok."""
    if len(split_lines(source, kind_of)) != 1:
        return False
    return all(kind_of(int(m.group(1))) != KIND_PAGE_BREAK for m in placeholders.TOKEN_RE.finditer(source))


def width_problem(
    source: str,
    translation: str,
    kind_of: KindOf,
    table: WidthTable,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    box: float | None = None,
    variable_width: int = DEFAULT_VARIABLE_WIDTH,
) -> WidthProblem | None:
    """Çevirinin en geniş satırı kutuyu (`box`, yoksa orijinalin genişliği) `tolerance` kadar aşıyorsa sorun döndürür.

    Çok satırlı (satır sonu ya da sayfa sonu içeren) orijinalde, boş çeviride, kutu sıfır ya da bilinmiyorsa `None`.
    """
    if not translation.strip() or not _is_single_line(source, kind_of):
        return None
    base = box if box is not None else visible_pixels(source, kind_of, table, variable_width=variable_width)
    if base <= 0:
        return None
    measured = max(
        visible_pixels(line, kind_of, table, variable_width=variable_width)
        for line in split_lines(translation, kind_of)
    )
    limit = base * (1 + tolerance)
    if measured <= limit * (1 + 1e-9):  # kayan nokta payı: tam sınırdaki satır sorun değildir
        return None
    return WidthProblem(measured, limit, measured / base)


def group_boxes(
    rows: Iterable[tuple[str, str]],
    kind_of: KindOf,
    table: WidthTable,
    group_of: Callable[[str], str | None],
    *,
    variable_width: int = DEFAULT_VARIABLE_WIDTH,
) -> dict[str, float]:
    """Grup → o gruptaki en geniş tek satırlı orijinalin genişliği (menü öğeleri aynı kutuyu paylaşır).

    `rows`: `(anahtar, orijinal)` çiftleri; `group_of(anahtar)` `None` verirse satır atlanır. Yalnızca çok satırlı
    orijinali olan gruplar sonuçta yer almaz.
    """
    boxes: dict[str, float] = {}
    for key, source in rows:
        group = group_of(key)
        if group is None or not _is_single_line(source, kind_of):
            continue
        width = visible_pixels(source, kind_of, table, variable_width=variable_width)
        boxes[group] = max(boxes.get(group, 0.0), width)
    return boxes
