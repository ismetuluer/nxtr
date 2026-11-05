"""Sözlüğün iki sütunlu XLSX olarak dışa/içe aktarılması ve birleştirilmesi."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.translate.csvio import CsvError, table_xlsx
from nxceviri.core.translate.glossary_io import (
    GLOSSARY_COLUMNS,
    export_glossary_xlsx,
    merge_terms,
    read_glossary_xlsx,
)
from nxceviri.core.translate.providers.base import GlossaryTerm


def test_round_trip_keeps_terms_and_lore(tmp_path: Path) -> None:
    terms = [
        GlossaryTerm("Silver Pines", "Silver Pines"),
        GlossaryTerm("Sheriff", "Şerif", "unvan"),
        GlossaryTerm("Elara", "", "Kahramanın ablası; resmî konuşur."),  # lore: çevirisi yok, yalnızca not
    ]
    path = tmp_path / "sozluk.xlsx"
    export_glossary_xlsx(terms, path)
    assert GLOSSARY_COLUMNS == ("terim", "çeviri")
    back = read_glossary_xlsx(path)
    # İki sütun: notlar dışa aktarılmaz; lore maddesinin notu çeviri yerine yazılmaz.
    assert back == [GlossaryTerm("Silver Pines", "Silver Pines"), GlossaryTerm("Sheriff", "Şerif")]


def test_reads_headerless_and_extra_columns(tmp_path: Path) -> None:
    path = tmp_path / "dis.xlsx"
    path.write_bytes(
        table_xlsx(
            ["Sword of Light", "Işık Kılıcı", "eşya"],
            [["  Kingdom  ", " Krallık "], ["", "boş terim atlanır"], ["Mana", ""], ["Mana", "Mana"]],
        )
    )
    # Başlık yoksa ilk satır da veridir; üçüncü sütun not olarak okunur; aynı terim iki kez varsa sonuncusu geçer.
    assert read_glossary_xlsx(path) == [
        GlossaryTerm("Sword of Light", "Işık Kılıcı", "eşya"),
        GlossaryTerm("Kingdom", "Krallık"),
        GlossaryTerm("Mana", "Mana"),
    ]


def test_broken_or_empty_file_raises_turkish_error(tmp_path: Path) -> None:
    bad = tmp_path / "bozuk.xlsx"
    bad.write_bytes(b"bu bir xlsx degil")
    with pytest.raises(CsvError):
        read_glossary_xlsx(bad)
    empty = tmp_path / "bos.xlsx"
    empty.write_bytes(table_xlsx(list(GLOSSARY_COLUMNS), []))
    with pytest.raises(CsvError, match="terim"):
        read_glossary_xlsx(empty)


def test_merge_updates_case_insensitively_and_keeps_notes() -> None:
    existing = [GlossaryTerm("Sheriff", "Şerif", "unvan"), GlossaryTerm("Elara", "", "ablası")]
    imported = [GlossaryTerm("sheriff", "Polis Şefi"), GlossaryTerm("Kingdom", "Krallık"), GlossaryTerm("Elara", "")]
    merged, added, updated = merge_terms(existing, imported)
    assert merged == [
        GlossaryTerm("Sheriff", "Polis Şefi", "unvan"),  # yazımı korunur, çeviri güncellenir, not kalır
        GlossaryTerm("Elara", "", "ablası"),  # değişiklik yok
        GlossaryTerm("Kingdom", "Krallık"),
    ]
    assert (added, updated) == (1, 1)
