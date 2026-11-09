"""Yazım Denetimi penceresi: sözcük tablosu, satır listesi, sinyaller ve boş durum."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem
from pytestqt.qtbot import QtBot

from nxceviri.core.spell.report import WordUse
from nxceviri.gui.spell_window import SpellWindow

pytestmark = pytest.mark.gui

WORDS = [WordUse("zzz", 3, (1, 2, 3)), WordUse("ççç", 2, (2, 3)), WordUse("bbb", 1, (3,))]


@pytest.fixture
def win(qtbot: QtBot) -> SpellWindow:
    w = SpellWindow(None)
    qtbot.addWidget(w)
    w.set_words(WORDS)
    w.show()
    return w


def _cell(w: SpellWindow, row: int, column: int = 0) -> QTableWidgetItem:
    item = w.table.item(row, column)
    assert item is not None
    return item


def _shown(w: SpellWindow) -> list[str]:
    return [_cell(w, r).text() for r in range(w.table.rowCount()) if not w.table.isRowHidden(r)]


def _select(w: SpellWindow, *rows: int) -> None:
    w.table.clearSelection()
    for r in rows:
        _cell(w, r).setSelected(True)


def test_table_lists_words_with_counts(win: SpellWindow) -> None:
    assert win.windowTitle() == "Yazım Denetimi"
    assert _shown(win) == ["zzz", "ççç", "bbb"]
    assert [_cell(win, r, 1).text() for r in range(3)] == ["3", "2", "1"]


def test_search_filters_words(win: SpellWindow) -> None:
    win.search.setText("ç")
    assert _shown(win) == ["ççç"]
    win.search.setText("")
    assert len(_shown(win)) == 3


def test_empty_state_when_no_words(win: SpellWindow) -> None:
    win.set_words([])
    assert win.empty_label.isVisibleTo(win)
    assert not win.table.isVisibleTo(win)
    assert not win.ignore_button.isEnabled()
    assert "Bilinmeyen sözcük yok" in win.empty_label.text()
    win.set_words(WORDS)
    assert not win.empty_label.isVisibleTo(win)
    assert win.table.isVisibleTo(win)


def test_selecting_a_word_fills_the_row_list_and_double_click_shows_row(win: SpellWindow, qtbot: QtBot) -> None:
    _select(win, 0)
    assert win.rows_list.count() == 3
    ids = [win.rows_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(3)]
    assert ids == [1, 2, 3]
    with qtbot.waitSignal(win.show_row) as sig:
        win.rows_list.itemDoubleClicked.emit(win.rows_list.item(1))
    assert sig.args == [2]


def test_ignore_and_add_emit_selected_words(win: SpellWindow, qtbot: QtBot) -> None:
    _select(win, 0, 2)
    with qtbot.waitSignal(win.ignore_requested) as ignored:
        win.ignore_button.click()
    assert sorted(ignored.args[0]) == ["bbb", "zzz"]
    with qtbot.waitSignal(win.add_requested) as added:
        win.add_button.click()
    assert sorted(added.args[0]) == ["bbb", "zzz"]


def test_replace_emits_old_and_new_and_needs_both(win: SpellWindow, qtbot: QtBot) -> None:
    assert not win.replace_button.isEnabled()  # seçim yok
    _select(win, 0)
    assert not win.replace_button.isEnabled()  # yeni sözcük yok
    win.replace_edit.setText("  yeni ")
    assert win.replace_button.isEnabled()
    with qtbot.waitSignal(win.replace_requested) as sig:
        win.replace_button.click()
    assert sig.args == ["zzz", "yeni"]


def test_replace_disabled_with_multiple_selection(win: SpellWindow) -> None:
    win.replace_edit.setText("x")
    _select(win, 0, 1)
    assert not win.replace_button.isEnabled()
    assert win.ignore_button.isEnabled()


def test_set_words_keeps_selection_when_word_remains(win: SpellWindow) -> None:
    _select(win, 1)
    win.set_words([WordUse("ççç", 1, (3,)), WordUse("bbb", 1, (3,))])
    assert win.selected_words() == ["ççç"]
    assert win.rows_list.count() == 1
    win.set_words([WordUse("bbb", 1, (3,))])
    assert win.selected_words() == []
    assert win.rows_list.count() == 0
