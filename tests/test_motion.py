"""Kısa açılış animasyonları: bildirim kartı ve düzenleme paneli solarak açılır; kapalıyken anında."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QGraphicsOpacityEffect, QMainWindow, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.gui import motion
from nxceviri.gui.motion import FADE_MS, animations_enabled, fade_in
from nxceviri.gui.notify import Notice, NoticeCard

pytestmark = pytest.mark.gui


def test_animations_are_off_under_offscreen_platform(qtbot: QtBot) -> None:
    """Testlerde ve `offscreen`de hiçbir animasyon beklemez."""
    assert not animations_enabled()


def test_fade_in_is_instant_when_disabled(qtbot: QtBot) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.show()
    assert fade_in(widget) is None
    assert widget.graphicsEffect() is None


def test_fade_in_runs_briefly_and_cleans_up(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(motion, "animations_enabled", lambda: True)
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.show()
    anim = fade_in(widget)
    assert anim is not None
    assert anim.duration() == FADE_MS <= 150
    effect = widget.graphicsEffect()
    assert isinstance(effect, QGraphicsOpacityEffect)
    assert effect.opacity() < 1.0
    qtbot.waitUntil(lambda: widget.graphicsEffect() is None, timeout=2000)


def test_notice_card_fades_in_when_animations_on(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(motion, "animations_enabled", lambda: True)
    window = QMainWindow()
    qtbot.addWidget(window)
    window.resize(800, 600)
    window.show()
    from nxceviri.gui.notify import NoticeStack

    stack = NoticeStack(window)
    card = NoticeCard(Notice("info", "Merhaba", "Deneme"))
    stack.add(card)
    assert isinstance(card.graphicsEffect(), QGraphicsOpacityEffect)
    qtbot.waitUntil(lambda: card.graphicsEffect() is None, timeout=2000)
    assert card.isVisible()


def test_editor_pane_fades_in_when_reopened(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_translate_pane import make_page

    page, _ = make_page(qtbot)
    page.view_actions.pane_toggle.trigger()  # kapat
    assert not page.pane.isVisibleTo(page)
    assert page.pane.graphicsEffect() is None
    monkeypatch.setattr(motion, "animations_enabled", lambda: True)
    page.view_actions.pane_toggle.trigger()  # aç
    assert page.pane.isVisibleTo(page)
    assert isinstance(page.pane.graphicsEffect(), QGraphicsOpacityEffect)
    qtbot.waitUntil(lambda: page.pane.graphicsEffect() is None, timeout=2000)


def test_notice_card_has_no_effect_when_animations_off(qtbot: QtBot) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    window.show()
    from nxceviri.gui.notify import NoticeStack

    stack = NoticeStack(window)
    card = NoticeCard(Notice("info", "Merhaba", "Deneme"))
    stack.add(card)
    assert card.graphicsEffect() is None
