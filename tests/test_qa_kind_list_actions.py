"""Kontrol Et: tür listesinde "Yok sayılanlar" tıklaması, tür sağ tık menüsü, denetim sırasında özet."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.gui.issue_kinds import IGNORED_KIND
from nxceviri.gui.main_window import STEP_QA, MainWindow

pytestmark = pytest.mark.gui

WORDS = ["burada", "gitti", "kitap"]
ROWS = [("a", "Book ", "kitap "), ("b", "Go", "xyzzy burada"), ("c", "Run", "gitti")]


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    p = Project.new()
    entries = tuple(TextEntry(k, i, s, ()) for i, (k, s, _t) in enumerate(ROWS))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    by_key = {r.key: r for r in p.translation_rows()}
    for key, _s, text in ROWS:
        p.set_translations([(by_key[key].id, text)], machine=True)
    w = MainWindow(QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat))
    w.secrets = MemoryStore()
    w.spell = SpellChecker(BloomFilter.build(WORDS, error_rate=0.00001))
    w._replace_project(p)
    w.show()
    w.nav.setCurrentRow(STEP_QA)
    w.qa_page.check_button.click()
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_clicking_ignored_entry_lists_ignored_info_findings(window: MainWindow, qtbot: QtBot) -> None:
    page = window.qa_page
    spelling = [i for i in page.active_issues() if i.kind == "spelling"]
    assert spelling
    window.ignore_issues([(i.row_id, i.kind) for i in spelling])
    kl = page.kind_list
    qtbot.mouseClick(
        kl.viewport(), Qt.MouseButton.LeftButton, pos=kl.visualItemRect(kl.kind_item(IGNORED_KIND)).center()
    )
    assert page._ignored_view
    assert page.proxy.rowCount() == len(spelling)
    qtbot.mouseClick(kl.viewport(), Qt.MouseButton.LeftButton, pos=kl.visualItemRect(kl.all_item).center())
    assert all(i.kind != "spelling" for i in page.model.issues)


def test_summary_is_not_checking_text_while_checking(window: MainWindow) -> None:
    page = window.qa_page
    page.mark_checking()
    assert "Denetleniyor" not in page.summary.text()
    page.stop_checking()
    assert page.summary.text()


def test_kind_menu_exports_that_kinds_findings(window: MainWindow) -> None:
    page = window.qa_page
    asked: list[tuple[frozenset[str], int]] = []
    page.export_findings_requested.disconnect(window.export_findings)  # gerçek iletişim kutusu açılmasın
    page.export_findings_requested.connect(
        lambda: asked.append((page.kind_list.selected_kinds(), len(page.visible_findings())))
    )
    menu = page.kind_context_menu(page.kind_list.kind_item("spelling"))
    assert menu is not None
    next(a for a in menu.actions() if a.text() == "Bu gruptaki bulguları dışa aktar…").trigger()
    expected = sum(1 for i in page.model.issues if i.kind == "spelling")
    assert asked == [(frozenset({"spelling"}), expected)]
    all_menu = page.kind_context_menu(page.kind_list.all_item)
    assert all_menu is not None
    assert [a.text() for a in all_menu.actions()] == ["Tüm bulguları dışa aktar…"]
