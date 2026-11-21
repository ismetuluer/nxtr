"""Dışa aktarma: kaynağı boş satırlar dosyaya yazılmaz; kart adı kaydet penceresinin önerisini gösterir."""

from __future__ import annotations

import pytest

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.csvio import CsvRow, plan_import, without_empty_source
from nxceviri.gui.csv_dialog import FORMAT_TXT, CsvExportDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _row(i: int, source: str = "Hi", group: str = "a>UI") -> TranslationRow:
    return TranslationRow(i, group, f"k{i}", source, "Selam" if source else "", "machine", "", (), None)


def _rows() -> list[TranslationRow]:
    return [_row(1, ""), _row(2, "  "), _row(3), _row(4), _row(5)]


def test_without_empty_source_drops_blank_sources_only() -> None:
    assert [r.id for r in without_empty_source(_rows())] == [3, 4, 5]


def test_dialog_counts_and_files_exclude_empty_rows() -> None:
    rows = _rows()
    d = CsvExportDialog(None, selected=rows[:2], visible=rows[:4], all_rows=rows)
    assert len(d.rows()) == 3
    assert d.scope_group.button(2).text().endswith("(3)")
    assert not d.scope_group.button(0).isEnabled()  # seçili iki satırın ikisi de boş
    assert d.cards[0].text().endswith("3 satır")
    assert d.split_label.text() == "1 dosya, 3 satır"
    assert d.skipped_label.text() == "2 boş satır atlandı"
    d.split_box.setChecked(True)
    d.part_spin.setValue(2)
    assert [len(c.rows) for c in d._planned] == [2, 1]
    first = d.preview_table.item(0, 0)
    assert first is not None
    assert first.text() == "Hi"
    d.scope_group.button(1).click()  # görünen: 4 satırın 2'si boş
    assert d.skipped_label.text() == "2 boş satır atlandı"


def test_no_note_when_nothing_skipped() -> None:
    rows = [_row(i) for i in range(1, 4)]
    d = CsvExportDialog(None, selected=[], visible=rows, all_rows=rows)
    assert d.skipped_label.isHidden()


def test_import_still_sees_empty_source_rows() -> None:
    rows = [_row(1, ""), _row(2)]
    plan = plan_import(rows, [CsvRow(None, "", "", "Yeni"), CsvRow(None, "Hi", "Selam", "Merhaba")])
    assert dict(plan.changes) == {1: "Yeni", 2: "Merhaba"}


def test_card_names_use_suggested_base_name() -> None:
    rows = [_row(i, group="a>Dialogue" if i < 3 else "a>UI") for i in range(1, 6)]
    d = CsvExportDialog(None, selected=[], visible=rows, all_rows=rows, name_hint="oyun_ceviri")
    assert d.cards[0].text().split("\n")[0] == "oyun_ceviri.xlsx"
    d.group_box.setChecked(True)
    assert d.cards[0].text().split("\n")[0] == "oyun_ceviri_Dialogue.xlsx"
    d.txt_radio.setChecked(True)
    assert d.format() == FORMAT_TXT
    assert d.cards[1].text().split("\n")[0] == "oyun_ceviri_UI.txt"
