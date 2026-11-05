"""Terim sözlüğünün iki sütunlu XLSX (Excel) olarak dışa ve içe aktarılması.

Dosya düzeni çeviri/redaksiyon tablolarıyla aynı yazıcıyı kullanır: başlık satırı `terim`, `çeviri`. İçe aktarırken
başlık yoksa ilk satır da veridir; isteğe bağlı üçüncü sütun not olarak okunur. Çevirisi boş satırlar atlanır
(lore maddeleri yalnızca uygulamanın içinde yazılır: iki sütunda notları taşınamaz).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from nxceviri.core.translate.csvio import CsvError, table_xlsx, xlsx_table
from nxceviri.core.translate.providers.base import GlossaryTerm

GLOSSARY_COLUMNS = ("terim", "çeviri")

#: Başlık satırının ilk hücresi olarak tanınan adlar (küçük harfle).
_HEADER_NAMES = frozenset(("terim", "term", "kaynak", "orijinal", "source", "original"))


def glossary_xlsx(terms: Sequence[GlossaryTerm]) -> bytes:
    """Çevirisi olan terimler, iki sütun (`terim`, `çeviri`)."""
    return table_xlsx(GLOSSARY_COLUMNS, [(t.term, t.translation) for t in terms if t.translation], sheet="Sözlük")


def export_glossary_xlsx(terms: Sequence[GlossaryTerm], path: Path) -> None:
    try:
        path.write_bytes(glossary_xlsx(terms))
    except OSError as exc:
        raise CsvError(
            f"XLSX dosyası yazılamadı: {exc.strerror or exc}", "Başka bir klasör seçin veya dosya açıksa kapatın."
        ) from exc


def parse_glossary_xlsx(data: bytes) -> list[GlossaryTerm]:
    rows = xlsx_table(data)
    if rows and rows[0][0].strip().casefold() in _HEADER_NAMES:
        rows = rows[1:]
    found: dict[str, GlossaryTerm] = {}
    for line in rows:
        cells = [c.strip() for c in line] + ["", ""]
        term, translation, note = cells[0], cells[1], cells[2] if len(line) > 2 else ""
        if term and translation:
            found.pop(term.casefold(), None)  # aynı terim yeniden geçerse sonuncusu geçerli, sırası da onun
            found[term.casefold()] = GlossaryTerm(term, translation, note)
    if not found:
        raise CsvError(
            "XLSX dosyasında “terim” ve “çeviri” sütunlu bir satır bulunamadı.",
            "İlk sütuna terimi (kaynak dil), ikinci sütuna Türkçe karşılığını yazın.",
        )
    return list(found.values())


def read_glossary_xlsx(path: Path) -> list[GlossaryTerm]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CsvError(f"Dosya okunamadı: {path.name} ({exc.strerror or exc})") from exc
    try:
        return parse_glossary_xlsx(raw)
    except CsvError as exc:
        raise CsvError(f"{path.name}: {exc.message}", exc.hint) from exc


def merge_terms(
    existing: Sequence[GlossaryTerm], imported: Sequence[GlossaryTerm]
) -> tuple[list[GlossaryTerm], int, int]:
    """İçe aktarılan terimleri sözlüğe katar: (yeni sözlük, eklenen, güncellenen).

    Terimler büyük/küçük harf duyarsız eşleşir; var olan terimin yazımı ve (içe aktarılanda yoksa) notu korunur.
    Çevirisi boş içe aktarılan satır bir şey değiştirmez.
    """
    merged = {t.term.casefold(): t for t in existing}
    added = updated = 0
    for t in imported:
        if not t.translation:
            continue
        key = t.term.casefold()
        old = merged.get(key)
        if old is None:
            merged[key] = t
            added += 1
        elif (old.translation, old.note) != (t.translation, t.note or old.note):
            merged[key] = GlossaryTerm(old.term, t.translation, t.note or old.note)
            updated += 1
    return list(merged.values()), added, updated
