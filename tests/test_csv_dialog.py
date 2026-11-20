"""Dışa aktarma penceresi (`CsvExportDialog`): varsayılanlar, parça sayısı ve canlı dosya önizlemesi."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.csvio import export_xlsx
from nxceviri.gui.csv_dialog import FORMAT_XLSX, MODE_FINDINGS, MODE_REDACTION, CsvExportDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _row(i: int, group: str = "a.assets>Dialogue") -> TranslationRow:
    return TranslationRow(i, group, f"k{i}", "Hi", "Selam", "machine", "", (), None)


def _dialog(rows: list[TranslationRow], mode: str = MODE_REDACTION, selected: int = 0) -> CsvExportDialog:
    return CsvExportDialog(
        None,
        selected=rows[:selected],
        visible=rows[:3],
        all_rows=rows if mode != MODE_FINDINGS else [],
        mode=mode,
    )


def test_defaults_are_xlsx_all_rows_no_group_no_split() -> None:
    rows = [_row(i, "a>Dialogue" if i % 2 else "a>UI") for i in range(10)]
    d = _dialog(rows, selected=5)
    assert d.format() == FORMAT_XLSX
    assert d.xlsx_radio.isChecked()
    assert d.xlsx_radio.text() == "Excel (XLSX)"
    assert d.txt_radio.text() == "Metin (TXT)"
    assert d.rows() is d._scopes[2]
    assert len(d.rows()) == 10
    assert not d.by_group()
    assert not d.split_box.isChecked()
    assert d.parts() == 0
    assert d.split_label.text() == "1 dosya, 10 satır"


def test_findings_mode_defaults_cover_all_findings_rows() -> None:
    rows = [_row(i) for i in range(6)]
    d = _dialog(rows, MODE_FINDINGS, selected=4)
    assert d.format() == FORMAT_XLSX
    assert d.rows() is d._scopes[1]  # görünen bulguların satırları
    assert d.parts() == 0
    assert not d.by_group()


def test_live_label_follows_parts_scope_and_grouping() -> None:
    rows = [_row(i, "a>Dialogue" if i < 6 else "a>UI") for i in range(10)]
    d = _dialog(rows)
    d.split_box.setChecked(True)
    assert d.part_spin.minimum() == 2
    assert d.part_spin.maximum() == 10
    d.part_spin.setValue(3)
    assert d.parts() == 3
    assert d.split_label.text() == "3 dosya, her biri en çok 4 satır"
    d.part_spin.setValue(4)
    assert d.split_label.text() == "4 dosya, her biri en çok 3 satır"
    d.group_box.setChecked(True)
    assert d.part_spin.maximum() == 6  # en büyük grup
    d.part_spin.setValue(2)
    assert d.split_label.text() == "2 grup × 2 parça = 4 dosya"
    d.split_box.setChecked(False)
    assert d.split_label.text() == "2 grup = 2 dosya"
    d.group_box.setChecked(False)
    d.scope_group.button(1).click()  # görünen (3 satır)
    assert d.split_label.text() == "1 dosya, 3 satır"
    d.split_box.setChecked(True)
    assert d.part_spin.maximum() == 3


def test_uneven_groups_label_and_files_match_writer(tmp_path: Path) -> None:
    rows = [_row(i, "a>Dialogue") for i in range(5)] + [_row(10 + i, "a>UI") for i in range(2)]
    d = _dialog(rows)
    d.group_box.setChecked(True)
    d.split_box.setChecked(True)
    d.part_spin.setValue(2)
    assert d.split_label.text() == "2 grup × 2 parça = 4 dosya"
    d.part_spin.setValue(4)  # Dialogue: 2 satır/parça = 3 dosya; UI: 1 satır/parça = 2 dosya
    assert d.split_label.text() == "2 grup, toplam 5 dosya (her biri en çok 2 satır)"
    paths = export_xlsx(d.rows(), tmp_path / "o.xlsx", by_group=d.by_group(), parts=d.parts())
    assert len(paths) == 5


def test_label_file_count_equals_produced_files(tmp_path: Path) -> None:
    rows = [_row(i) for i in range(20)]
    d = _dialog(rows)
    d.split_box.setChecked(True)
    d.part_spin.setValue(6)
    shown = int(d.split_label.text().split(" ")[0])
    paths = export_xlsx(d.rows(), tmp_path / "o.xlsx", parts=d.parts())
    assert len(paths) == shown
    assert all(p.exists() for p in paths)


def test_split_unavailable_for_single_row() -> None:
    d = _dialog([_row(1)])
    assert not d.split_box.isEnabled()
    assert d.parts() == 0
