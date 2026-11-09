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
        "DMC serisi", [GlossaryTerm("Dante", "Dante", "ana karakter"), GlossaryTerm("Devil Arm", "Şeytan Silahı", "")]
    )
    save_list("Zelda/Hyrule?", [GlossaryTerm("Rupee", "Rupi", "")])  # dosya adına uygun olmayan karakterler
    assert list_names() == ["DMC serisi", "Zelda/Hyrule?"]
    assert load_list("DMC serisi")[1] == GlossaryTerm("Devil Arm", "Şeytan Silahı", "")
    save_list("DMC serisi", [GlossaryTerm("Vergil", "Vergil", "")])  # aynı ad: yerine yazılır
    assert [t.term for t in load_list("DMC serisi")] == ["Vergil"]
    delete_list("Zelda/Hyrule?")
    assert list_names() == ["DMC serisi"]


def test_broken_list_file_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    termlib_dir().mkdir(parents=True, exist_ok=True)
    (termlib_dir() / "bozuk.json").write_text("{", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert list_names() == []
    assert "Terminoloji listesi" in caplog.text


def test_add_missing_keeps_project_translation() -> None:
    project = [GlossaryTerm("Dante", "Dante", ""), GlossaryTerm("Devil Arm", "İblis Silahı", "")]
    incoming = [GlossaryTerm("devil arm", "Şeytan Silahı", ""), GlossaryTerm("Vergil", "Vergil", "")]
    merged, added, kept = add_missing(project, incoming)
    assert [t.term for t in merged] == ["Dante", "Devil Arm", "Vergil"]
    assert merged[1].translation == "İblis Silahı"  # projedeki karşılık korunur
    assert (added, kept) == (1, 1)


def test_dialog_library_saves_and_adds(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    from nxceviri.gui.machine_dialogs import GlossaryDialog

    dialog = GlossaryDialog(None, [GlossaryTerm("Dante", "Dante", "")])
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: ("DMC serisi", True))
    dialog.library.save_current()
    assert load_list("DMC serisi") == [GlossaryTerm("Dante", "Dante", "")]

    other = GlossaryDialog(None, [GlossaryTerm("Link", "Link", "")])
    qtbot.addWidget(other)
    other.library.add_from("DMC serisi")
    assert [t.term for t in other.terms()] == ["Link", "Dante"]
    assert "1 terim eklendi" in other.banner.text.text()
    names = [a.text() for a in other.library.menu_widget.actions() if a.menu() is not None]
    assert names == ["Kitaplıktan Ekle", "Listeyi Sil"]
