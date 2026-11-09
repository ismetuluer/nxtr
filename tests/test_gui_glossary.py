"""Arayüz: sözlük penceresinde XLSX içe/dışa aktarma, bilgi notları (lore) ve Ollama ile terim önerisi."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialog, QFileDialog
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.csvio import table_xlsx
from nxceviri.core.translate.glossary_io import read_glossary_xlsx
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.terms import TermSuggestion
from nxceviri.gui import machine_dialogs
from nxceviri.gui.machine_dialogs import GlossaryDialog, TermSuggestionsDialog
from nxceviri.gui.main_window import MainWindow
from tests.fake_ollama import FakeOllama

pytestmark = pytest.mark.gui

LINES = [
    "Welcome to Silver Pines.",
    "The Sheriff waits at the Old Mill.",
    "Ask the Sheriff about Silver Pines.",
    "Is the Old Mill open?",
]


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    p = Project.new()
    entries = tuple(TextEntry(f"s{i}", i, s, ()) for i, s in enumerate(LINES))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    p.set_glossary([GlossaryTerm("Sheriff", "Şerif")])
    w._replace_project(p)
    w.show()
    yield w
    if w.task is not None:
        w.task.cancel()
        w.task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def test_dialog_imports_exports_and_keeps_lore(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lore = GlossaryTerm("Elara", "", "Kahramanın ablası.")
    dialog = GlossaryDialog(None, [GlossaryTerm("Sheriff", "Şerif", "unvan"), lore], tmp_path)
    qtbot.addWidget(dialog)
    source = tmp_path / "gelen.xlsx"
    source.write_bytes(table_xlsx(["terim", "çeviri"], [["sheriff", "Polis Şefi"], ["Old Mill", "Eski Değirmen"]]))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(source), ""))
    dialog.import_action.trigger()
    assert dialog.terms() == [
        GlossaryTerm("Sheriff", "Polis Şefi", "unvan"),
        lore,
        GlossaryTerm("Old Mill", "Eski Değirmen"),
    ]
    assert "1 terim eklendi, 1 terim güncellendi" in dialog.banner.text.text()

    target = tmp_path / "giden"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    dialog.export_action.trigger()
    assert read_glossary_xlsx(tmp_path / "giden.xlsx") == [
        GlossaryTerm("Sheriff", "Polis Şefi"),
        GlossaryTerm("Old Mill", "Eski Değirmen"),
    ]
    assert "1 bilgi notu" in dialog.banner.text.text()

    broken = tmp_path / "bozuk.xlsx"
    broken.write_bytes(b"bozuk")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(broken), ""))
    dialog.import_action.trigger()
    assert "bozuk.xlsx" in dialog.banner.text.text()
    assert len(dialog.terms()) == 3  # bozuk dosya sözlüğü değiştirmez


def test_suggestions_dialog_returns_checked_and_edited_terms(qtbot: QtBot) -> None:
    dialog = TermSuggestionsDialog(
        None, [TermSuggestion("Silver Pines", "Silver Pines", "yer adı", 3), TermSuggestion("Mara", "Mara", "", 2)]
    )
    qtbot.addWidget(dialog)
    item = dialog.table.item(1, 0)
    assert item is not None
    item.setCheckState(Qt.CheckState.Unchecked)
    translation = dialog.table.item(0, 1)
    assert translation is not None
    translation.setText("Gümüş Çamlar")
    assert dialog.selected() == [GlossaryTerm("Silver Pines", "Gümüş Çamlar", "yer adı")]


def test_suggest_terms_end_to_end(qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeOllama()
    window.provider_factory = lambda s: server.provider(s.model)
    window.settings.setValue("translate/provider", "ollama")
    window.settings.setValue("ollama/model", "gemma4:12b")
    shown: list[list[str]] = []

    def accept(self: TermSuggestionsDialog) -> int:
        shown.append([self.table.item(r, 0).text() for r in range(self.table.rowCount())])  # type: ignore[union-attr]
        return QDialog.DialogCode.Accepted.value

    monkeypatch.setattr(machine_dialogs.TermSuggestionsDialog, "exec", accept)
    window.suggest_glossary_terms()
    qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
    assert shown == [["Silver Pines", "Old Mill"]]  # sözlükte olan Sheriff aday değil
    assert window.project.glossary() == [
        GlossaryTerm("Sheriff", "Şerif"),
        GlossaryTerm("Silver Pines", "tr-Silver Pines", "öneri notu"),
        GlossaryTerm("Old Mill", "tr-Old Mill", "öneri notu"),
    ]
    assert "2 terim eklendi" in window.translate_page.notice_text


def test_suggest_terms_needs_ollama_model(window: MainWindow) -> None:
    window.settings.setValue("translate/provider", "deepl")
    window.suggest_glossary_terms()
    assert window.task is None
    assert "Ollama gerekli" in window.translate_page.notice_text
