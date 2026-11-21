"""Dosya başına içe aktarma sayıları (`plan_import_files`), reddedilen düzeltmeler ve çıkacak dosya planı."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.csvio import (
    CsvRow,
    describe_import,
    export_xlsx,
    plan_files,
    plan_import,
    plan_import_files,
    preview_table,
)


def _row(i: int, group: str = "a>UI", source: str = "Hi ⟦1⟧", text: str = "Selam ⟦1⟧") -> TranslationRow:
    return TranslationRow(i, group, f"k{i}", source, text, "machine", "", (), None)


def test_plan_import_records_rejected_candidates_and_matched_lines() -> None:
    rows = [_row(1, source="Hi ⟦1⟧"), _row(2, source="Bye", text="Güle")]
    csv_rows = [
        CsvRow(None, "Hi ⟦1⟧", "Selam ⟦1⟧", "Merhaba"),  # kod yok: reddedilir
        CsvRow(None, "Bye", "Güle", "Hoşça kal"),
        CsvRow(None, "Nothing here", "x", "y"),  # eşleşmez
    ]
    plan = plan_import(rows, csv_rows)
    assert plan.rejected == {1: "Merhaba"}
    assert [eid for eid, _ in plan.code_problems] == [1]
    assert plan.matched_lines == {0, 1}
    assert plan.changes == [(2, "Hoşça kal")]


def test_plan_import_files_counts_per_file() -> None:
    rows = [_row(1, source="A", text="a"), _row(2, source="B", text="b"), _row(3, source="C", text="c")]
    first = [CsvRow(None, "A", "a", "Aa"), CsvRow(None, "B", "b", "")]
    foreign = [CsvRow(None, "Zzz", "q", "w"), CsvRow(None, "Yyy", "q", "w")]
    result = plan_import_files(rows, [("bir.xlsx", first), ("yabanci.txt", foreign)])
    assert [(f.name, f.lines, f.corrections, f.matched) for f in result.files] == [
        ("bir.xlsx", 2, 1, 2),
        ("yabanci.txt", 2, 2, 0),
    ]
    assert result.files[1].foreign
    assert not result.files[0].foreign
    # Birleşik plan, dosyaları art arda okumakla aynıdır.
    assert result.plan.changes == plan_import(rows, first + foreign).changes == [(1, "Aa")]
    assert result.plan.found == 4


def test_plan_import_files_empty_list_is_empty_plan() -> None:
    result = plan_import_files([_row(1)], [])
    assert result.files == []
    assert result.plan.found == 0
    assert result.plan.changes == []


def test_plan_import_files_legacy_csv_counts_text_as_correction() -> None:
    rows = [_row(1, source="A", text="a")]
    result = plan_import_files(rows, [("eski.csv", [CsvRow(1, "A", "Yeni"), CsvRow(99, "X", "Y")])])
    assert result.files[0].corrections == 2
    assert result.files[0].matched == 1


@pytest.mark.parametrize(
    ("by_group", "parts"),
    [(False, 0), (False, 3), (True, 0), (True, 2), (True, 7)],
)
def test_plan_files_matches_written_names(tmp_path: Path, by_group: bool, parts: int) -> None:
    rows = [_row(i, "a>Dialogue" if i < 6 else "a>UI") for i in range(9)]
    planned = plan_files(rows, by_group=by_group, parts=parts)
    written = export_xlsx(rows, tmp_path / "ad.xlsx", by_group=by_group, parts=parts)
    assert [f"ad{p.suffix}.xlsx" for p in planned] == [w.name for w in written]
    assert sum(len(p.rows) for p in planned) == len(rows)


def test_preview_table_columns_and_rows_per_mode() -> None:
    rows = [_row(1, "a>UI", "Hi", "Selam"), _row(2, "a>Dialogue", "Bye", "Güle")]
    header, body = preview_table(rows, mode="redaction")
    assert header == ("orijinal", "çeviri", "düzeltme", "grup")
    assert body[0] == ("Hi", "Selam", "", "UI")
    header, _ = preview_table(rows, mode="translation")
    assert header[2] == "yeni çeviri"
    header, body = preview_table(rows, mode="findings", notes={1: "Uyarı: kısa"})
    assert header[-1] == "bulgu"
    assert body[0][-1] == "Uyarı: kısa"
    assert body[1][-1] == ""
    _, limited = preview_table(rows * 50, mode="redaction", limit=5)
    assert len(limited) == 5


def test_describe_import_lists_every_note_of_the_old_summary() -> None:
    rows = [
        _row(1, source="Hi ⟦1⟧"),
        _row(2, source="Bye", text="Güle"),
        TranslationRow(3, "a>UI", "k3", "Ok", "Tamam", "approved", "", (), None),
    ]
    csv_rows = [
        CsvRow(None, "Hi ⟦1⟧", "Selam ⟦1⟧", "Merhaba"),  # kod uymuyor
        CsvRow(None, "Bye", "Güle", "Hoşça <b>kal</b>"),  # temizlendi
        CsvRow(None, "Ok", "Tamam", "Peki"),  # onaylıydı
        CsvRow(None, "Yok", "x", "y"),  # eşleşmedi
    ]
    plan = plan_import(rows, csv_rows)
    lines = describe_import(plan, {1: "k1"}, "Redakte")
    text = "\n".join(lines)
    assert plan.skipped == 2
    assert "1 satırın kontrol kodları uymuyor" in text
    assert "1 satır projedeki bir satırla eşleşmedi" in text
    assert "Değişenlerin 1 tanesi onaylıydı; durumları “Redakte” olur." in text
    assert "1 satırdaki fazla etiket veya bozuk kod yazımı programca düzeltildi." in text
    assert "  • k1: " in text


def test_describe_import_flags_whole_file_from_another_project() -> None:
    plan = plan_import([_row(1)], [CsvRow(None, "Zzz", "q", "w")])
    assert any("başka bir projeden" in line for line in describe_import(plan, {}, "Redakte"))
    csv_plan = plan_import([_row(1)], [CsvRow(77, "Zzz", "w")])
    assert any("başka bir projeden" in line for line in describe_import(csv_plan, {}, "Redakte"))
    assert describe_import(plan_import([_row(1)], []), {}, "Redakte") == []
