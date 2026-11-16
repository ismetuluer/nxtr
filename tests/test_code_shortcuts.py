"""Kontrol kodlarını klavyeden ekleme (Ctrl+1…9) ve sayfa geçişinin Alt+1…5'e taşınması."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QItemSelectionModel, QSettings, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QPlainTextEdit
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.status import Status
from nxceviri.gui.editor_pane import EditorPane
from nxceviri.gui.main_window import STEP_SCAN, STEP_TRANSLATE, MainWindow
from nxceviri.gui.shortcuts import COMMANDS, COMMANDS_BY_ID, ShortcutRegistry
from nxceviri.gui.translate_page import COL_TRANSLATION, TranslatePage

pytestmark = pytest.mark.gui

CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier
ALTGR = CTRL | ALT
CODE_COMMANDS = [f"edit.code{n}" for n in range(1, 10)]


def _kind_of(_number: int) -> str:
    return "other"


def _row(translation: str = "Merhaba", labels: tuple[str, ...] = ("Satır sonu", "Renk")) -> TranslationRow:
    return TranslationRow(7, "a.msbt", "k", "Hi ⟦1⟧ you ⟦2⟧", translation, Status.MACHINE, "", labels, None)


def _pane(qtbot: QtBot, row: TranslationRow | None = None, registry: ShortcutRegistry | None = None) -> EditorPane:
    pane = EditorPane(registry)
    qtbot.addWidget(pane)
    pane.resize(600, 400)
    pane.show()
    qtbot.waitExposed(pane)
    pane.activateWindow()
    pane.set_row(row if row is not None else _row(), _kind_of, None)
    pane.translation_edit.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is pane.translation_edit)
    return pane


def _altgr_char(edit: QPlainTextEdit, key: Qt.Key, text: str) -> None:
    """Türkçe düzende AltGr+rakam: Windows'ta Ctrl+Alt değiştiricisi, tuş rakam, metin ise üretilen karakter."""
    event = QKeyEvent(QEvent.Type.KeyPress, key, ALTGR, text)
    QApplication.sendEvent(edit, event)


# --- katalog ---------------------------------------------------------------------------------


def test_catalog_has_nine_code_commands_with_ctrl_digits() -> None:
    for n, command_id in enumerate(CODE_COMMANDS, start=1):
        command = COMMANDS_BY_ID[command_id]
        assert command.default == f"Ctrl+{n}"
        assert command.label == f"Kod {n} Ekle"


def test_page_steps_moved_to_alt_digits_without_conflicts() -> None:
    steps = ("go.add", "go.scan", "go.translate", "go.qa", "go.export")
    assert [COMMANDS_BY_ID[c].default for c in steps] == [f"Alt+{n}" for n in range(1, 6)]
    registry = ShortcutRegistry()
    for command in COMMANDS:
        if command.default:
            assert registry.conflicts(command.id, QKeySequence(command.default)) == [], command.id


def test_user_choices_for_steps_are_kept(tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
    first = ShortcutRegistry()
    first.bind_settings(settings)
    first.set_sequence("go.translate", QKeySequence("Ctrl+Shift+3"))
    first.set_sequence("go.add", QKeySequence("Alt+1"))  # yeni varsayılana eşit: kayıt tutulmaz
    settings.sync()
    second = ShortcutRegistry()
    second.bind_settings(QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat))
    assert second.sequence("go.translate") == QKeySequence("Ctrl+Shift+3")
    assert not second.is_custom("go.add")
    assert second.sequence("go.add") == QKeySequence("Alt+1")


# --- düzenleme paneli ------------------------------------------------------------------------


def test_pane_ctrl_digit_inserts_code_at_cursor(qtbot: QtBot) -> None:
    pane = _pane(qtbot)
    pane.translation_edit.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(pane.translation_edit, Qt.Key.Key_2, CTRL)
    assert pane.translation_edit.toPlainText() == "Merhaba⟦2⟧"


def test_pane_shortcut_replaces_selection_like_the_chip(qtbot: QtBot) -> None:
    pane = _pane(qtbot)
    pane.translation_edit.selectAll()
    QTest.keyClick(pane.translation_edit, Qt.Key.Key_1, CTRL)
    by_key = pane.translation_edit.toPlainText()
    pane.set_row(_row(), _kind_of, None)
    pane.translation_edit.selectAll()
    qtbot.mouseClick(pane.chip_buttons[0], Qt.MouseButton.LeftButton)
    assert by_key == pane.translation_edit.toPlainText() == "⟦1⟧"


