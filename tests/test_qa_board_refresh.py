"""Kontrol Et: düzeltilen satırın bulgusu, düzeltme hangi ekrandan yapılırsa yapılsın listeden düşer."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.secrets import MemoryStore
from nxceviri.gui.main_window import STEP_QA, MainWindow

pytestmark = pytest.mark.gui

#: (anahtar, orijinal, çeviri) — çevirinin sonunda fazladan boşluk: boşluk uyarısı
ROWS = [("a", "Book", "kitap "), ("b", "Pen", "kalem "), ("c", "Cup", "fincan")]


def _project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(key, i, source, ()) for i, (key, source, _t) in enumerate(ROWS))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    by_key = {r.key: r for r in p.translation_rows()}
    for key, _source, text in ROWS:
        p.set_translations([(by_key[key].id, text)], machine=True)
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = MainWindow(QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat))
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    w.nav.setCurrentRow(STEP_QA)
    w.qa_page.check_button.click()
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _row(w: MainWindow, key: str) -> TranslationRow:
    return next(r for r in w.project.translation_rows() if r.key == key)


def _flagged(w: MainWindow, key: str) -> bool:
    row_id = _row(w, key).id
    return any(i.row_id == row_id for i in w.qa_page.active_issues())


def test_board_edit_drops_finding(window: MainWindow) -> None:
    assert _flagged(window, "a")
    window._edit_from_issues(_row(window, "a").id, "kitap")
    assert not _flagged(window, "a")
    assert _flagged(window, "b")


def test_translate_table_edit_drops_finding(window: MainWindow, qtbot: QtBot) -> None:
    assert _flagged(window, "a")
    assert window.translate_page.model.apply([(_row(window, "a").id, "kitap")])
    qtbot.waitUntil(lambda: not _flagged(window, "a"), timeout=5000)
    assert _flagged(window, "b")


def test_undo_brings_finding_back(window: MainWindow, qtbot: QtBot) -> None:
    window._edit_from_issues(_row(window, "a").id, "kitap")
    assert not _flagged(window, "a")
    window.undo_last()
    qtbot.waitUntil(lambda: _flagged(window, "a"), timeout=5000)
