"""Arayüz: yazım denetimi — editörde işaret ve sağ tık, Kontrol Et'te toplu ekleme, kullanıcı sözlüğü."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.userdict import UserDictionary
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.gui import main_window as main_window_module
from nxceviri.gui import spell_dialogs
from nxceviri.gui.editor_pane import EditorPane
from nxceviri.gui.main_window import STEP_QA, STEP_TRANSLATE, MainWindow

pytestmark = pytest.mark.gui

WORDS = ["merhaba", "oyun", "başlat", "yükle", "iyi", "ile", "tanış"]


def _underlined(pane: EditorPane) -> list[str]:
    edit = pane.translation_edit
    out = []
    for sel in edit.extraSelections():
        fmt: QTextCharFormat = sel.format
        if fmt.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline:
            out.append(sel.cursor.selectedText())
    return out


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w.user_dictionary = UserDictionary(tmp_path / "yazim.txt")
    w.spell = SpellChecker(BloomFilter.build(WORDS, error_rate=0.0001), w.user_dictionary.words())
    p = Project.new()
    entries = (TextEntry("a", 0, "Start game", ()), TextEntry("b", 1, "Meet Elara", ()))
    p.import_texts([ImportedFile("Menu.tsv", "0100", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations([(rows["a"].id, "Oyun başlatt"), (rows["b"].id, "Elara ile tanış")], machine=True)
    p.set_glossary([GlossaryTerm("Elara", "Elara")])
    w._replace_project(p)
    w.show()
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_pane_underlines_unknown_words_and_offers_adding(qtbot: QtBot, window: MainWindow) -> None:
    window.nav.setCurrentRow(STEP_TRANSLATE)
    page = window.translate_page
    page.table.selectRow(0)
    qtbot.waitUntil(lambda: page.pane.translation_edit.toPlainText() == "Oyun başlatt", timeout=5000)
    assert _underlined(page.pane) == ["başlatt"]
    page.pane.set_spell(None, frozenset())
    assert _underlined(page.pane) == []
    page.pane.set_spell(window.spell, frozenset())
    assert page.pane.unknown_word_at(7) == "başlatt"
    assert page.pane.unknown_word_at(1) is None


def test_adding_word_from_pane_persists_and_clears_underline(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    page = window.translate_page
    page.table.selectRow(0)
    qtbot.waitUntil(lambda: page.pane.translation_edit.toPlainText() == "Oyun başlatt", timeout=5000)
    page.pane.spell_word_requested.emit("başlatt")
    assert UserDictionary(tmp_path / "yazim.txt").words() == frozenset({"başlatt"})
    assert _underlined(page.pane) == []
    assert "yazım sözlüğüne eklendi" in window.statusBar().currentMessage()


def test_pane_context_menu_has_add_action(qtbot: QtBot, window: MainWindow) -> None:
    page = window.translate_page
    page.table.selectRow(0)
    qtbot.waitUntil(lambda: page.pane.translation_edit.toPlainText() == "Oyun başlatt", timeout=5000)
    edit = page.pane.translation_edit
    cursor = QTextCursor(edit.document())
    cursor.setPosition(9)  # "başlatt" içinde
    texts = [a.text() for a in edit.build_menu(edit.cursorRect(cursor).center()).actions()]
    assert "“başlatt” sözcüğünü yazım sözlüğüne ekle" in texts
    cursor.setPosition(1)  # "Oyun" bilinen sözcük
    texts = [a.text() for a in edit.build_menu(edit.cursorRect(cursor).center()).actions()]
    assert not any("yazım sözlüğüne ekle" in t for t in texts)


def test_qa_lists_spelling_and_adds_selected_words(
    qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.nav.setCurrentRow(STEP_QA)
    window.run_checks()
    page = window.qa_page
    spelling = [i for i in page.model.issues if i.kind == "spelling"]
    assert [i.words for i in spelling] == [("başlatt",)]  # "Elara" kaynakta ve oyun sözlüğünde var
    assert not page.spell_add_button.isEnabled()
    assert page.proxy.rowCount() == 0  # bilgi düzeyi: varsayılan listeyi kirletmez
    page.chip_bar.chips["spelling"].click()
    assert page.proxy.rowCount() == 1
    for row in range(page.proxy.rowCount()):
        if page.model.issues[page.proxy.mapToSource(page.proxy.index(row, 0)).row()].kind == "spelling":
            page.table.selectRow(row)
    assert page.spell_add_button.isEnabled()

    chosen: list[list[str]] = []

    def fake_exec(self: spell_dialogs.AddSpellWordsDialog) -> int:
        chosen.append(self.selected())
        return QDialog.DialogCode.Accepted.value

    monkeypatch.setattr(spell_dialogs.AddSpellWordsDialog, "exec", fake_exec)
    page.spell_add_button.trigger()
    assert chosen == [["başlatt"]]
    assert window.user_dictionary.words() == frozenset({"başlatt"})
    qtbot.waitUntil(lambda: not window.busy)  # denetim arka planda yenilenir
    assert not [i for i in page.model.issues if i.kind == "spelling" and "başlatt" in i.words]  # yeniden denetlendi


def test_user_dictionary_dialog_removes_words(qtbot: QtBot, tmp_path: Path) -> None:
    user = UserDictionary(tmp_path / "yazim.txt")
    user.add(["elara", "mara", "kael"])
    dialog = spell_dialogs.UserDictionaryDialog(None, user)
    qtbot.addWidget(dialog)
    assert [dialog.list.item(i).text() for i in range(dialog.list.count())] == ["elara", "kael", "mara"]
    dialog.list.setCurrentRow(1)
    dialog.remove_button.click()
    assert user.words() == frozenset({"elara", "mara"})
    assert dialog.list.count() == 2
    assert main_window_module  # içe aktarma: arayüz testleri aynı modülü kullanır


def test_copied_words_setting_flags_original_words(qtbot: QtBot, window: MainWindow) -> None:
    from nxceviri.gui.settings_dialog import KEY_SPELL_COPIED

    page = window.translate_page
    page.table.selectRow(1)  # "Elara ile tanış": Elara kaynakta da var
    qtbot.waitUntil(lambda: page.pane.translation_edit.toPlainText() == "Elara ile tanış", timeout=5000)
    assert _underlined(page.pane) == []
    window._set_spell_copied(True)
    assert str(window.settings.value(KEY_SPELL_COPIED)) == "1"
    assert window.spell is not None
    assert window.spell.unknown_words("Elara ile tanış", "Meet Elara") == ["elara"]
    window._set_spell_copied(False)
    assert window.spell.unknown_words("Elara ile tanış", "Meet Elara") == []
    assert str(window.settings.value(KEY_SPELL_COPIED)) == "0"


def test_live_settings_page_has_copied_words_option(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    from nxceviri.gui.settings_dialog import KEY_SPELL_COPIED, PAGE_LIVE, SettingsDialog

    window.settings.setValue(KEY_SPELL_COPIED, "1")
    dialog = SettingsDialog(
        window,
        window.settings,
        window.shortcuts,
        window.translate_page.view_actions,
        window.secrets,
        theme=window._theme_mode(),
        font_size=window._font_size(),
        wrap=window.translate_page.wrap_box,
        issue_colors=window.translate_page.colors_box,
        error_rows=window.translate_page.error_rows_box,
        updates_available=False,
        page=PAGE_LIVE,
    )
    qtbot.addWidget(dialog)
    assert dialog.spell_copied_box.text() == "Orijinalden aynen kopyalanan sözcükleri de işaretle"
    assert dialog.spell_copied_box.isChecked()
    seen: list[bool] = []
    dialog.spell_copied_changed.connect(seen.append)
    dialog.spell_copied_box.setChecked(False)
    assert seen == [False]
