"""Dışa aktarma penceresinin önizlemeli düzeni: çıkacak dosya kartları ve ilk satırların tablosu."""

from __future__ import annotations

import time

import pytest

from nxceviri.core.project import TranslationRow
from nxceviri.gui.csv_dialog import MODE_FINDINGS, MODE_REDACTION, MODE_TRANSLATION, CsvExportDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _row(i: int, group: str = "a.assets>Dialogue") -> TranslationRow:
    return TranslationRow(i, group, f"k{i}", "Hi", "Selam", "machine", "", (), None)


def _dialog(rows: list[TranslationRow]) -> CsvExportDialog:
    return CsvExportDialog(None, selected=[], visible=rows[:3], all_rows=rows)


def _card_names(d: CsvExportDialog) -> list[str]:
    return [c.text().split("\n")[0] for c in d.cards]


def _cell(d: CsvExportDialog, row: int, column: int) -> str:
    item = d.preview_table.item(row, column)
    assert item is not None
    return item.text()


def _header(d: CsvExportDialog) -> list[str]:
    table = d.preview_table
    items = [table.horizontalHeaderItem(c) for c in range(table.columnCount())]
    return [item.text() for item in items if item is not None]


def test_single_file_card_and_preview_show_real_columns() -> None:
    d = _dialog([_row(i) for i in range(5)])
    assert _card_names(d) == ["ad.xlsx"]
    assert d.cards[0].text().endswith("5 satır")
    assert d.save_button.text() == "Kaydet…"
    assert _header(d) == ["orijinal", "çeviri", "düzeltme", "grup"]
    assert d.preview_table.rowCount() == 5
    assert _cell(d, 0, 0) == "Hi"
    assert _cell(d, 0, 2) == ""
    assert d.preview_more.isHidden()


def test_preview_follows_format_parts_and_group() -> None:
    d = _dialog([_row(i, "a>Dialogue" if i < 6 else "a>UI") for i in range(10)])
    d.txt_radio.setChecked(True)
    assert _card_names(d) == ["ad.txt"]
    d.split_box.setChecked(True)
    d.part_spin.setValue(3)
    assert _card_names(d) == ["…_001.txt", "…_002.txt", "…_003.txt"]
    assert d.save_button.text() == "3 dosyayı kaydet…"
    d.group_box.setChecked(True)
    d.split_box.setChecked(False)
    assert _card_names(d) == ["…_Dialogue.txt", "…_UI.txt"]
    assert d.split_label.text() == "2 grup = 2 dosya"
    d.split_box.setChecked(True)
    d.part_spin.setValue(2)
    assert _card_names(d)[0] == "…_Dialogue_001.txt"
    assert len(d.cards) == 4


def test_card_selection_switches_the_preview_rows() -> None:
    d = _dialog([_row(i, "a>Dialogue" if i < 6 else "a>UI") for i in range(10)])
    d.group_box.setChecked(True)
    assert _cell(d, 0, 3) == "Dialogue"
    d.cards[1].click()
    assert d.cards[1].isChecked()
    assert not d.cards[0].isChecked()
    assert _cell(d, 0, 3) == "UI"
    assert d.preview_table.rowCount() == 4
    d.group_box.setChecked(False)  # ayar değişince seçim ilk karta döner
    assert d.cards[0].isChecked()


def test_preview_is_limited_and_says_how_many_more() -> None:
    d = _dialog([_row(i) for i in range(57)])
    assert d.preview_table.rowCount() == 20
    assert d.preview_more.text() == "… ve 37 satır daha"
    assert not d.preview_more.isHidden()


def test_cards_are_capped_with_more_label() -> None:
    d = _dialog([_row(i) for i in range(60)])
    d.split_box.setChecked(True)
    d.part_spin.setValue(30)
    assert len(d.cards) == 12
    assert d.more_label.text() == "ve 18 dosya daha"
    assert d.save_button.text() == "30 dosyayı kaydet…"
    d.part_spin.setValue(5)
    assert d.more_label.isHidden()


@pytest.mark.parametrize(
    ("mode", "third", "last"),
    [
        (MODE_REDACTION, "düzeltme", "grup"),
        (MODE_TRANSLATION, "yeni çeviri", "grup"),
        (MODE_FINDINGS, "düzeltme", "bulgu"),
    ],
)
def test_three_modes_share_the_layout_with_their_own_columns(mode: str, third: str, last: str) -> None:
    rows = [_row(i) for i in range(4)]
    d = CsvExportDialog(
        None,
        selected=[],
        visible=rows,
        all_rows=rows if mode != MODE_FINDINGS else [],
        mode=mode,
        notes={0: "Uyarı: kısa"},
    )
    header = _header(d)
    assert header[2] == third
    assert header[-1] == last
    assert d.prompt.toPlainText()
    if mode == MODE_FINDINGS:
        assert _cell(d, 0, 4) == "Uyarı: kısa"


def test_prompt_section_is_collapsed_but_filled() -> None:
    d = _dialog([_row(1)])
    assert d.prompt.isHidden()
    assert "⟦1⟧" in d.prompt.toPlainText()
    d.prompt_toggle.click()
    assert not d.prompt.isHidden()
    d.prompt_toggle.click()
    assert d.prompt.isHidden()


def test_multiline_text_is_shown_on_one_line() -> None:
    row = TranslationRow(1, "a>UI", "k1", "Line one\nline two", "Satır bir\nsatır iki", "machine", "", (), None)
    d = _dialog([row])
    assert "\n" not in _cell(d, 0, 0)
    assert "\n" not in _cell(d, 0, 1)


def test_many_rows_preview_is_fast() -> None:
    rows = [_row(i, f"a>G{i % 14}") for i in range(57000)]
    started = time.perf_counter()
    d = _dialog(rows)
    d.group_box.setChecked(True)
    d.split_box.setChecked(True)
    for parts in (2, 3, 4, 8):
        d.part_spin.setValue(parts)
    assert time.perf_counter() - started < 10
    assert d.preview_table.rowCount() == 20


def test_dialog_fits_narrow_window_and_shows() -> None:
    d = _dialog([_row(i) for i in range(30)])
    d.resize(720, 520)
    d.show()
    assert d.width() >= d.minimumWidth()
