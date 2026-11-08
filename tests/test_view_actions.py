"""Görünüm durumu: semboller, hiza ve panel konumu eylemleri ve kalıcılığı."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.gui.view_actions import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    PANE_BOTTOM,
    PANE_RIGHT,
    ViewActions,
)


def make_settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "gorunum.ini"), QSettings.Format.IniFormat)


def test_defaults(qtbot: QtBot) -> None:
    actions = ViewActions()
    assert actions.symbols_on is False
    assert actions.align == ALIGN_LEFT
    assert actions.pane == PANE_BOTTOM
    assert actions.pane_actions[PANE_BOTTOM].isChecked()
    assert not actions.pane_actions[PANE_RIGHT].isChecked()
    assert actions.align_actions[ALIGN_LEFT].isChecked()


def test_align_is_exclusive_and_emits_once(qtbot: QtBot) -> None:
    actions = ViewActions()
    seen: list[str] = []
    actions.align_changed.connect(seen.append)
    actions.align_actions[ALIGN_CENTER].trigger()
    assert seen == [ALIGN_CENTER]
    assert actions.align == ALIGN_CENTER
    assert not actions.align_actions[ALIGN_LEFT].isChecked()
    actions.align_actions[ALIGN_CENTER].trigger()  # zaten seçili: yeniden yayınlanmaz
    assert seen == [ALIGN_CENTER]
    actions.align_actions[ALIGN_RIGHT].trigger()
    assert seen == [ALIGN_CENTER, ALIGN_RIGHT]


def test_pane_position_choice_and_toggle(qtbot: QtBot) -> None:
    actions = ViewActions()
    seen: list[str] = []
    shown: list[bool] = []
    actions.pane_changed.connect(seen.append)
    actions.pane_visible_changed.connect(shown.append)
    actions.pane_actions[PANE_RIGHT].trigger()  # altta → sağda
    assert seen == [PANE_RIGHT]
    assert actions.pane_actions[PANE_RIGHT].isChecked()
    assert not actions.pane_actions[PANE_BOTTOM].isChecked()
    actions.pane_actions[PANE_RIGHT].trigger()  # etkine tıklamak konumu bozmaz, paneli kapatmaz
    assert actions.pane == PANE_RIGHT
    assert actions.pane_visible
    assert shown == []
    actions.pane_toggle.trigger()  # Ctrl+J: kapat
    assert shown == [False]
    assert actions.pane == PANE_RIGHT  # konum korunur
    actions.pane_actions[PANE_BOTTOM].trigger()  # konum seçimi paneli de açar
    assert actions.pane_visible
    assert shown == [False, True]
    assert actions.pane_actions[PANE_BOTTOM].isChecked()


def test_symbols_toggle_emits(qtbot: QtBot) -> None:
    actions = ViewActions()
    seen: list[bool] = []
    actions.symbols_changed.connect(seen.append)
    actions.symbols.trigger()
    actions.symbols.trigger()
    assert seen == [True, False]
    assert actions.symbols_on is False


def test_settings_roundtrip(qtbot: QtBot, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    first = ViewActions()
    first.bind_settings(settings)
    first.symbols.trigger()
    first.align_actions[ALIGN_RIGHT].trigger()
    first.pane_actions[PANE_RIGHT].trigger()
    settings.sync()
    second = ViewActions()
    second.bind_settings(make_settings(tmp_path))
    assert second.symbols_on is True
    assert second.align == ALIGN_RIGHT
    assert second.pane == PANE_RIGHT
    assert second.align_actions[ALIGN_RIGHT].isChecked()
    assert second.pane_actions[PANE_RIGHT].isChecked()
    assert not second.pane_actions[PANE_BOTTOM].isChecked()


def test_pane_visibility_is_persisted(qtbot: QtBot, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    first = ViewActions()
    first.bind_settings(settings)
    first.pane_toggle.trigger()  # varsayılan açık → kapat
    second = ViewActions()
    second.bind_settings(make_settings(tmp_path))
    assert not second.pane_visible
    assert not second.pane_toggle.isChecked()
    assert second.pane == PANE_BOTTOM


def test_legacy_off_value_means_closed_bottom(qtbot: QtBot, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.setValue("translate/pane", "off")
    actions = ViewActions()
    actions.bind_settings(settings)
    assert actions.pane == PANE_BOTTOM
    assert not actions.pane_visible


def test_bad_settings_fall_back(qtbot: QtBot, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    settings = make_settings(tmp_path)
    settings.setValue("translate/align", "orta")
    settings.setValue("translate/pane", "kuzey")
    settings.setValue("translate/symbols", "x")
    actions = ViewActions()
    with caplog.at_level(logging.WARNING):
        actions.bind_settings(settings)
    assert actions.align == ALIGN_LEFT
    assert actions.pane == PANE_BOTTOM
    assert actions.symbols_on is False
    assert "orta" in caplog.text
    assert "kuzey" in caplog.text


def test_shortcuts_and_icons(qtbot: QtBot) -> None:
    actions = ViewActions()
    assert actions.symbols.shortcut().toString() == "Ctrl+Shift+8"
    assert [actions.align_actions[k].shortcut().toString() for k in (ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT)] == [
        "Ctrl+L",
        "Ctrl+E",
        "Ctrl+R",
    ]
    assert actions.pane_actions[PANE_BOTTOM].shortcut().toString() == "Ctrl+Alt+B"
    assert actions.pane_actions[PANE_RIGHT].shortcut().toString() == "Ctrl+Alt+R"
    assert actions.pane_toggle.shortcut().toString() == "Ctrl+J"
    every = [actions.symbols, actions.pane_toggle, *actions.align_actions.values(), *actions.pane_actions.values()]
    for action in every:
        assert not action.icon().isNull(), action.text()
        assert action.toolTip()


def test_load_does_not_emit(qtbot: QtBot, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.setValue("translate/symbols", "1")
    settings.setValue("translate/align", "center")
    settings.setValue("translate/pane", "right")
    actions = ViewActions()
    seen: list[object] = []
    actions.symbols_changed.connect(seen.append)
    actions.align_changed.connect(seen.append)
    actions.pane_changed.connect(seen.append)
    actions.load(settings)
    assert seen == []
    assert actions.symbols_on is True
    assert actions.align == ALIGN_CENTER
    assert actions.pane == PANE_RIGHT
