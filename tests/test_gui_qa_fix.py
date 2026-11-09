"""Arayüz: Kontrol Et → Satır denetimi düzeltmeleri (tür seçimi, kapsam, rapor, ayar kalıcılığı)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractButton
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.status import Status
from nxceviri.gui.main_window import STEP_QA, MainWindow

pytestmark = pytest.mark.gui

LINES = [
    ("a", "Start Game"),
    ("b", "Hello "),
    ("c", "Go on and on"),
    ("d", "Hello "),
]


def _project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(LINES))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [(rows["a"].id, "Oyunu Başlat."), (rows["b"].id, "Merhaba"), (rows["c"].id, "Devam et ve ve bitir")],
        machine=True,
    )
    p.set_translations([(rows["d"].id, "Selam")])  # onaylı; sondaki boşluk eksik ama dokunulmaz
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    w.nav.setCurrentRow(STEP_QA)
    w.qa_page.check_button.click()
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)  # Denetle arka planda çalışır
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _rows(w: MainWindow) -> dict[str, TranslationRow]:
    return {r.key: r for r in w.project.translation_rows()}


def _only(w: MainWindow, *kinds: str) -> None:
    page = w.qa_page
    page.fix_none.click()
    for kind in kinds:
        page.fix_boxes[kind].setChecked(True)


def _select_issue_row(w: MainWindow, key: str) -> None:
    page = w.qa_page
    page.table.clearSelection()
    target = _rows(w)[key].id
    for r in range(page.proxy.rowCount()):
        if page.model.issues[page.proxy.mapToSource(page.proxy.index(r, 0)).row()].row_id == target:
            page.table.selectRow(r)
            return
    raise AssertionError(f"{key} için bulgu yok")


def test_counts_and_disabled_kinds(window: MainWindow) -> None:
    page = window.qa_page
    assert page.fix_counts["spaces"] == 2
    assert page.fix_counts["end_punctuation"] == 1
    assert page.fix_counts["repeated_word"] == 1
    assert page.fix_boxes["spaces"].text() == "Boşluk  2"
    assert page.fix_boxes["spaces"].isVisibleTo(page.fix_body)
    assert not page.fix_boxes["markup"].isVisibleTo(page.fix_body)  # bulgusu olmayan tür görünmez
    assert page.fix_button.text() == "Seçilenleri Düzelt"


def test_fix_selected_kinds_report_and_second_round(window: MainWindow) -> None:
    page = window.qa_page
    _only(window, "end_punctuation")
    page.fix_button.click()
    rows = _rows(window)
    assert rows["a"].translation == "Oyunu Başlat"
    assert rows["b"].translation == "Merhaba"  # seçilmeyen tür uygulanmadı
    assert rows["c"].translation == "Devam et ve ve bitir"
    assert page.fix_banner.text.text() == "1 satır düzeltildi."
    assert page.fix_banner.action_button.text() == "Raporu Gör"
    assert page.fix_counts["end_punctuation"] == 0  # denetim kendiliğinden yeniden çalıştı
    assert not page.fix_boxes["end_punctuation"].isVisibleTo(page.fix_body)
    assert page.fix_counts["spaces"] == 2

    page.fix_banner.action_button.click()
    dialog = window.changes_dialog
    assert dialog is not None
    assert dialog.table.rowCount() == 1
    header, cell = dialog.table.horizontalHeaderItem(5), dialog.table.item(0, 5)
    assert header is not None
    assert cell is not None
    assert (header.text(), cell.text()) == ("Düzeltme", "Sondaki noktalama")
    dialog.close()

    # Başka bir türü seçip yeniden düzelt: onaylı satıra dokunulmaz, not düşülür.
    _only(window, "spaces")
    page.fix_button.click()
    rows = _rows(window)
    assert rows["b"].translation == "Merhaba "
    assert rows["d"].translation == "Selam"
    assert rows["d"].status == Status.APPROVED
    assert "1 satır düzeltildi." in page.fix_banner.text.text()
    assert "1 satıra dokunulmadı" in page.fix_banner.text.text()


def test_fix_is_one_undoable_job(window: MainWindow) -> None:
    page = window.qa_page
    _only(window, "end_punctuation", "repeated_word")
    page.fix_button.click()
    rows = _rows(window)
    assert (rows["a"].translation, rows["c"].translation) == ("Oyunu Başlat", "Devam et ve bitir")
    window.undo_last()
    rows = _rows(window)
    assert (rows["a"].translation, rows["c"].translation) == ("Oyunu Başlat.", "Devam et ve ve bitir")


def test_selected_rows_scope(window: MainWindow) -> None:
    page = window.qa_page
    _select_issue_row(window, "c")
    assert page.scope_selected.isChecked()
    page.fix_button.click()
    rows = _rows(window)
    assert rows["c"].translation == "Devam et ve bitir"
    assert rows["a"].translation == "Oyunu Başlat."  # seçili olmayan satırlara dokunulmadı
    assert rows["b"].translation == "Merhaba"
    assert page.fix_banner.text.text() == "1 satır düzeltildi."


def test_no_kind_selected_disables_button(window: MainWindow) -> None:
    page = window.qa_page
    page.fix_none.click()
    assert not page.fix_button.isEnabled()
    page.fix_all.click()
    assert page.fix_button.isEnabled()


def test_selection_is_remembered(window: MainWindow) -> None:
    _only(window, "spaces", "markup")  # markup'ın bulgusu yok; yine de hatırlanır
    assert window.settings.value("qa/fix_kinds") == "markup,spaces"
    other = MainWindow(window.settings)
    try:
        assert other.qa_page.checked_fix_kinds() == ["markup", "spaces"]
    finally:
        other.dirty = False
        other.close()
        other.deleteLater()


def test_ollama_fix_is_gone(window: MainWindow) -> None:
    page = window.qa_page
    texts = [b.text() for b in page.findChildren(QAbstractButton)]
    texts += [a.text() for a in page.findChildren(QAction)]
    texts += [a.text() for a in page.context_menu().actions()]
    assert not [t for t in texts if "Otomatik Düzelt" in t or "Ollama" in t or "Programla" in t]
    assert not hasattr(window, "auto_fix")
    assert not hasattr(window, "program_fix")
    assert [a.text() for a in page.context_menu().actions()] == ["Yazım sözlüğünü aç…"]