def test_pane_missing_code_changes_nothing_and_says_so(qtbot: QtBot) -> None:
    pane = _pane(qtbot)
    with qtbot.waitSignal(pane.notice) as blocker:
        QTest.keyClick(pane.translation_edit, Qt.Key.Key_5, CTRL)
    assert pane.translation_edit.toPlainText() == "Merhaba"
    assert "5" in blocker.args[0]


def test_pane_row_without_codes_changes_nothing(qtbot: QtBot) -> None:
    pane = _pane(qtbot, _row(labels=()))
    QTest.keyClick(pane.translation_edit, Qt.Key.Key_1, CTRL)
    assert pane.translation_edit.toPlainText() == "Merhaba"


def test_pane_insert_is_undone_by_the_editors_own_ctrl_z(qtbot: QtBot) -> None:
    pane = _pane(qtbot)
    pane.translation_edit.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(pane.translation_edit, Qt.Key.Key_1, CTRL)
    QTest.keyClick(pane.translation_edit, Qt.Key.Key_Z, CTRL)
    assert pane.translation_edit.toPlainText() == "Merhaba"


def test_pane_shortcut_does_nothing_when_focus_is_elsewhere(qtbot: QtBot) -> None:
    pane = _pane(qtbot)
    pane.source_view.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is pane.source_view)
    QTest.keyClick(pane.source_view, Qt.Key.Key_1, CTRL)
    assert pane.translation_edit.toPlainText() == "Merhaba"
    assert pane.source_view.toPlainText() == "Hi ⟦1⟧ you ⟦2⟧"


def test_pane_altgr_digit_types_the_character_and_inserts_no_code(qtbot: QtBot) -> None:
    pane = _pane(qtbot)
    pane.translation_edit.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(pane.translation_edit, Qt.Key.Key_2, ALTGR)  # kısayol eşleşmesi: hiçbir şey eklenmemeli
    assert "⟦" not in pane.translation_edit.toPlainText()
    _altgr_char(pane.translation_edit, Qt.Key.Key_3, "#")
    assert pane.translation_edit.toPlainText().endswith("#")
    assert "⟦" not in pane.translation_edit.toPlainText()


def test_chip_tooltip_shows_current_shortcut(qtbot: QtBot) -> None:
    registry = ShortcutRegistry()
    pane = _pane(qtbot, registry=registry)
    assert "Ctrl+1" in pane.chip_buttons[0].toolTip()
    assert "Ctrl+2" in pane.chip_buttons[1].toolTip()
    registry.set_sequence("edit.code2", QKeySequence("Ctrl+Shift+9"))
    assert "Ctrl+Shift+9" in pane.chip_buttons[1].toolTip()
    assert "Ctrl+2" not in pane.chip_buttons[1].toolTip()
    QTest.keyClick(pane.translation_edit, Qt.Key.Key_9, CTRL | Qt.KeyboardModifier.ShiftModifier)
    assert pane.translation_edit.toPlainText().startswith("⟦2⟧")


# --- hücre düzenleyicisi ---------------------------------------------------------------------


def _page(qtbot: QtBot, rows: list[TranslationRow]) -> TranslatePage:
    page = TranslatePage()
    qtbot.addWidget(page)
    page.resize(1100, 600)
    page.show()
    qtbot.waitExposed(page)
    page.activateWindow()
    page.set_rows(rows)
    return page


def _open_cell_editor(qtbot: QtBot, page: TranslatePage) -> QPlainTextEdit:
    index = page.proxy.index(0, COL_TRANSLATION)
    page.table.setCurrentIndex(index)
    page.table.edit(index)
    editor = page.table.findChild(QPlainTextEdit)
    assert editor is not None
    editor.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is editor)
    return editor


def test_cell_editor_ctrl_digit_inserts_code(qtbot: QtBot) -> None:
    page = _page(qtbot, [_row()])
    editor = _open_cell_editor(qtbot, page)
    editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(editor, Qt.Key.Key_2, CTRL)
    assert editor.toPlainText() == "Merhaba⟦2⟧"


def test_cell_editor_shortcut_replaces_selection_and_undoes(qtbot: QtBot) -> None:
    page = _page(qtbot, [_row()])
    editor = _open_cell_editor(qtbot, page)
    editor.selectAll()
    QTest.keyClick(editor, Qt.Key.Key_1, CTRL)
    assert editor.toPlainText() == "⟦1⟧"
    QTest.keyClick(editor, Qt.Key.Key_Z, CTRL)
    assert editor.toPlainText() == "Merhaba"


