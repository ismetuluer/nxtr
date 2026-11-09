"""Bul ve Değiştir'in taşınabilir penceresi: tablonun üstünde yer kaplamaz, konumu hatırlanır, kısayollar çalışır."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from nxceviri.gui.find_replace import FIELD_SOURCE, KEY_FIND_GEOMETRY
from nxceviri.gui.main_window import STEP_QA, STEP_TRANSLATE, MainWindow
from tests.test_statusbar import _make_window, _project

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    w.nav.setCurrentRow(STEP_TRANSLATE)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _open(qtbot: QtBot, w: MainWindow) -> None:
    w.activateWindow()
    qtbot.waitUntil(w.isActiveWindow, timeout=3000)
    w.menu_actions["edit.find"].trigger()
    qtbot.waitUntil(w.translate_page.find_window.isVisible, timeout=3000)


def test_find_opens_in_separate_window_not_above_the_table(qtbot: QtBot, window: MainWindow) -> None:
    page = window.translate_page
    table_top = page.table.mapTo(page, QPoint(0, 0)).y()
    _open(qtbot, window)
    find_window = page.find_window
    assert find_window.isWindow()
    assert find_window.windowFlags() & Qt.WindowType.Tool
    assert find_window.windowTitle() == "Bul ve Değiştir"
    assert page.table.mapTo(page, QPoint(0, 0)).y() == table_top  # tablo aşağı itilmedi
    assert not page.find_bar.close_button.isVisibleTo(find_window)  # pencerenin kendi kapat düğmesi var


def test_window_is_compact_and_count_does_not_cover_the_field(qtbot: QtBot, window: MainWindow) -> None:
    """Dizüstü ekranda uzun şerit yerine kareye yakın pencere; sayaç bul kutusunun (temizle düğmesi) üstüne binmez."""
    page = window.translate_page
    _open(qtbot, window)
    bar = page.find_bar
    bar.replace_toggle.setChecked(True)
    bar.set_field(FIELD_SOURCE)
    bar.find_edit.setText("Hello")
    bar.flush()
    find_window = page.find_window
    find_window.adjustSize()
    qtbot.wait(20)
    assert find_window.width() <= 460
    assert find_window.minimumWidth() <= 380

    def rect(widget: QWidget) -> QRect:
        return QRect(widget.mapTo(find_window, QPoint(0, 0)), widget.size())

    assert bar.count_label.text() == "1 / 1"
    assert not rect(bar.count_label).intersects(rect(bar.find_edit))
    for widget in (bar.replace_edit, bar.replace_button, bar.replace_all_button, bar.scope_button):
        assert rect(widget).right() <= find_window.width()  # hiçbir şey taşmaz


def test_window_close_button_closes_the_search(qtbot: QtBot, window: MainWindow) -> None:
    page = window.translate_page
    _open(qtbot, window)
    page.find_bar.set_field(FIELD_SOURCE)  # örnek projede çeviri yok; orijinalde ara
    page.find_bar.find_edit.setText("Hello")
    page.find_bar.flush()
    assert page.find_bar.match_count == 1
    page.find_window.close()
    assert not page.find_bar.isVisibleTo(page)
    assert page.find_bar.match_count == 0  # boyamalar temizlendi


def test_moved_position_is_remembered(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    page = window.translate_page
    _open(qtbot, window)
    page.find_window.move(140, 160)
    moved = page.find_window.pos()
    page.find_bar.close_bar()
    assert not page.find_window.isVisible()
    window.settings.sync()
    saved = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat).value(KEY_FIND_GEOMETRY)
    assert saved is not None
    _open(qtbot, window)
    assert page.find_window.pos() == moved


def test_f3_works_while_the_find_window_is_active(qtbot: QtBot, window: MainWindow) -> None:
    page = window.translate_page
    _open(qtbot, window)
    page.find_window.activateWindow()
    qtbot.waitUntil(page.find_window.isActiveWindow, timeout=3000)
    page.find_bar.set_field(FIELD_SOURCE)
    page.find_bar.find_edit.setText("o")  # Hello there, Goodbye: iki satırda "o"
    page.find_bar.flush()
    first = page.find_bar.current_id
    QTest.keyClick(page.find_bar.find_edit, Qt.Key.Key_F3)
    assert page.find_bar.current_id != first
    # Shift+F3 gerçek tuşla gönderilmez: ekransız ortamda Shift basılı kalır ve sonraki testleri bozar.
    window.menu_actions["edit.find_prev"].trigger()
    assert page.find_bar.current_id == first


def test_find_window_hides_with_the_page_and_returns_with_it(qtbot: QtBot, window: MainWindow) -> None:
    page = window.translate_page
    _open(qtbot, window)
    window.nav.setCurrentRow(STEP_QA)
    qtbot.waitUntil(lambda: not page.find_window.isVisible(), timeout=3000)
    window.nav.setCurrentRow(STEP_TRANSLATE)
    qtbot.waitUntil(page.find_window.isVisible, timeout=3000)  # arama açıktı: pencere geri gelir


def test_closed_search_does_not_reappear_with_the_page(qtbot: QtBot, window: MainWindow) -> None:
    page = window.translate_page
    _open(qtbot, window)
    page.find_bar.close_bar()
    window.nav.setCurrentRow(STEP_QA)
    window.nav.setCurrentRow(STEP_TRANSLATE)
    assert not page.find_window.isVisible()


def test_new_rows_close_the_search(qtbot: QtBot, window: MainWindow) -> None:
    page = window.translate_page
    _open(qtbot, window)
    page.set_rows(page.model.rows[:2])
    assert not page.find_window.isVisible()
    assert page.find_bar.isHidden()


def test_closing_the_main_window_remembers_the_find_window_position(qtbot: QtBot, window: MainWindow) -> None:
    page = window.translate_page
    _open(qtbot, window)
    page.find_window.move(131, 157)
    assert window.settings.value(KEY_FIND_GEOMETRY) is None
    window.dirty = False
    window.close()
    assert window.settings.value(KEY_FIND_GEOMETRY) is not None
    assert not page.find_window.isVisible()


def test_previous_open_row_works_while_the_search_is_closed(window: MainWindow) -> None:
    page = window.translate_page
    page.table.selectRow(1)
    keys = [r.key for r in page.model.rows]
    current = page.table.currentIndex().row()
    assert not page.find_bar.isVisible()
    window.menu_actions["edit.find_prev"].trigger()  # Shift+F3: F3'ün tersi
    assert page.table.currentIndex().row() == (current - 1) % len(keys)
    window.menu_actions["edit.find_prev"].trigger()
    assert page.table.currentIndex().row() == (current - 2) % len(keys)
