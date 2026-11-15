"""Çevir tablosu ve gruplu görünüm: kapalıyken tablo doğrudan süzgeci görür; aç/kapa geçişi durumu korur."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QPlainTextEdit
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.status import Status
from nxceviri.gui.translate_page import COL_FILE, COL_KEY, COL_SOURCE, COL_TRANSLATION, TranslatePage

pytestmark = pytest.mark.gui


def _row(i: int, source: str, translation: str = "", status: str = Status.MACHINE) -> TranslationRow:
    return TranslationRow(i, f"Data/f{i % 3}.msbt", f"k{i}", source, translation, status, "", (), None, "", "msbt")


def _page(qtbot: QtBot, rows: list[TranslationRow]) -> TranslatePage:
    p = TranslatePage()
    qtbot.addWidget(p)
    p.resize(1000, 500)
    p.show()
    p.set_rows(rows)
    p.model.commit = lambda changes: [
        TranslationRow(
            i, r.file, r.key, r.source, t, Status.APPROVED if t else Status.UNTRANSLATED, "", (), None, "", "msbt"
        )
        for i, t in changes
        if (r := p.model.row_by_id(i)) is not None
    ]
    return p


ROWS = [_row(i, f"{'Elma' if i % 2 else 'Armut'} {i}", f"Çeviri {i}") for i in range(1, 21)]


def _current_id(p: TranslatePage) -> int | None:
    row = p.current_row()
    return None if row is None else row.id


def _select_ids(p: TranslatePage, ids: list[int]) -> None:
    selection = p.table.selectionModel()
    selection.clearSelection()
    for row_id in ids:
        index = p._view_index(p.model.position(row_id) or 0)
        selection.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)


def test_ungrouped_table_sees_filter_without_proxy(qtbot: QtBot) -> None:
    p = _page(qtbot, ROWS)

    def models() -> tuple[object, object, object]:
        return p.table.model(), p.proxy, p.group_proxy.sourceModel()

    assert models() == (p.filter, p.filter, None)  # kapalıyken vekil kaynaktan kopuk: hiçbir sinyal işlemez
    assert p._set_grouped(True)
    assert models() == (p.group_proxy, p.group_proxy, p.filter)
    assert p._set_grouped(False)
    assert models() == (p.filter, p.filter, None)


@pytest.mark.parametrize("grouped", [False, True])
def test_filter_change_keeps_selection_and_current_row(qtbot: QtBot, grouped: bool) -> None:
    p = _page(qtbot, ROWS)
    p._set_grouped(grouped)
    p.table.setCurrentIndex(p._view_index(p.model.position(7) or 0, COL_TRANSLATION))
    _select_ids(p, [5, 7, 9])
    assert _current_id(p) == 7
    p.search.setText("Elma")  # tek sayılı satırlar kalır; seçili satırlar yer değiştirir
    assert p.filter.rowCount() == 10
    assert sorted(r.id for r in p.selected_rows()) == [5, 7, 9]
    assert _current_id(p) == 7
    p.search.setText("Armut")  # seçili satırların hepsi süzgeçten çıkar: seçim boşalır, başka satıra kaymaz
    assert p.selected_rows() == []
    p.search.clear()
    assert all(r.id in {5, 7, 9} for r in p.selected_rows())


@pytest.mark.parametrize("grouped", [False, True])
def test_approve_and_delete_apply_to_selected_rows_after_filter_change(qtbot: QtBot, grouped: bool) -> None:
    p = _page(qtbot, ROWS)
    p._set_grouped(grouped)
    _select_ids(p, [3, 11])
    p.search.setText("Elma")
    p.approve_selected()
    approved = {r.id for r in p.model.rows if r.status == Status.APPROVED}
    assert approved == {3, 11}
    _select_ids(p, [13])
    p.search.setText("1")  # 1, 10-19
    p.clear_selected()
    assert [r.id for r in p.model.rows if not r.translation] == [13]


def test_all_count_uses_filter_not_view(qtbot: QtBot) -> None:
    p = _page(qtbot, ROWS)
    p.search.setText("Elma")
    text, _tip = p._all_text_tip()
    assert text == "10 / 20"
    assert p.find_filters_active()


def _group_by_file(p: TranslatePage) -> None:
    """Gruplamayı sayfanın geçiş yardımcısıyla açar (arayüz düğmesi sonraki adımda)."""
    assert p._set_grouped(True)


def test_grouped_helpers_skip_headers_and_open_collapsed_groups(qtbot: QtBot) -> None:
    p = _page(qtbot, ROWS)
    _group_by_file(p)
    assert p.group_proxy.header_group(0) == "f1.msbt"  # ilk satırın dosyası önce gelir
    assert p.proxy.rowCount() == 23  # 20 satır + 3 başlık
    p.table.selectAll()
    assert sorted(r.id for r in p.selected_rows()) == list(range(1, 21))  # başlıklar seçime girmez
    p.group_proxy.set_collapsed("f2.msbt", True)
    assert p._all_text_tip()[0] == "20"  # katlamak süzmek değildir
    assert not p.find_filters_active()
    assert len(p.filtered_rows()) == 20
    assert p.go_to_number(2)  # 2. satır f2'de: grup açılır
    assert not p.group_proxy.is_collapsed("f2.msbt")
    assert _current_id(p) == 2
    p.group_proxy.set_collapsed("f2.msbt", True)
    p.select_row(5)
    assert _current_id(p) == 5
    assert not p.group_proxy.is_collapsed("f2.msbt")


def test_grouped_navigation_follows_group_order(qtbot: QtBot) -> None:
    p = _page(qtbot, ROWS)
    _group_by_file(p)
    p.select_row(19)  # f1'in son satırı
    p._navigate(1)
    assert _current_id(p) == 2
    p.group_proxy.set_collapsed("f0.msbt", True)
    p._navigate(1)  # f2'nin sonuna kadar
    p.select_row(20)  # f2'nin son satırı
    p._navigate(1)  # f0 katlı: açılır
    assert _current_id(p) == 3
    assert not p.group_proxy.is_collapsed("f0.msbt")
    assert p.find_order(3) > p.find_order(20) > p.find_order(19)


def test_toggle_cycle_keeps_selection_current_and_columns(qtbot: QtBot) -> None:
    p = _page(qtbot, ROWS)
    header = p.table.horizontalHeader()
    header.resizeSection(COL_SOURCE, 211)
    p.table.setColumnHidden(COL_KEY, True)
    header.setSortIndicator(COL_FILE, Qt.SortOrder.AscendingOrder)  # sıralama modelde yapılır, gösterge kalmalı
    p.table.setCurrentIndex(p._view_index(p.model.position(8) or 0, COL_TRANSLATION))
    _select_ids(p, [4, 8, 17])
    state = (header.sectionSize(COL_SOURCE), p.table.isColumnHidden(COL_KEY), header.sortIndicatorSection())
    calls: list[int] = []
    p._sync_pane = lambda force=False: calls.append(1)  # type: ignore[method-assign]
    for on in (True, False, True, False):
        assert p._set_grouped(on)
        assert _current_id(p) == 8
        assert sorted(r.id for r in p.selected_rows()) == [4, 8, 17]
        assert (header.sectionSize(COL_SOURCE), p.table.isColumnHidden(COL_KEY), header.sortIndicatorSection()) == state
        assert p.table.currentIndex().column() == COL_TRANSLATION
    # Bağlantılar sızmaz ve çiftlenmez: tek seçim değişikliği paneli bir kez (seçim) + bir kez (geçerli) yeniler.
    calls.clear()
    p.table.selectRow(0)
    single = len(calls)
    p._set_grouped(True)
    p._set_grouped(False)
    calls.clear()
    p.table.selectRow(1)
    assert len(calls) == single
    assert single <= 2


def test_switch_commits_open_cell_editor_and_pane_text(qtbot: QtBot) -> None:
    p = _page(qtbot, ROWS)
    index = p._view_index(p.model.position(6) or 0, COL_TRANSLATION)
    p.table.setCurrentIndex(index)
    p.table.edit(index)
    editors = p.table.viewport().findChildren(QPlainTextEdit)
    assert editors
    editors[0].setPlainText("Hücrede yazıldı")
    assert p._set_grouped(True)
    assert p.model.row_by_id(6).translation == "Hücrede yazıldı"  # type: ignore[union-attr]
    p.select_row(9)
    p.pane.translation_edit.setPlainText("Panelde yazıldı")
    assert p.pane.has_pending()
    assert p._set_grouped(False)
    assert p.model.row_by_id(9).translation == "Panelde yazıldı"  # type: ignore[union-attr]
    assert not p.pane.has_pending()
