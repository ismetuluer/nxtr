"""Kaydedilmemiş değişiklik sorusu: Evet / Hayır / İptal (Qt'nin "At" çevirisine bağlı değil)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QCloseEvent
from pytestqt.qtbot import QtBot

from nxceviri.gui.main_window import MainWindow, build_save_box

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = MainWindow(QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat))
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _answer(monkeypatch: pytest.MonkeyPatch, w: MainWindow, choice: str) -> list[bool]:
    asked: list[bool] = []

    def fake(closing: bool) -> str:
        asked.append(closing)
        return choice

    monkeypatch.setattr(w, "ask_save_changes", fake)
    return asked


def test_box_buttons_default_and_escape(qtbot: QtBot, window: MainWindow) -> None:
    box, save, discard = build_save_box(window, closing=False)
    qtbot.addWidget(box)
    assert box.windowTitle() == "Kaydedilmemiş değişiklikler"
    assert sorted(b.text() for b in box.buttons()) == ["Evet", "Hayır", "İptal"]
    assert save.text() == "Evet"
    assert discard.text() == "Hayır"
    assert box.defaultButton() is save
    escape = box.escapeButton()
    assert escape is not None
    assert escape.text() == "İptal"
    assert "At" not in [b.text() for b in box.buttons()]


def test_box_text_depends_on_closing(qtbot: QtBot, window: MainWindow) -> None:
    closing, _, _ = build_save_box(window, closing=True)
    other, _, _ = build_save_box(window, closing=False)
    qtbot.addWidget(closing)
    qtbot.addWidget(other)
    assert closing.text() == "Projede kaydedilmemiş değişiklikler var. Çıkmadan önce kaydedilsin mi?"
    assert other.text() == "Projede kaydedilmemiş değişiklikler var. Devam etmeden önce kaydedilsin mi?"


def test_not_dirty_asks_nothing(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _answer(monkeypatch, window, "cancel")
    window.dirty = False
    assert window._confirm_discard() is True
    assert asked == []


@pytest.mark.parametrize("saved", [True, False])
def test_save_returns_save_result(window: MainWindow, monkeypatch: pytest.MonkeyPatch, saved: bool) -> None:
    _answer(monkeypatch, window, "save")
    calls: list[int] = []

    def save() -> bool:
        calls.append(1)
        return saved

    monkeypatch.setattr(window, "save_project", save)
    window.dirty = True
    assert window._confirm_discard() is saved
    assert calls == [1]


def test_discard_continues_without_saving(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, window, "discard")
    calls: list[int] = []

    def save() -> bool:
        calls.append(1)
        return True

    monkeypatch.setattr(window, "save_project", save)
    window.dirty = True
    assert window._confirm_discard() is True
    assert calls == []


def test_cancel_keeps_project(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, window, "cancel")
    project = window.project
    window.dirty = True
    assert window._confirm_discard() is False
    assert window.project is project
    assert window.dirty is True


def test_close_event_passes_closing_and_cancel_ignores(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _answer(monkeypatch, window, "cancel")
    window.dirty = True
    event = QCloseEvent()
    window.closeEvent(event)
    assert asked == [True]
    assert not event.isAccepted()


def test_new_project_asks_with_closing_false(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _answer(monkeypatch, window, "cancel")
    window.dirty = True
    window.new_project()
    assert asked == [False]
