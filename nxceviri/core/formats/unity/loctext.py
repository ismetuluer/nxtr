"""Düz metin olarak saklanan yerelleştirme verileri: SRT altyazıları ve dil sütunlu TSV tabloları.

Bazı Unity oyunları (ör. Despelote) metni `TextAsset` olarak koyar:

- SRT altyazı: `1\\r\\n00:00:00,000 --> 00:00:04,118\\r\\nMetin`. Dil, varlık adındaki
  `[en]` etiketinden anlaşılır (`Nina1[en]`, `[es]shop convo_x`).
- TSV tablo: ilk satır başlık, sonraki satırlar sekmeyle ayrılmış hücreler; dil sütunları
  `es`, `en` veya `[es]`, `[en]` başlıklıdır. Satır sonları metnin içinde `\\n` (ters bölü + n)
  olarak yazılıdır; gerçek satır sonu yalnızca satırları ayırır.

Burada yalnızca ayrıştırma ve yerinde değiştirme vardır: dönen konumlar orijinal metnin
karakter konumlarıdır, böylece değişmeyen her şey olduğu gibi kalır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TIME = r"\d{1,2}:\d\d:\d\d,\d{1,3}"
_TIMING = rf"{_TIME} --> {_TIME}"
_SRT_HEAD = re.compile(rf"\A\ufeff?\s*\d+\r?\n{_TIMING}")
# Bir altyazı bloğu: numara, zaman satırı, metin. Metin sonraki bloğa veya dosya sonuna kadar sürer;
# sondaki boşluklar metne dahil edilmez.
_CUE = re.compile(
    rf"^\ufeff?(\d+)\r?\n({_TIMING}[^\r\n]*)\r?\n(.*?)(?=\r?\n\r?\n\d+\r?\n{_TIMING}|\s*\Z)",
    re.MULTILINE | re.DOTALL,
)
_LANG_TAG = re.compile(r"\[([A-Za-z]{2,3})\]")

#: TSV başlığında dil sütunu sayılan kodlar (küçük harf).
LANGUAGE_CODES = frozenset(
    {
        *("ar", "bg", "br", "ca", "cs", "da", "de", "el", "en", "es", "fi", "fr"),
        *("he", "hu", "it", "ja", "ko", "nl", "no", "pl", "pt", "ro", "ru"),
        *("sv", "th", "tr", "uk", "vi", "zh", "chs", "cht"),
    }
)


@dataclass(frozen=True)
class Cue:
    """Bir altyazı bloğunun metni; `start:end` özgün metindeki konumudur."""

    start: int
    end: int
    text: str


def is_srt(script: str) -> bool:
    return _SRT_HEAD.match(script) is not None


def srt_language(name: str) -> str:
    """Varlık adındaki `[xx]` dil etiketi; yoksa boş dize."""
    m = _LANG_TAG.search(name)
    return m.group(1).lower() if m else ""


def parse_srt(script: str) -> list[Cue]:
    return [Cue(m.start(3), m.end(3), m.group(3)) for m in _CUE.finditer(script)]


def replace_spans(script: str, edits: list[tuple[int, int, str]]) -> str:
    """Konumlarla verilen parçaları değiştirir; `edits` çakışmayan aralıklardır."""
    out: list[str] = []
    pos = 0
    for start, end, new in sorted(edits):
        out.append(script[pos:start])
        out.append(new)
        pos = end
    out.append(script[pos:])
    return "".join(out)


@dataclass(frozen=True)
class Table:
    eol: str
    lines: tuple[str, ...]
    header: tuple[str, ...]
    #: dil kodu → sütun sırası
    languages: dict[str, int]
    #: (satır sırası, hücreler); hücre sayısı başlıkla uyuşmayan satırlar (boş son satır…) yoktur
    rows: tuple[tuple[int, tuple[str, ...]], ...]

    def label(self, cells: tuple[str, ...]) -> str:
        """Satırı tanıtan hücreler (dil sütunları ve zaman aralığı hariç), eğik çizgiyle birleşik."""
        skip = set(self.languages.values())
        parts = [c for i, c in enumerate(cells) if i not in skip and c and "-->" not in c]
        return "/".join(parts)


def _language_of(header: str) -> str:
    code = header.strip().strip("[]")  # büyük harfli başlıklar ("ID") dil kodu değildir
    return code if code in LANGUAGE_CODES else ""


def parse_tsv(script: str) -> Table | None:
    """Dil sütunlu TSV tablosunu ayrıştırır; böyle bir tablo değilse None."""
    eol = "\r\n" if "\r\n" in script else "\n"
    lines = script.split(eol)
    header = tuple(lines[0].lstrip("\ufeff").split("\t"))
    if len(header) < 3:
        return None
    languages: dict[str, int] = {}
    for col, title in enumerate(header):
        code = _language_of(title)
        if code:
            if code in languages:
                return None
            languages[code] = col
    if len(languages) < 2:
        return None
    rows = []
    for i, line in enumerate(lines[1:], 1):
        cells = tuple(line.split("\t"))
        if len(cells) == len(header):
            rows.append((i, cells))
    return Table(eol, tuple(lines), header, languages, tuple(rows))


def replace_cells(table: Table, changes: dict[tuple[int, int], str]) -> str:
    """`(satır sırası, sütun) → yeni hücre` değişikliklerini uygulayıp tabloyu birleştirir."""
    lines = list(table.lines)
    by_line: dict[int, dict[int, str]] = {}
    for (line_no, col), text in changes.items():
        by_line.setdefault(line_no, {})[col] = text
    for line_no, cols in by_line.items():
        cells = lines[line_no].split("\t")
        for col, text in cols.items():
            cells[col] = text
        lines[line_no] = "\t".join(cells)
    return table.eol.join(lines)
