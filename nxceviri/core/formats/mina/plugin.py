"""Mina the Hollower (Yacht Club YCD) metin eklentisi.

`extract` oyunun İngilizce sütununu okur. `inject` çevirileri satırın tüm dil sütunlarına yazar;
dosya boyutu ve hiçbir işaretçi değişmez, yalnızca çevrilen satırın betimleyicileri ve dizgi baytları
güncellenir (ayrıntı: docs/formats/mina-ycd.md). Cihazda doğrulanana kadar deneysel sayılır.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from nxceviri.core.formats.base import Context, ControlCode, FormatError, TextEntry
from nxceviri.core.formats.mina import ycd
from nxceviri.core.translate import markup, placeholders

_TAG_RE = re.compile(r"</?[A-Za-z][^<>\n]{0,200}>")
_TAG_NAME = re.compile(r"<(/?)([A-Za-z]+)")
_FILE_REFERENCE = re.compile(r"[\w\-./]+\.yc")
_ENGLISH = "English"
_SPEAKER = "Speaker"


def _tag_label(tag: str) -> str:
    if tag.startswith("{"):
        return f"Değişken {tag}" if len(tag) <= 40 else "Değişken / biçim ifadesi"
    m = _TAG_NAME.match(tag)
    if m is None:
        return f"Biçim etiketi {tag}"
    name = m.group(2)
    return f"Etiket sonu </{name}>" if m.group(1) else f"Biçim etiketi <{name}>"


def tokenize(text: str) -> tuple[str, tuple[ControlCode, ...]]:
    """Oyunun metin etiketlerini (`<f cn=mina>`, `<w>`…) ⟦n⟧ yer tutucularına çevirir."""
    return markup.tokenize(text, _TAG_RE, _tag_label)


def table_key(kind: str, row_id: str, seen: set[str]) -> str:
    """Tablo türü + satır kimliği; aynı kimlik ikinci kez geçerse `#2` eklenir."""
    key = f"{kind}/{row_id}"
    n = 1
    while key in seen:
        n += 1
        key = f"{kind}/{row_id}#{n}"
    seen.add(key)
    return key


def _plain(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


class MinaPlugin:
    name = "mina"
    label = "Mina the Hollower (YCD)"
    candidates_only = True
    path_suffixes: tuple[str, ...] = (".yc",)

    def detect(self, path: str, head: bytes) -> bool:
        return ycd.is_ycd(head)

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        return {}

    def language(self, data: bytes) -> str | None:
        return None  # tüm diller aynı dosyada; kaynak İngilizce sütunudur

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        entries: list[TextEntry] = []
        seen_kinds: set[str] = set()
        seen_keys: set[str] = set()
        for table in ycd.read_tables(data):
            if table.kind in seen_kinds:
                continue  # aynı türde ikinci tablo (yama dosyalarında Türkçe kopya) yok sayılır
            seen_kinds.add(table.kind)
            english = table.column(_ENGLISH)
            speaker = table.header.index(_SPEAKER) if _SPEAKER in table.header else None
            for row in table.rows:
                key = table_key(table.kind, row.cells[0], seen_keys)  # atlanan satırlar da sayılır
                text = row.cells[english]
                if not text.strip() or _FILE_REFERENCE.fullmatch(text.strip()):
                    continue  # boş veya başka bir dosyaya yol (ör. palet): çevrilecek metin değil
                source, codes = tokenize(text)
                who = _plain(row.cells[speaker]) if speaker is not None else ""
                entries.append(TextEntry(key, len(entries), source, codes, context=who))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        """Çevirileri, ilgili satırların tüm dil sütunlarına yazar; dosya boyutu değişmez."""
        if not translations:
            return data
        tables = ycd.read_tables(data)
        rows: dict[str, tuple[ycd.Table, int]] = {}
        seen_kinds: set[str] = set()
        seen_keys: set[str] = set()
        for table in tables:
            if table.kind in seen_kinds:
                continue
            seen_kinds.add(table.kind)
            for index, row in enumerate(table.rows):
                rows[table_key(table.kind, row.cells[0], seen_keys)] = (table, index)
        unknown = [k for k in translations if k not in rows]
        if unknown:
            raise FormatError(f"Dosyada olmayan satırlar için çeviri verildi: {', '.join(unknown[:5])}")
        edits: dict[int, dict[int, str]] = {}
        for key, new in translations.items():
            table, index = rows[key]
            original = table.rows[index].cells[table.column(_ENGLISH)]
            source, codes = tokenize(original)
            issues = placeholders.problems(source, new)
            if issues:
                raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
            edits.setdefault(table.offset, {})[index] = markup.detokenize(new, codes)
        for table in tables:
            if table.offset not in edits:
                continue
            data, failed = ycd.replace_language_texts(data, table, tables, edits[table.offset])
            if failed:
                names = ", ".join(table.rows[i].cells[0] for i in failed[:5])
                raise FormatError(
                    f"{len(failed)} satırın çevirisi dosyada boş yer bulunamadığı için yazılamadı ({names}…).",
                    "Bu satırların çevirisini kısaltın.",
                )
        return data
