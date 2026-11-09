"""Kısayol kayıt defteri: katalog, kalıcılık, bağlı eylemlerin güncellenmesi ve çakışma denetimi."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from nxceviri.gui.shortcuts import CATEGORIES, COMMANDS, COMMANDS_BY_ID, KEY_PREFIX, ShortcutRegistry, reserved_reason


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "ayar.ini"), QSettings.Format.IniFormat)


def test_catalog_ids_unique_and_categories_known() -> None:
    assert len(COMMANDS_BY_ID) == len(COMMANDS)
    assert {c.category for c in COMMANDS} <= set(CATEGORIES)


def test_default_keys_do_not_collide() -> None:
    seen: dict[str, str] = {}
    for command in COMMANDS:
        if not command.default:
            continue
        key = QKeySequence(command.default).toString(QKeySequence.SequenceFormat.PortableText)
        assert key, command.id
        assert key not in seen, (command.id, seen.get(key))
        seen[key] = command.id


def test_bound_action_gets_default_and_follows_change(qtbot: QtBot, tmp_path: Path) -> None:
    registry = ShortcutRegistry()
    registry.bind_settings(_settings(tmp_path))
    action = QAction("Otomatik Çeviri")
    registry.bind("translate.auto", action, tip="Toplu çeviri")
    assert action.shortcut() == QKeySequence("Ctrl+T")
    native = QKeySequence("Ctrl+T").toString(QKeySequence.SequenceFormat.NativeText)
    assert action.toolTip() == f"Toplu çeviri ({native})"
    registry.set_sequence("translate.auto", QKeySequence("Ctrl+Shift+Y"))
    assert action.shortcut() == QKeySequence("Ctrl+Shift+Y")
    assert registry.is_custom("translate.auto")


def test_shortcut_object_is_updated(qtbot: QtBot) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    registry = ShortcutRegistry()
    shortcut = QShortcut(widget)
    registry.bind("edit.find", shortcut)
    assert shortcut.key() == QKeySequence("Ctrl+F")
    registry.set_sequence("edit.find", QKeySequence("Alt+F"))
    assert shortcut.key() == QKeySequence("Alt+F")


def test_custom_keys_persist_and_reset_removes_record(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = ShortcutRegistry()
    first.bind_settings(settings)
    first.set_sequence("view.pane", QKeySequence("Ctrl+Shift+J"))
    first.set_sequence("translate.glossary", QKeySequence())  # kısayolsuz bırakıldı
    settings.sync()

    second = ShortcutRegistry()
    second.bind_settings(_settings(tmp_path))
    assert second.sequence("view.pane") == QKeySequence("Ctrl+Shift+J")
    assert second.sequence("translate.glossary").isEmpty()
    assert second.text("translate.glossary") == ""

    second.reset("view.pane")
    assert second.sequence("view.pane") == QKeySequence("Ctrl+J")
    assert not second.is_custom("view.pane")
    assert not _settings(tmp_path).contains(KEY_PREFIX + "view.pane")


def test_setting_default_again_is_not_custom(tmp_path: Path) -> None:
    registry = ShortcutRegistry()
    registry.bind_settings(_settings(tmp_path))
    registry.set_sequence("file.save", QKeySequence("Ctrl+S"))
    assert not registry.is_custom("file.save")


def test_reset_all_restores_every_default(tmp_path: Path) -> None:
    registry = ShortcutRegistry()
    registry.bind_settings(_settings(tmp_path))
    registry.set_sequence("file.save", QKeySequence("Ctrl+Alt+K"))
    registry.set_sequence("edit.undo", QKeySequence())
    changed: list[str] = []
    registry.changed.connect(changed.append)
    registry.reset_all()
    assert registry.sequence("file.save") == QKeySequence("Ctrl+S")
    assert registry.sequence("edit.undo") == QKeySequence("Ctrl+Z")
    assert sorted(changed) == ["edit.undo", "file.save"]


def test_conflicts_name_other_commands_only() -> None:
    registry = ShortcutRegistry()
    clash = registry.conflicts("translate.auto", QKeySequence("Ctrl+F"))
    assert [c.id for c in clash] == ["edit.find"]
    assert registry.conflicts("edit.find", QKeySequence("Ctrl+F")) == []
    assert registry.conflicts("edit.find", QKeySequence()) == []


def test_broken_and_unknown_settings_fall_back(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    settings = _settings(tmp_path)
    settings.setValue(KEY_PREFIX + "file.save", "Ctrl+Bozuk+Tuş+???")
    settings.setValue(KEY_PREFIX + "yok.boyle", "Ctrl+K")
    registry = ShortcutRegistry()
    with caplog.at_level("WARNING"):
        registry.bind_settings(settings)
    assert registry.sequence("file.save") == QKeySequence("Ctrl+S")
    assert "yok.boyle" in caplog.text


def test_unknown_command_cannot_be_bound() -> None:
    with pytest.raises(KeyError):
        ShortcutRegistry().bind("yok.boyle", QAction("x"))


def test_destroyed_target_is_forgotten(qtbot: QtBot) -> None:
    registry = ShortcutRegistry()
    widget = QWidget()
    qtbot.addWidget(widget)
    action = QAction("Bul", widget)
    registry.bind("edit.find", action)
    action.deleteLater()
    qtbot.waitUntil(lambda: not any(registry._bound.get("edit.find", [])))
    registry.set_sequence("edit.find", QKeySequence("Alt+F"))  # silinmiş nesneye yazmaya çalışmamalı


@pytest.mark.parametrize(
    "key",
    [
        *("Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+A", "Alt+Up", "Alt+Down", "Esc", "Return", "Enter", "Tab", "Backspace"),
        *("Delete", "F2", "Space", "A", "5", "Shift+A", "Left", "Up", "PgDown", "Home", "Ctrl+Insert"),
    ],
)
def test_reserved_keys_are_reported(key: str) -> None:
    reason = reserved_reason(QKeySequence(key))
    assert reason is not None, key
    assert reason


@pytest.mark.parametrize("key", ["F1", "F3", "F12", "Shift+F3", "Ctrl+Shift+G", "Ctrl+Alt+S", "Ctrl+,", "Alt+F"])
def test_ordinary_shortcuts_are_not_reserved(key: str) -> None:
    assert reserved_reason(QKeySequence(key)) is None, key


def test_default_keys_are_not_reserved() -> None:
    for command in COMMANDS:
        if command.default:
            assert reserved_reason(QKeySequence(command.default)) is None, command.id
