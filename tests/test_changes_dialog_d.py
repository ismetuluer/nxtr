"""Değişiklikler penceresi (D aşaması): uzun listede kaydırma, "Yeni" hücresini yerinde düzenleme, bağlam ipucu."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.project import Change
from nxceviri.gui.changes_dialog import CONTEXT_KEY, NEW_TEXT_ROLE, ChangesDialog

pytestmark = pytest.mark.gui

LONG = " ".join(["Uzun bir cümle ki tek satıra sığmaz"] * 6)


def _changes(n: int) -> list[Change]:
    return [
        Change(i + 1, f"Konusma/{i}", f"{LONG} {i}", f"Eski {i}", "machine", "", f"Yeni {LONG} {i}", "retranslate", "")
        for i in range(n)
    ]


def _dialog(qtbot: QtBot, n: int = 3, **kwargs: object) -> ChangesDialog:
    dialog = ChangesDialog(None, "Yeniden çeviri: değişiklikler", _changes(n), **kwargs)  # type: ignore[arg-type]
    qtbot.addWidget(dialog)
    dialog.resize(1000, 600)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


def test_long_list_still_wraps_visible_rows(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot, n=4000)  # eskiden 1.500 satırdan sonra hiç ölçülmüyordu
    one_line = dialog.table.fontMetrics().height() + 12
    qtbot.waitUntil(lambda: dialog.table.rowHeight(0) > one_line, timeout=3000)
    last = dialog.table.rowCount() - 1
    dialog.table.scrollToBottom()
    qtbot.waitUntil(lambda: dialog.table.rowHeight(last) > one_line, timeout=3000)


def test_new_cell_is_editable_and_saved_through_callback(qtbot: QtBot) -> None:
    saved: list[tuple[int, str]] = []
    dialog = _dialog(qtbot, edit_fn=lambda entry_id, text: saved.append((entry_id, text)))
    item = dialog.table.item(0, 4)
    assert item is not None
    assert dialog.table.model().flags(dialog.table.model().index(0, 4)) & dialog.EDITABLE
    assert dialog.table.editTriggers() & dialog.table.EditTrigger.DoubleClicked
    item.setData(NEW_TEXT_ROLE, "Elle düzeltildi")
    assert saved == [(1, "Elle düzeltildi")]
    assert "düzeltildi" in item.text()  # hücre yeni metinle yeniden çizildi


def test_rejected_edit_restores_cell_and_explains(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot, edit_fn=lambda _entry_id, _text: "Kontrol kodu eksik.")
    item = dialog.table.item(0, 4)
    assert item is not None
    item.setData(NEW_TEXT_ROLE, "bozuk")
    assert item.data(NEW_TEXT_ROLE) == f"Yeni {LONG} 0"
    assert "Kontrol kodu eksik." in dialog.status.text.text()


def test_without_callback_cells_are_read_only(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    assert dialog.table.editTriggers() == dialog.table.EditTrigger.NoEditTriggers


def test_context_tooltip_is_optional_and_remembered(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
    dialog = _dialog(qtbot, context_fn=lambda entry_id: f"önceki/sonraki satırlar {entry_id}", settings=settings)
    assert dialog.context_box.isVisible()
    assert not dialog.context_box.isChecked()  # varsayılan kapalı
    assert dialog.context_tip(0) == ""
    dialog.context_box.setChecked(True)
    assert "önceki/sonraki satırlar 1" in dialog.context_tip(0)
    assert settings.value(CONTEXT_KEY) == "1"
    again = _dialog(qtbot, context_fn=lambda _e: "x", settings=settings)
    assert again.context_box.isChecked()


def test_no_context_option_without_provider(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    assert not dialog.context_box.isVisible()
