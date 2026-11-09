"""Talimat kitaplığı (AppData) ve Otomatik Çeviri penceresindeki grup/anahtar deseni kapsamı."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.instructions import (
    KIND_REVISE,
    KIND_TRANSLATE,
    SavedInstruction,
    delete_instruction,
    library_path,
    load_library,
    save_instruction,
)
from nxceviri.core.translate.runner import ACTION_TRANSLATE
from nxceviri.core.translate.status import Status
from nxceviri.gui.machine_dialogs import SCOPE_ALL, SCOPE_PATTERN, MachineDialog, rows_matching


def test_library_lives_in_app_data() -> None:
    assert library_path().name == "talimatlar.json"
    assert library_path().parent.name == "NXCeviri"


def test_save_replace_and_delete(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    assert load_library(path) == []
    save_instruction(SavedInstruction("Eski dil", KIND_TRANSLATE, "Eski Türkçe karşılıklar kullan."), path)
    save_instruction(SavedInstruction("Kısa", KIND_REVISE, "Kısalt."), path)
    save_instruction(SavedInstruction("Eski dil", KIND_TRANSLATE, "Osmanlıca sözcükler."), path)  # aynı ad: değişir
    items = load_library(path)
    assert [(i.name, i.kind, i.text) for i in items] == [
        ("Eski dil", KIND_TRANSLATE, "Osmanlıca sözcükler."),
        ("Kısa", KIND_REVISE, "Kısalt."),
    ]
    delete_instruction("Kısa", KIND_REVISE, path)
    assert [i.name for i in load_library(path)] == ["Eski dil"]


def test_broken_library_is_empty_and_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "t.json"
    path.write_text("{bozuk", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert load_library(path) == []
    assert "Talimat kitaplığı" in caplog.text


def _row(i: int, file: str, key: str, context: str = "") -> TranslationRow:
    return TranslationRow(i, file, key, f"S{i}", "", Status.UNTRANSLATED, "", (), None, context)


def test_rows_matching_group_or_key() -> None:
    rows = [
        _row(1, "a.tsv", "menu_start", "UI/Menu/menu_start"),
        _row(2, "a.tsv", "chapter1_kids_01", "Conversations/Chapter1/kids_01"),
        _row(3, "b.tsv", "MENU_quit", "UI/Menu/MENU_quit"),
    ]
    assert [r.id for r in rows_matching(rows, "menu_*")] == [1, 3]  # anahtar, büyük/küçük harf duyarsız
    assert [r.id for r in rows_matching(rows, "*kids*")] == [2]
    assert rows_matching(rows, "") == []


def _dialog(qtbot: QtBot, rows: list[TranslationRow]) -> MachineDialog:
    dialog = MachineDialog(
        None,
        provider="ollama",
        base_url="",
        model="gemma4:12b",
        notes="",
        source_language="en",
        secrets=MemoryStore(),
        scopes={SCOPE_ALL: rows},
        action=ACTION_TRANSLATE,
    )
    qtbot.addWidget(dialog)
    return dialog


def test_pattern_scope_counts_and_carries_pattern(qtbot: QtBot) -> None:
    rows = [_row(1, "a.tsv", "menu_start"), _row(2, "a.tsv", "talk_01"), _row(3, "a.tsv", "menu_quit")]
    dialog = _dialog(qtbot, rows)
    dialog.scope.setCurrentIndex(dialog.scope.findData(SCOPE_PATTERN))
    assert dialog.pattern.isVisibleTo(dialog)
    dialog.pattern.setText("menu_*")
    assert [r.id for r in dialog.target()] == [1, 3]
    assert "2 satır" in dialog.count.text()
    assert dialog.settings().pattern == "menu_*"
    dialog.pattern.setText("yok_*")
    assert not dialog.start.isEnabled()


def test_library_menu_saves_and_uses_instruction(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    dialog = _dialog(qtbot, [_row(1, "a.tsv", "k")])
    dialog.instruction.setPlainText("Eski Türkçe karşılıklar kullan.")
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: ("Eski dil", True))
    dialog.save_to_library()
    assert [i.name for i in load_library()] == ["Eski dil"]
    dialog.instruction.setPlainText("")
    dialog.use_saved("Eski dil")
    assert dialog.instruction.toPlainText() == "Eski Türkçe karşılıklar kullan."
    names = [a.text() for a in dialog.library_menu.actions() if a.text()]
    assert "Eski dil" in names
