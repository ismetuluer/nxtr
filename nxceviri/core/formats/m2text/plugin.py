"""M2 PSB metin eklentisi: oyunun menü, onay, rehber ve Master Book metinleri.

Metinler `.psb.m` dosyalarının (PSB) dizge tablosundadır. İki yapı tanınır:

- **Dil tabloları** (`system/config/menu_item`, `notice`, `menu_info`, `guide_body`, …): her anahtarın altında
  `eng`, `fra`, `ger`, `ita`, `jpn`, `spa` listeleri. Kaynak `eng` listesidir.
- **Master Book sayfaları** (`087/config/*_EN`): `data[n].text`, `.pageTitle`, `.TextArea…`.

Bir dizge tablosunda aynı yazı bir kez tutulur ve birden çok yerden başvurulur. Bu yüzden satır
**dizge başına** çıkarılır (anahtar: ilk geçtiği yol; bağlam: kullanıldığı anahtarlar) ve çeviri,
dizgenin kendisini yerinde değiştirerek yazılır; ağaç ve dosyanın geri kalanı bayt bayt aynı kalır.
Bir dizge metin dışı bir yerden de (ör. bir kimlik olarak) başvuruluyorsa değiştirilmez, çıkarılmaz.
Ayrıntılar: docs/formats/m2.md
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from nxceviri.core.archives import psb
from nxceviri.core.errors import NxError
from nxceviri.core.formats.base import SOURCE_PATH, Context, ControlCode, FormatError, TextEntry
from nxceviri.core.translate import markup, placeholders

SOURCE_SLOT = "eng"
#: Dil tablolarında görülen dil anahtarları; kaynak dışındakiler metin kaynağı değil, dil yuvasıdır.
LANGUAGE_SLOTS = frozenset({"eng", "fra", "ger", "ita", "jpn", "spa"})
_BOOK_FIELDS = frozenset({"text", "pageTitle"})
_MAX_CONTEXT = 3

#: Oyun metninin içindeki kodlar: `#{color,FF0000FF}`, `<br>`, `<size=24>`, `%s`, `%02d`, `{…}`.
_CODE_RE = re.compile(r"#\{[^{}]*\}|</?[A-Za-z][^<>\n]{0,80}>|%[-+0-9.]*[sdfxX]|\{[^{}]*\}")
_TAG_NAME = re.compile(r"</?([A-Za-z]+)")


def _code_label(code: str) -> str:
    if code.startswith("#{"):
        return f"Renk / biçim kodu {code}"
    if code.startswith("<"):
        if code == "<br>":
            return "Satır sonu <br>"
        m = _TAG_NAME.match(code)
        name = m.group(1) if m else code
        return f"Etiket sonu </{name}>" if code.startswith("</") else f"Biçim etiketi <{name}>"
    if code.startswith("%"):
        return f"Değişken {code}"
    return f"Değişken / biçim ifadesi {code}" if len(code) <= 40 else "Değişken / biçim ifadesi"


def tokenize(text: str) -> tuple[str, tuple[ControlCode, ...]]:
    """Oyun kodlarını ⟦n⟧ yer tutucularına çevirir."""
    out: list[str] = []
    codes: list[ControlCode] = []
    pos = 0
    for m in _CODE_RE.finditer(text):
        out.append(text[pos : m.start()])
        codes.append(ControlCode(m.group().encode("utf-8"), _code_label(m.group())))
        out.append(placeholders.token(len(codes)))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out), tuple(codes)


def _is_source_path(path: tuple[str | int, ...], *, book_ok: bool) -> bool:
    if len(path) >= 2 and path[-2] == SOURCE_SLOT and isinstance(path[-1], int):
        return True
    if not book_ok or len(path) != 3 or path[0] != "data" or not isinstance(path[1], int):
        return False
    field = path[2]
    return isinstance(field, str) and (field in _BOOK_FIELDS or field.startswith("TextArea"))


def _is_language_slot(path: tuple[str | int, ...]) -> bool:
    return len(path) >= 2 and path[-2] in LANGUAGE_SLOTS and isinstance(path[-1], int)


def _translatable(text: str) -> bool:
    return any(ch.isalpha() for ch in _CODE_RE.sub("", text))


def _context(path: tuple[str | int, ...]) -> str:
    if path and path[0] == "data":
        return f"sayfa {path[1]} / {path[2]}" if len(path) == 3 else ""
    return str(path[-3]) if len(path) >= 3 else ""


@dataclass
class _Row:
    key: str
    string_index: int
    source: str
    contexts: list[str]


def _rows(doc: psb.Psb, *, book_ok: bool) -> list[_Row]:
    refs = doc.string_refs()
    unsafe = {i for p, i in refs if not _is_source_path(p, book_ok=book_ok) and not _is_language_slot(p)}
    rows: dict[int, _Row] = {}
    for path, index in refs:
        if index in unsafe or not _is_source_path(path, book_ok=book_ok):
            continue
        text = doc.strings[index]
        if not _translatable(text):
            continue
        context = _context(path)
        row = rows.get(index)
        if row is None:
            rows[index] = _Row("/".join(map(str, path)), index, text, [context] if context else [])
        elif context and context not in row.contexts:
            row.contexts.append(context)
    return list(rows.values())


def _book_allowed(path: str) -> bool:
    """Master Book sayfaları yalnızca İngilizce dosyalardan alınır (`…_EN.psb.m`); `_JP` Japonca kaynaktır."""
    name = path.rsplit(">", 1)[-1].rsplit("/", 1)[-1].lower()
    return name.removesuffix(".psb.m").endswith("_en")


def is_text_member(path: str, data: bytes) -> bool:
    """Arşiv üyesi çevrilebilir metin içeriyor mu? (taramada kullanılır)"""
    if not psb.is_psb(data):
        return False
    try:
        return bool(_rows(psb.Psb(data), book_ok=_book_allowed(path)))
    except NxError:
        return False  # bozuk üye taramayı durdurmaz; çıkarma aşamasında asıl hata gösterilir


class M2TextPlugin:
    name = "m2text"
    label = "M2 PSB metni (Metal Gear Solid)"
    candidates_only = True
    path_suffixes: tuple[str, ...] = (".psb.m",)

    def detect(self, path: str, head: bytes) -> bool:
        return psb.is_psb(head)

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        return {}

    def language(self, data: bytes) -> str | None:
        return None  # dil tabloları tüm dilleri taşır; kaynak her zaman İngilizce yuvadır

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        source_path = str(context.get(SOURCE_PATH) or "") if context is not None else ""
        book_ok = _book_allowed(source_path) if source_path else True
        entries: list[TextEntry] = []
        for row in _rows(psb.Psb(data), book_ok=book_ok):
            source, codes = tokenize(row.source)
            shown = ", ".join(row.contexts[:_MAX_CONTEXT])
            if len(row.contexts) > _MAX_CONTEXT:
                shown += f" (+{len(row.contexts) - _MAX_CONTEXT})"
            entries.append(TextEntry(row.key, len(entries), source, codes, context=shown))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        if not translations:
            return data
        doc = psb.Psb(data)
        rows = {row.key: row for row in _rows(doc, book_ok=True)}
        unknown = [k for k in translations if k not in rows]
        if unknown:
            raise FormatError(f"Dosyada olmayan satırlar için çeviri verildi: {', '.join(unknown[:5])}")
        replacements: dict[int, str] = {}
        for key, new in translations.items():
            row = rows[key]
            source, codes = tokenize(row.source)
            issues = placeholders.problems(source, new)
            if issues:
                raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
            replacements[row.string_index] = markup.detokenize(new, codes)
        return psb.replace_strings(data, replacements)
