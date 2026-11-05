"""Çeviri sayfası görünümünün ana pencereye bağlanması: menü, durum çubuğu, kod türleri ve kapanışta kaydetme."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QFocusEvent
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox
from pytestqt.qtbot import QtBot

from nxceviri.core.translate.codekinds import KIND_PAGE_BREAK
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.marked_delegate import MarkedDelegate
from nxceviri.gui.translate_page import COL_SOURCE
from nxceviri.gui.view_actions import ALIGN_CENTER
from tests.test_gui_fit import CODE, _enable, _page
from tests.test_gui_fit import _project as fit_project
from tests.test_statusbar import _make_window, _project

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _restore_app(qtbot: QtBot) -> Iterator[None]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    yield
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)


@pytest.fixture(autouse=True)
def _no_modal_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kapanışta "kaydedilmemiş proje" sorusu testi kilitlemesin."""
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard)


def _close(w: MainWindow) -> None:
    w.dirty = False
    w.close()
    w.deleteLater()


def _all_actions(menu: QMenu) -> list[QAction]:
    found: list[QAction] = []
    for action in menu.actions():
        found.append(action)
        sub = action.menu()
        if isinstance(sub, QMenu):
            found.extend(_all_actions(sub))
    return found


def _view_menu(w: MainWindow) -> QMenu:
    for menu in w.menuBar().findChildren(QMenu):
        if menu.title().replace("&", "") == "Görünüm":
            return menu
    raise AssertionError("Görünüm menüsü yok")


def test_view_menu_has_view_actions(qtbot: QtBot, tmp_path: Path) -> None:
    w = _make_window(qtbot, tmp_path, _project())
    try:
        actions = _all_actions(_view_menu(w))
        view = w.translate_page.view_actions
        assert view.symbols in actions
        for action in (*view.align_actions.values(), *view.pane_actions.values()):
            assert action in actions
    finally:
        _close(w)


def test_status_bar_symbols_button_shares_action(qtbot: QtBot, tmp_path: Path) -> None:
    w = _make_window(qtbot, tmp_path, _project())
    try:
        view = w.translate_page.view_actions
        button = w.status_segments.symbols_button
        assert button.defaultAction() is view.symbols
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert view.symbols.isChecked()
        assert w.translate_page.source_delegate.symbols
    finally:
        _close(w)


def test_cursor_segment_shows_line_column_when_pane_focused(qtbot: QtBot, tmp_path: Path) -> None:
    w = _make_window(qtbot, tmp_path, _project())
    try:
        page = w.translate_page
        page._select_proxy_row(0)
        edit = page.pane.translation_edit
        edit.setPlainText("ab\ncd")
        cursor = edit.textCursor()
        cursor.setPosition(4)
        edit.setTextCursor(cursor)
        seg = w.status_segments
        assert not seg.cursor_label.isVisibleTo(w)  # odak yokken gizli
        QApplication.sendEvent(edit, QFocusEvent(QEvent.Type.FocusIn))
        assert seg.cursor_label.isVisibleTo(w)
        assert seg.cursor_label.text() == "Satır 2 · Sütun 2"
        QApplication.sendEvent(edit, QFocusEvent(QEvent.Type.FocusOut))
        assert not seg.cursor_label.isVisibleTo(w)
        qtbot.keyClick(edit, Qt.Key.Key_Escape)  # bekleyen metni at: kapanışta kaydetme sorusu çıkmasın
    finally:
        _close(w)


def test_code_kinds_feed_chips(qtbot: QtBot, tmp_path: Path) -> None:
    w = _make_window(qtbot, tmp_path, fit_project())
    try:
        page = _page(w)
        _enable(page, 40, 3)
        combo = page.fit_kinds.cellWidget(0, 1)
        assert combo is not None
        assert page.fit_kinds.item(0, 0).text() == CODE  # type: ignore[union-attr]
        combo.setCurrentIndex(combo.findData(KIND_PAGE_BREAK))  # type: ignore[attr-defined]
        delegate = w.translate_page.table.itemDelegateForColumn(COL_SOURCE)
        assert isinstance(delegate, MarkedDelegate)
        row_index = next(i for i, r in enumerate(w.translate_page.model.rows) if r.key == "d02")
        proxy_index = w.translate_page.proxy.mapFromSource(w.translate_page.model.index(row_index, COL_SOURCE))
        assert "§1" in delegate.html_for(proxy_index).replace("&nbsp;", "")
    finally:
        _close(w)


def test_close_flushes_pending_pane_text(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard
    )  # kaydedilmemiş proje sorusu
    w = _make_window(qtbot, tmp_path, _project())
    page = w.translate_page
    page._select_proxy_row(0)
    page.pane.translation_edit.setFocus()
    page.pane.translation_edit.selectAll()
    qtbot.keyClicks(page.pane.translation_edit, "kapanis")
    project = w.project
    saved: list[list[tuple[int, str]]] = []
    original = project.set_translations

    def spy(changes: list[tuple[int, str]], *args: object, **kwargs: object) -> object:
        saved.append(list(changes))
        return original(changes, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(project, "set_translations", spy)
    w.close()
    assert saved
    assert saved[0][0][1] == "kapanis"
    w.dirty = False
    w.deleteLater()


def test_project_replace_flushes_pending_text_before_swap(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = _make_window(qtbot, tmp_path, _project())
    try:
        page = w.translate_page
        page._select_proxy_row(0)
        page.pane.translation_edit.setFocus()
        page.pane.translation_edit.selectAll()
        qtbot.keyClicks(page.pane.translation_edit, "eski proje")
        old = w.project
        calls: list[object] = []
        original = old.set_translations

        def spy(changes: list[tuple[int, str]], *args: object, **kwargs: object) -> object:
            calls.append(w.project is old)  # yazma sırasında hâlâ eski proje geçerli olmalı
            return original(changes, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(old, "set_translations", spy)
        w._replace_project(_project())
        assert calls == [True]
    finally:
        _close(w)


def test_view_choices_survive_project_replace(qtbot: QtBot, tmp_path: Path) -> None:
    w = _make_window(qtbot, tmp_path, _project())
    try:
        w.translate_page.view_actions.align_actions[ALIGN_CENTER].trigger()
        w._replace_project(_project())
        assert w.translate_page.view_actions.align == ALIGN_CENTER
        assert w.translate_page.source_delegate.align == ALIGN_CENTER
        w.nav.setCurrentRow(STEP_QA)
    finally:
        _close(w)


def test_reload_rows_flushes_pending_text_before_reading(qtbot: QtBot, tmp_path: Path) -> None:
    w = _make_window(qtbot, tmp_path, _project())
    try:
        page = w.translate_page
        page._select_proxy_row(0)
        page.pane.translation_edit.setFocus()
        page.pane.translation_edit.selectAll()
        qtbot.keyClicks(page.pane.translation_edit, "taze")
        row_id = page.pane.row_id
        assert row_id is not None
        w._reload_rows()
        row = page.model.row_by_id(row_id)
        assert row is not None
        assert row.translation == "taze"  # tablo, kaydedilen metni yansıtır
    finally:
        _close(w)