def test_cell_editor_missing_code_changes_nothing_and_hints(qtbot: QtBot) -> None:
    page = _page(qtbot, [_row()])
    editor = _open_cell_editor(qtbot, page)
    with qtbot.waitSignal(page.hint) as blocker:
        QTest.keyClick(editor, Qt.Key.Key_7, CTRL)
    assert editor.toPlainText() == "Merhaba"
    assert "7" in blocker.args[0]


def test_cell_editor_altgr_digit_types_the_character_and_inserts_no_code(qtbot: QtBot) -> None:
    page = _page(qtbot, [_row()])
    editor = _open_cell_editor(qtbot, page)
    editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(editor, Qt.Key.Key_1, ALTGR)
    assert "⟦" not in editor.toPlainText()
    _altgr_char(editor, Qt.Key.Key_4, "$")
    assert editor.toPlainText().endswith("$")
    assert "⟦" not in editor.toPlainText()


def test_table_selection_without_editor_opens_no_cell_editor(qtbot: QtBot) -> None:
    page = _page(qtbot, [_row()])
    _choose(page, 0)
    page.table.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is page.table)
    QTest.keyClick(page.table, Qt.Key.Key_1, CTRL)
    assert page.table.findChild(QPlainTextEdit) is None  # "herhangi bir tuş düzenlemeyi açar" kuralı tetiklenmedi
    row = page.current_row()
    assert row is not None
    assert row.translation == "Merhaba"  # kayıtlı metne dokunulmadı; kod yalnızca panelin kutusuna yazıldı


# --- sayfa geçişi ----------------------------------------------------------------------------


def _project() -> Project:
    project = Project.new()
    project.import_texts(
        [
            ImportedFile(
                "Dialogue.tsv",
                "0100",
                "unity",
                "base",
                (TextEntry("s01", 0, "Hello ⟦1⟧ world", (ControlCode(b"\\n", "Satır sonu"),)),),
            )
        ]
    )
    return project


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = MainWindow(QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat))
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.resize(1180, 780)
    w.show()
    qtbot.waitExposed(w)
    w.activateWindow()
    w.nav.setCurrentRow(STEP_SCAN)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_alt_digit_changes_page_and_ctrl_digit_does_not(qtbot: QtBot, window: MainWindow) -> None:
    window.nav.setFocus()
    QTest.keyClick(window.nav, Qt.Key.Key_3, ALT)
    assert window.nav.currentRow() == STEP_TRANSLATE
    window.nav.setCurrentRow(STEP_SCAN)
    QTest.keyClick(window.nav, Qt.Key.Key_3, CTRL)
    assert window.nav.currentRow() == STEP_SCAN


def test_altgr_digit_changes_no_page(qtbot: QtBot, window: MainWindow) -> None:
    window.nav.setFocus()
    for key in (Qt.Key.Key_1, Qt.Key.Key_3):
        QTest.keyClick(window.nav, key, ALTGR)
    assert window.nav.currentRow() == STEP_SCAN


def test_code_shortcut_in_other_field_inserts_nothing_and_keeps_page(qtbot: QtBot, window: MainWindow) -> None:
    window.nav.setCurrentRow(STEP_TRANSLATE)
    page = window.translate_page
    box = page.findChild(QLineEdit)
    assert box is not None
    box.setFocus()
    before = box.text()
    QTest.keyClick(box, Qt.Key.Key_1, CTRL)
    assert box.text() == before
    assert window.nav.currentRow() == STEP_TRANSLATE
    assert page.pane.translation_edit.toPlainText() == ""


def test_main_window_code_shortcuts_have_no_menu_entries(window: MainWindow) -> None:
    menus = window.menuBar().findChildren(QMenu)
    texts = [action.text() for menu in menus for action in menu.actions()]
    assert texts
    assert not any(t.startswith("Kod ") and t.endswith("Ekle") for t in texts)


# --- tablo odaktayken (hücre düzenleyicisi kapalı) -------------------------------------------


def _coded(row_id: int, file: str = "a.msbt", translation: str = "Merhaba", codes: int = 2) -> TranslationRow:
    labels = tuple(f"Kod {i}" for i in range(1, codes + 1))
    return TranslationRow(row_id, file, f"k{row_id}", "Hi ⟦1⟧ you ⟦2⟧", translation, Status.MACHINE, "", labels, None)


def _choose(page: TranslatePage, view_row: int) -> None:
    """Tek satırı seçip geçerli yapar. `select_row` kullanılmaz: önceki testin Ctrl tuşu kalıntısı seçimi tersler."""
    index = page.proxy.index(view_row, COL_TRANSLATION)
    page.table.selectionModel().setCurrentIndex(
        index, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
    )


