"""C aşaması bağlantıları: Yazım Denetimi penceresi, yazım yoksayma, "Terim değil", çip stili."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QAbstractButton, QMenu
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.checks import QaIssue
from nxceviri.core.qa.live import LIVE_KINDS, LiveChecker, LiveContext
from nxceviri.core.qa.terms import canonical_terms, term_issues
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.userdict import UserDictionary
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import Status
from nxceviri.gui.issue_chips import ChipBar
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.spell_window import SpellWindow
from nxceviri.gui.theme import TOKENS, _qss

pytestmark = pytest.mark.gui

WORDS = [
    "merhaba",
    "oyun",
    "başlat",
    "yükle",
    "iyi",
    "ile",
    "tanış",
    "tuşu",
    "bas",
    "gümüş",
    "çamlar",
    "hoş",
    "geldin",
    "yine",
    "başla",
]
CODE = ControlCode(b"\x0e\x05", "Kod")


def _project() -> Project:
    p = Project.new()
    entries = (
        TextEntry("a", 0, "Start game", ()),
        TextEntry("b", 1, "Meet Elara", ()),
        TextEntry("c", 2, "Press ⟦1⟧ Start", (CODE,)),
        TextEntry("d", 3, "Start again", ()),
        TextEntry("e", 4, "Silver Pines", ()),
        TextEntry("f", 5, "Welcome to Silver Pines", ()),
    )
    p.import_texts([ImportedFile("Menu.tsv", "0100", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [
            (rows["a"].id, "Oyun başlatt"),
            (rows["b"].id, "Elara ile tanış"),
            (rows["d"].id, "Yine başlatt"),
            (rows["e"].id, "Gümüş Çamlar"),
            (rows["f"].id, "Silver Pines'a hoş geldin"),
        ],
        machine=True,
    )
    p.set_translations([(rows["c"].id, "Başlatt ⟦1⟧ tuşu")], status=Status.APPROVED)
    p.set_glossary([GlossaryTerm("Elara", "Elara")])
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w.user_dictionary = UserDictionary(tmp_path / "yazim.txt")
    w.spell = SpellChecker(BloomFilter.build(WORDS, error_rate=0.0001), w.user_dictionary.words())
    w._replace_project(_project())
    w.show()
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _spell_window(window: MainWindow) -> SpellWindow:
    window.menu_actions["tools.spell_check"].trigger()
    win = window._spell_window
    assert win is not None
    return win


def _words(win: SpellWindow) -> list[str]:
    return [it.text() for r in range(win.table.rowCount()) if (it := win.table.item(r, 0)) is not None]


def _select_word(win: SpellWindow, word: str) -> None:
    win.table.clearSelection()
    for r in range(win.table.rowCount()):
        item = win.table.item(r, 0)
        if item is not None and item.text() == word:
            item.setSelected(True)


def _translations(window: MainWindow) -> dict[str, str]:
    return {r.key: r.translation for r in window.project.translation_rows()}


# --- Araçlar → Yazım Denetimi ----------------------------------------------------------------


def test_menu_item_has_f7_and_sits_above_dictionary(window: MainWindow) -> None:
    action = window.menu_actions["tools.spell_check"]
    assert action.text() == "Yazım Denetimi…"
    assert action.shortcut().toString() == "F7"
    menu = next(a.menu() for a in window.menuBar().actions() if a.menu() and a.text() == "&Araçlar")
    assert isinstance(menu, QMenu)
    items = menu.actions()
    assert items.index(action) + 1 == items.index(window.menu_actions["tools.spell_dictionary"])
    assert action.isEnabled()


def test_menu_item_disabled_without_spell_checker_or_rows(qtbot: QtBot, window: MainWindow) -> None:
    window.spell = None
    window.update_menu_state()
    assert not window.menu_actions["tools.spell_check"].isEnabled()
    window.spell = SpellChecker(BloomFilter.build(WORDS, error_rate=0.0001), frozenset())
    window.update_menu_state()
    assert window.menu_actions["tools.spell_check"].isEnabled()
    window._replace_project(Project.new())
    window.update_menu_state()
    assert not window.menu_actions["tools.spell_check"].isEnabled()


def test_window_lists_unknown_words_and_is_single_instance(window: MainWindow) -> None:
    win = _spell_window(window)
    assert not win.isModal()
    assert win.isVisible()
    assert _words(win) == ["başlatt"]  # "Elara" sözlükte, "Silver" ve "Pines" kaynakta; kodlar atlanır
    window.menu_actions["tools.spell_check"].trigger()
    assert window._spell_window is win


def test_window_preview_is_short_translation(window: MainWindow) -> None:
    win = _spell_window(window)
    _select_word(win, "başlatt")
    previews = [win.rows_list.item(i).text() for i in range(win.rows_list.count())]
    assert "Oyun başlatt" in previews
    assert len(previews) == 3


def test_show_row_opens_it_in_translate(window: MainWindow) -> None:
    win = _spell_window(window)
    row = next(r for r in window.project.translation_rows() if r.key == "b")
    win.show_row.emit(row.id)
    assert window.nav.currentRow() == 2
    current = window.translate_page.current_row()
    assert current is not None
    assert current.id == row.id


def test_window_refreshes_after_row_change(qtbot: QtBot, window: MainWindow) -> None:
    win = _spell_window(window)
    row = next(r for r in window.project.translation_rows() if r.key == "b")
    rows = window._commit_translations([(row.id, "Elara ile kzmplt")])
    window.translate_page.model.update_rows(rows)
    qtbot.waitUntil(lambda: "kzmplt" in _words(win), timeout=3000)


# --- yoksay / ekle ---------------------------------------------------------------------------


def test_ignore_persists_and_silences_live_and_qa(qtbot: QtBot, window: MainWindow) -> None:
    win = _spell_window(window)
    window.run_checks()
    assert any(i.kind == "spelling" for i in window.qa_page.model.issues)
    _select_word(win, "başlatt")
    win.ignore_button.click()
    assert json.loads(window.project.setting("spell_ignored")) == ["başlatt"]
    assert _words(win) == []
    window.run_checks()
    assert not any(i.kind == "spelling" for i in window.qa_page.model.issues)
    row = next(r for r in window.translate_page.model.rows if r.key == "a")
    assert not [i for i in window.translate_page.model.live.check(row) if i.kind == "spelling"]


def test_live_context_spell_ignored(window: MainWindow) -> None:
    checker = LiveChecker()
    spell = SpellChecker(BloomFilter.build(WORDS, error_rate=0.0001), frozenset())
    row = next(r for r in window.translate_page.model.rows if r.key == "a")
    checker.set_context(LiveContext(spell=spell))
    assert [i for i in checker.check(row) if i.kind == "spelling"]
    checker.set_context(LiveContext(spell=spell, spell_ignored=frozenset({"başlatt"})))
    assert not [i for i in checker.check(row) if i.kind == "spelling"]


def test_broken_ignore_setting_is_empty_and_logged(window: MainWindow, caplog: pytest.LogCaptureFixture) -> None:
    window.project.set_setting("spell_ignored", "{bozuk")
    with caplog.at_level(logging.WARNING):
        win = _spell_window(window)
    assert _words(win) == ["başlatt"]
    assert any("spell_ignored" in r.getMessage() for r in caplog.records)
    window.project.set_setting("spell_ignored", json.dumps({"a": 1}))
    assert window._spell_ignored() == []


def test_add_to_dictionary_removes_word(window: MainWindow, tmp_path: Path) -> None:
    win = _spell_window(window)
    _select_word(win, "başlatt")
    win.add_button.click()
    assert UserDictionary(tmp_path / "yazim.txt").words() == frozenset({"başlatt"})
    assert _words(win) == []


# --- hepsini değiştir ------------------------------------------------------------------------


def test_replace_all_is_one_undoable_job_and_keeps_codes_and_approval(window: MainWindow) -> None:
    win = _spell_window(window)
    _select_word(win, "başlatt")
    win.replace_edit.setText("başla")
    win.replace_button.click()
    after = _translations(window)
    assert after["a"] == "Oyun başla"
    assert after["d"] == "Yine başla"
    assert after["c"] == "Başla ⟦1⟧ tuşu"  # büyük harf biçimi ve kontrol kodu korunur
    rows = {r.key: r for r in window.project.translation_rows()}
    assert rows["c"].status == Status.APPROVED
    assert rows["a"].status != Status.APPROVED
    assert "3 satırda değiştirildi" in window.statusBar().currentMessage()
    assert _words(win) == []
    window.undo_last()
    assert _translations(window)["a"] == "Oyun başlatt"
    assert _translations(window)["c"] == "Başlatt ⟦1⟧ tuşu"
    assert _translations(window)["d"] == "Yine başlatt"


# --- Terim değil -----------------------------------------------------------------------------


def _term_rows() -> list[TranslationRow]:
    return [
        TranslationRow(1, "f", "k1", "Silver Pines", "Gümüş Çamlar", "machine", "", (), None),
        TranslationRow(2, "f", "k2", "Welcome to Silver Pines", "Gümüş Çam'a hoş geldin", "machine", "", (), None),
    ]


def test_term_issue_carries_phrase() -> None:
    rows = _term_rows()
    issues = term_issues(rows, canonical_terms(rows, []))
    assert [i.words for i in issues] == [("Silver Pines",)]


def test_term_is_not_a_live_kind() -> None:
    assert "term" not in LIVE_KINDS


def test_not_term_menu_item_emits_phrases(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.resize(1400, 800)
    page.show()
    rows = _term_rows()
    issues = [
        QaIssue(2, "k2", "term", "warning", "terim", ("Silver Pines",)),
        QaIssue(1, "k1", "spaces", "warning", "b"),
    ]
    page.show_issues(issues, rows)

    def select_kind(kind: str) -> None:
        for r in range(page.proxy.rowCount()):
            if page.model.issues[page.proxy.mapToSource(page.proxy.index(r, 0)).row()].kind == kind:
                page.table.selectRow(r)

    select_kind("spaces")
    menu = page.context_menu()
    assert "Terim değil" not in [a.text() for a in menu.actions()]  # seçili bulgu terim değil
    select_kind("term")
    menu = page.context_menu()
    action = next(a for a in menu.actions() if a.text() == "Terim değil")
    with qtbot.waitSignal(page.not_term_requested) as sig:
        action.trigger()
    assert sig.args == [["Silver Pines"]]


def test_not_term_persists_and_clears_finding(window: MainWindow) -> None:
    window.nav.setCurrentRow(STEP_QA)
    window.run_checks()
    page = window.qa_page
    assert [i.words for i in page.model.issues if i.kind == "term"] == [("Silver Pines",)]
    page.not_term_requested.emit(["Silver Pines"])
    assert json.loads(window.project.setting("terms_ignored")) == ["Silver Pines"]
    assert not [i for i in page.model.issues if i.kind == "term"]
    page.not_term_requested.emit(["Silver Pines"])  # tekrar eklemek listeyi çoğaltmaz
    assert json.loads(window.project.setting("terms_ignored")) == ["Silver Pines"]


def test_broken_terms_ignored_setting(window: MainWindow, caplog: pytest.LogCaptureFixture) -> None:
    window.project.set_setting("terms_ignored", "değil json")
    with caplog.at_level(logging.WARNING):
        assert window._terms_ignored() == []
    assert any("terms_ignored" in r.getMessage() for r in caplog.records)


# --- çip stili -------------------------------------------------------------------------------


def test_chips_use_chip_role_and_theme_styles_it(qtbot: QtBot) -> None:
    bar = ChipBar()
    qtbot.addWidget(bar)
    assert all(isinstance(c, QAbstractButton) and c.property("role") == "chip" for c in bar.chips.values())
    for tokens in TOKENS.values():
        sheet = _qss(tokens)
        assert 'QToolButton[role="chip"]' in sheet
        assert 'QToolButton[role="chip"]:checked' in sheet
