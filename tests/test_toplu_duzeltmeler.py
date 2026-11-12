"""Toplu düzeltmeler: denetim bildirimi düzeyi ve proje değişince Kontrol Et'in sıfırlanması."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import MemoryStore
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.notify import LEVEL_INFO

pytestmark = pytest.mark.gui

LINES = [("a", "Start Game"), ("b", "Hello "), ("c", "Go on and on")]


def _project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(LINES))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [(rows["a"].id, "Oyunu Başlat."), (rows["b"].id, "Merhaba"), (rows["c"].id, "Devam et ve ve bitir")],
        machine=True,
    )
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    w.nav.setCurrentRow(STEP_QA)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _check(qtbot: QtBot, w: MainWindow) -> None:
    w.qa_page.check_button.click()
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)


def test_check_with_findings_is_informational_not_error(qtbot: QtBot, window: MainWindow) -> None:
    _check(qtbot, window)
    assert window.qa_page.model.issues  # bulgu var
    notice = next(n for n in window.notifier.history if n.title == "Denetim bitti")
    assert notice.level == LEVEL_INFO
    assert "hata" in notice.text
    assert "uyarı" in notice.text
    assert [a.label for a in notice.actions] == ["Sorunları Gör"]


def test_replacing_project_resets_qa_page(qtbot: QtBot, window: MainWindow) -> None:
    _check(qtbot, window)
    page = window.qa_page
    assert page.model.issues
    assert page.summary.text() != "Henüz denetlenmedi."
    window._replace_project(Project.new())
    assert page.model.issues == []
    assert page.proxy.rowCount() == 0
    assert page.summary.text() == "Henüz denetlenmedi."
    assert page.summary_icon.isHidden()
    assert not any(page.fix_counts.values())
    assert window._qa_count is None
    assert not window._qa_errors