def _table_page(qtbot: QtBot, rows: list[TranslationRow] | None = None) -> TranslatePage:
    page = _page(qtbot, rows if rows is not None else [_coded(1), _coded(2, translation="Selam", codes=1)])
    _choose(page, 0)
    qtbot.waitUntil(lambda: page.pane.row_id == 1 and len(page.selected_rows()) == 1)
    page.table.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is page.table)
    return page


def test_table_ctrl_digit_inserts_into_panel_and_focuses_it(qtbot: QtBot) -> None:
    page = _table_page(qtbot)
    page.pane.translation_edit.moveCursor(QTextCursor.MoveOperation.Start)
    QTest.keyClick(page.table, Qt.Key.Key_2, CTRL)
    assert page.pane.translation_edit.toPlainText() == "⟦2⟧Merhaba"  # tek tuş, tek ekleme
    assert QApplication.focusWidget() is page.pane.translation_edit
    assert page.table.findChild(QPlainTextEdit) is None


def test_table_missing_code_changes_nothing_keeps_focus_and_hints(qtbot: QtBot) -> None:
    page = _table_page(qtbot)
    with qtbot.waitSignal(page.hint) as blocker:
        QTest.keyClick(page.table, Qt.Key.Key_5, CTRL)
    assert "5" in blocker.args[0]
    assert page.pane.translation_edit.toPlainText() == "Merhaba"
    assert QApplication.focusWidget() is page.table


def test_table_shortcut_with_hidden_pane_hints_and_opens_no_editor(qtbot: QtBot) -> None:
    page = _table_page(qtbot)
    page.view_actions.pane_toggle.trigger()
    assert not page.pane.isVisibleTo(page)
    with qtbot.waitSignal(page.hint) as blocker:
        QTest.keyClick(page.table, Qt.Key.Key_1, CTRL)
    assert "paneli açın" in blocker.args[0]
    assert page.table.findChild(QPlainTextEdit) is None
    assert page.pane.translation_edit.toPlainText() == "Merhaba"


def test_table_shortcut_with_multiple_selection_does_nothing(qtbot: QtBot) -> None:
    page = _table_page(qtbot)
    page.table.selectAll()
    QTest.keyClick(page.table, Qt.Key.Key_1, CTRL)
    assert page.pane.translation_edit.toPlainText() in ("Merhaba", "Selam")
    assert "⟦" not in page.pane.translation_edit.toPlainText()
    assert QApplication.focusWidget() is page.table


def test_table_shortcut_right_after_row_change_writes_to_the_new_row(qtbot: QtBot) -> None:
    page = _table_page(qtbot)
    _choose(page, 1)  # panel eşzamanlaması beklenmeden tuşa basılır
    QTest.keyClick(page.table, Qt.Key.Key_1, CTRL)
    assert page.pane.row_id == 2
    assert "⟦1⟧" in page.pane.translation_edit.toPlainText()
    assert "Selam" in page.pane.translation_edit.toPlainText()
    row = page.model.row_by_id(1)
    assert row is not None
    assert row.translation == "Merhaba"


def test_table_altgr_digit_does_nothing(qtbot: QtBot) -> None:
    page = _table_page(qtbot)
    QTest.keyClick(page.table, Qt.Key.Key_2, ALTGR)
    assert page.pane.translation_edit.toPlainText() == "Merhaba"
    assert QApplication.focusWidget() is page.table


def test_table_shortcut_in_grouped_view_targets_right_row_and_skips_headers(qtbot: QtBot) -> None:
    rows = [_coded(1, "a.msbt"), _coded(2, "b.msbt", translation="Selam"), _coded(3, "b.msbt", translation="Dünya")]
    page = _table_page(qtbot, rows)
    page.group_action.trigger()
    assert page.proxy is page.group_proxy
    _choose(page, next(r for r in range(page.proxy.rowCount()) if (page._row_at(r) or _coded(0)).id == 3))
    page.table.setFocus()
    qtbot.waitUntil(lambda: page.pane.row_id == 3)
    QTest.keyClick(page.table, Qt.Key.Key_1, CTRL)
    assert page.pane.translation_edit.toPlainText().count("⟦1⟧") == 1
    assert "Dünya" in page.pane.translation_edit.toPlainText()
    header = next(r for r in range(page.proxy.rowCount()) if page.group_proxy.header_group(r) is not None)
    page.table.setFocus()
    page.table.setCurrentIndex(page.proxy.index(header, COL_TRANSLATION))
    before = page.pane.translation_edit.toPlainText()
    QTest.keyClick(page.table, Qt.Key.Key_2, CTRL)
    assert page.pane.translation_edit.toPlainText() == before
