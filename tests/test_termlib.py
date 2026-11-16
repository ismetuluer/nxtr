"""Terminoloji kitaplığı: adlandırılmış listeler (AppData), birleştirme ve pencereden kullanım."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.termlib import add_missing, delete_list, list_names, load_list, save_list, termlib_dir


def test_lists_live_in_app_data() -> None:
    assert termlib_dir().name == "terminoloji"
    assert termlib_dir().parent.name == "NXCeviri"


def test_save_load_list_and_delete() -> None:
    assert list_names() == []
    save_list(
        "Ana seri", [GlossaryTerm("Rowan", "Rowan", "ana karakter"), GlossaryTerm("Shadow Arm", "Gölge Silahı", "")]
    )
    save_list("Seri/Bölüm?", [GlossaryTerm("Coin", "Sikke", "")])  # dosya adına uygun olmayan karakterler
    assert list_names() == ["Ana seri", "Seri/Bölüm?"]
    assert load_list("Ana seri")[1] == GlossaryTerm("Shadow Arm", "Gölge Silahı", "")
    save_list("Ana seri", [GlossaryTerm("Darian", "Darian", "")])  # aynı ad: yerine yazılır
    assert [t.term for t in load_list("Ana seri")] == ["Darian"]
    delete_list("Seri/Bölüm?")
    assert list_names() == ["Ana seri"]


def test_broken_list_file_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    termlib_dir().mkdir(parents=True, exist_ok=True)
    (termlib_dir() / "bozuk.json").write_text("{", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert list_names() == []
    assert "Terminoloji listesi" in caplog.text


def test_add_missing_keeps_project_translation() -> None:
    project = [GlossaryTerm("Rowan", "Rowan", ""), GlossaryTerm("Shadow Arm", "Karanlık Silahı", "")]
    incoming = [GlossaryTerm("shadow arm", "Gölge Silahı", ""), GlossaryTerm("Darian", "Darian", "")]
    merged, added, kept = add_missing(project, incoming)
    assert [t.term for t in merged] == ["Rowan", "Shadow Arm", "Darian"]
    assert merged[1].translation == "Karanlık Silahı"  # projedeki karşılık korunur
    assert (added, kept) == (1, 1)


def test_dialog_library_saves_and_adds(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    from nxceviri.gui.machine_dialogs import GlossaryDialog

    dialog = GlossaryDialog(None, [GlossaryTerm("Rowan", "Rowan", "")])
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: ("Ana seri", True))
    dialog.library.save_current()
    assert load_list("Ana seri") == [GlossaryTerm("Rowan", "Rowan", "")]

    other = GlossaryDialog(None, [GlossaryTerm("Kael", "Kael", "")])
    qtbot.addWidget(other)
    other.library.add_from("Ana seri")
    assert [t.term for t in other.terms()] == ["Kael", "Rowan"]
    assert "1 terim eklendi" in other.banner.text.text()
    names = [a.text() for a in other.library.menu_widget.actions() if a.menu() is not None]
    assert names == ["Kitaplıktan Ekle", "Listeyi Sil"]
