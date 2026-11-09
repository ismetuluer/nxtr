"""Bul ve Değiştir'in taşınabilir penceresi: tablonun üstünde yer kaplamaz, konumu hatırlanır, kısayollar çalışır."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot

from nxceviri.gui.find_replace import FIELD_SOURCE, KEY_FIND_GEOMETRY
from nxceviri.gui.main_window import STEP_TRANSLATE, MainWindow
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
