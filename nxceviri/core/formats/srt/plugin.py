"""SubRip (`.srt`) altyazı eklentisi.

Ys Origin'in giriş videosu (`yso_pro.mp4`) yazısız bir görüntüdür; altyazıyı oyun `extension/movies/yso_pro_<dil>.srt`
dosyasından kendi fontuyla çizer (dil kodları: de, en, fr, it, sp, ko, zh-hans, zh-hant). Dosya arşivde değil, RomFS'te
serbest durur; moda doğrudan konabilir.

Yapı: boş satırla ayrılmış bloklar; her blok `sıra numarası`,
`başlangıç --> bitiş` ve bir veya daha fazla metin satırıdır.
Zaman damgalarına ve sıra numaralarına dokunulmaz; yalnızca metin satırları değişir. Tabloda her blok bir satırdır
(anahtar = sıra numarası, bağlam = zaman aralığı); blok içindeki satır sonları metnin parçasıdır.

Kodlar (`⟦n⟧` olur): `<i>`, `<b>`, `<u>`, `<font …>` etiketleri ve `{\an8}` gibi konum kodları.
Dosyadaki satır sonu biçimi (LF/CRLF), BOM ve değişmeyen bloklar bayt bayt korunur.
Ayrıntılar: docs/formats/ys-origin.md
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from nxceviri.core.formats.base import Context, ControlCode, FormatError, TextEntry
from nxceviri.core.formats.ysorigin.extras import derived_files
from nxceviri.core.translate import markup, placeholders

_BOM = b"\xef\xbb\xbf"
#: Dosya başı: isteğe bağlı BOM, sıra numarası, zaman satırı. `detection` aynı kalıpla tanır.
HEAD = re.compile(rb"\A(?:\xef\xbb\xbf)?\s*\d+[ \t]*\r?\n\d\d:\d\d:\d\d[,.]\d{3} --> \d\d:\d\d:\d\d[,.]\d{3}")
_TIME = r"\d\d:\d\d:\d\d[,.]\d{3} --> \d\d:\d\d:\d\d[,.]\d{3}[^\r\n]*"
_CUE = re.compile(rf"^(\d+)[ \t]*\r?\n({_TIME})\r?\n(.*?)(?=\r?\n[ \t]*\r?\n|\s*\Z)", re.DOTALL | re.MULTILINE)
_CODE_RE = re.compile(r"</?[biu]>|</?font[^<>]*>|\{\an?\d+\}", re.IGNORECASE)


def tokenize(text: str) -> tuple[str, tuple[ControlCode, ...]]:
    """Altyazı etiketlerini ⟦n⟧ yer tutucularına, satır sonlarını `\n`e çevirir."""
    out: list[str] = []
    codes: list[ControlCode] = []
    pos = 0
    for m in _CODE_RE.finditer(text):
        out.append(text[pos : m.start()])
        codes.append(ControlCode(m.group().encode("utf-8"), f"Altyazı kodu {m.group()}"))
        out.append(placeholders.token(len(codes)))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out).replace("\r\n", "\n"), tuple(codes)


def _translatable(text: str) -> bool:
    return any(ch.isalpha() for ch in _CODE_RE.sub("", text))


def _cues(text: str) -> list[tuple[str, re.Match[str]]]:
    rows: list[tuple[str, re.Match[str]]] = []
    seen: dict[str, int] = {}
    for m in _CUE.finditer(text):
        n = seen.get(m.group(1), 0)
        seen[m.group(1)] = n + 1
        rows.append((m.group(1) if n == 0 else f"{m.group(1)}#{n + 1}", m))
    return rows


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FormatError("Altyazı dosyası UTF-8 değil.") from None


class SrtPlugin:
    name = "srt"
    label = "SubRip altyazısı (.srt)"
    candidates_only = True
    path_suffixes: tuple[str, ...] = (".srt",)
    #: Ys Origin'de yazı tiplerine eksik harfler dışa aktarmada eklenir (`derived_files`); harf dönüştürülmez.
    unsupported_letters = ""

    derived_files = staticmethod(derived_files)

    def detect(self, path: str, head: bytes) -> bool:
        return path.lower().endswith(".srt") and HEAD.match(head) is not None

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        return {}

    def language(self, data: bytes) -> str | None:
        return None  # dil dosya adından anlaşılır (pipeline.path_language: `yso_pro_en.srt` → en)

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        entries: list[TextEntry] = []
        for key, m in _cues(_decode(data)):
            if not _translatable(m.group(3)):
                continue
            source, codes = tokenize(m.group(3))
            entries.append(TextEntry(key, len(entries), source, codes, context=m.group(2).split("\n")[0].strip()))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        if not translations:
            return data
        text = _decode(data)
        rows = dict(_cues(text))
        unknown = [k for k in translations if k not in rows or not _translatable(rows[k].group(3))]
        if unknown:
            raise FormatError(f"Dosyada olmayan satırlar için çeviri verildi: {', '.join(unknown[:5])}")
        pieces: list[str] = []
        pos = 0
        for key, m in sorted(((k, rows[k]) for k in translations), key=lambda kv: kv[1].start(3)):
            source, codes = tokenize(m.group(3))
            new = translations[key]
            if new == source:
                continue  # değişmeyen bloğun ham baytları korunur
            issues = placeholders.problems(source, new)
            if issues:
                raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
            body = markup.detokenize(new.replace("\r\n", "\n"), codes)
            if "\0" in body:
                raise FormatError(f"'{key}' çevirisinde boş karakter (NUL) olamaz.")
            if "\n\n" in body.replace("\r\n", "\n"):
                raise FormatError(f"'{key}' çevirisinde boş satır olamaz: altyazı bloğunu bitirir.")
            eol = "\r\n" if "\r\n" in m.group(3) or "\r\n" in text[m.start() : m.end(2) + 2] else "\n"
            pieces.append(text[pos : m.start(3)])
            pieces.append(body.replace("\n", eol))
            pos = m.end(3)
        pieces.append(text[pos:])
        out = "".join(pieces).encode("utf-8")
        return (_BOM + out) if data.startswith(_BOM) else out
