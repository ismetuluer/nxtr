"""Bildirim merkezi: kart, geçmiş, Windows bildirimi, ses, görev çubuğu uyarısı ve ayarlar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QEvent, QPointF, QSettings
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.gui.notify import (
    KEY_CARD_SECONDS,
    KEY_FLASH,
    KEY_SOUND,
    KEY_SYSTEM,
    LEVEL_ERROR,
    LEVEL_SUCCESS,
    LEVEL_WARNING,
    MAX_HISTORY,
    NoticeAction,
    NotificationCenter,
)

pytestmark = pytest.mark.gui


class FakeTray:
    def __init__(self) -> None:
        self.shown: list[tuple[str, str]] = []

    def show_message(self, title: str, text: str, level: str) -> None:
        self.shown.append((title, text))


class Env:
    def __init__(self, qtbot: QtBot, tmp_path: Path) -> None:
        self.window = QMainWindow()
        self.window.setCentralWidget(QWidget())
        self.window.resize(900, 600)
        qtbot.addWidget(self.window)
        self.settings = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
        self.tray = FakeTray()
        self.sounds: list[str] = []
        self.alerts: list[Any] = []
        self.center = NotificationCenter(
            self.window,
            self.settings,
            tray=self.tray,
            sound=self.sounds.append,
            alert=self.alerts.append,
        )


@pytest.fixture
def env(qtbot: QtBot, tmp_path: Path) -> Env:
    return Env(qtbot, tmp_path)


def test_quiet_notice_shows_only_a_card(env: Env) -> None:
    env.center.notify(LEVEL_SUCCESS, "Tarama bitti", "373 dosya", loud=False)
    cards = env.center.stack.cards()
    assert [c.title_label.text() for c in cards] == ["Tarama bitti"]
    assert cards[0].text_label.text() == "373 dosya"
    assert env.tray.shown == []
    assert env.sounds == []
    assert env.alerts == []


def test_loud_notice_uses_system_sound_and_taskbar(env: Env) -> None:
    env.center.notify(LEVEL_ERROR, "Çeviri durdu", "Ollama yanıt vermedi.", loud=True)
    assert env.tray.shown == [("Çeviri durdu", "Ollama yanıt vermedi.")]
    assert env.sounds == [LEVEL_ERROR]
    assert env.alerts == [env.window]


def test_loud_defaults_to_window_not_active(env: Env) -> None:
    assert not env.window.isActiveWindow()  # gösterilmemiş pencere etkin değildir
    env.center.notify(LEVEL_WARNING, "Denetim bitti")
    assert env.tray.shown == [("Denetim bitti", "")]


def test_settings_turn_channels_off(env: Env) -> None:
    for key in (KEY_SOUND, KEY_SYSTEM, KEY_FLASH):
        env.settings.setValue(key, "0")
    env.center.notify(LEVEL_ERROR, "Hata", loud=True)
    assert env.tray.shown == []
    assert env.sounds == []
    assert env.alerts == []
    assert len(env.center.stack.cards()) == 1  # kart ve geçmiş her zaman


def test_action_button_runs_callback_and_closes_card(env: Env) -> None:
    ran: list[str] = []
    env.center.notify(LEVEL_ERROR, "Tarama başarısız", actions=(NoticeAction("Tekrar Dene", lambda: ran.append("x")),))
    card = env.center.stack.cards()[0]
    assert [b.text() for b in card.action_buttons] == ["Tekrar Dene"]
    card.action_buttons[0].click()
    assert ran == ["x"]
    assert env.center.stack.cards() == []


def test_close_button_removes_card_but_keeps_history(env: Env) -> None:
    env.center.notify(LEVEL_SUCCESS, "Bitti", loud=False)
    env.center.stack.cards()[0].close_button.click()
    assert env.center.stack.cards() == []
    assert [n.title for n in env.center.history] == ["Bitti"]


def test_cards_hide_themselves_after_configured_time(qtbot: QtBot, env: Env) -> None:
    env.settings.setValue(KEY_CARD_SECONDS, "0.05")
    env.center.notify(LEVEL_SUCCESS, "Bitti", loud=False)
    env.center.notify(LEVEL_ERROR, "Hata", loud=False)
    env.center.notify(LEVEL_ERROR, "Eylemli", actions=(NoticeAction("Aç", lambda: None),), loud=False)
    assert len(env.center.stack.cards()) == 3
    qtbot.waitUntil(lambda: env.center.stack.cards() == [], timeout=2000)
    assert [n.title for n in env.center.history] == ["Eylemli", "Hata", "Bitti"]  # geçmişte kalır


def test_zero_seconds_keeps_cards(qtbot: QtBot, env: Env) -> None:
    env.settings.setValue(KEY_CARD_SECONDS, "0")
    env.center.notify(LEVEL_SUCCESS, "Bitti", loud=False)
    qtbot.wait(150)
    assert len(env.center.stack.cards()) == 1


def test_default_card_seconds_is_eight(env: Env) -> None:
    assert env.center.card_ms() == 8000
    env.settings.setValue(KEY_CARD_SECONDS, "12")
    assert env.center.card_ms() == 12000


def test_hover_pauses_countdown(qtbot: QtBot, env: Env) -> None:
    env.settings.setValue(KEY_CARD_SECONDS, "0.1")
    env.center.notify(LEVEL_SUCCESS, "Bitti", loud=False)
    card = env.center.stack.cards()[0]
    QApplication.sendEvent(card, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    qtbot.wait(400)
    assert env.center.stack.cards() == [card]  # fare üstündeyken kaybolmaz
    QApplication.sendEvent(card, QEvent(QEvent.Type.Leave))
    qtbot.waitUntil(lambda: env.center.stack.cards() == [], timeout=2000)


def test_history_is_newest_first_and_bounded(env: Env) -> None:
    for i in range(MAX_HISTORY + 5):
        env.center.notify(LEVEL_SUCCESS, f"İş {i}", loud=False)
    assert len(env.center.history) == MAX_HISTORY
    assert env.center.history[0].title == f"İş {MAX_HISTORY + 4}"
    assert env.center.unread == MAX_HISTORY
    env.center.mark_read()
    assert env.center.unread == 0


def test_card_stack_keeps_at_most_a_few_cards(env: Env) -> None:
    for i in range(8):
        env.center.notify(LEVEL_ERROR, f"Hata {i}", loud=False)
    titles = [c.title_label.text() for c in env.center.stack.cards()]
    assert len(titles) <= 4
    assert titles[-1] == "Hata 7"  # en yenisi altta, görünür


def test_posted_signal(env: Env) -> None:
    got: list[Any] = []
    env.center.posted.connect(got.append)
    notice = env.center.notify(LEVEL_SUCCESS, "Bitti", loud=False)
    assert got == [notice]


def test_card_parts_do_not_overlap(qtbot: QtBot, env: Env) -> None:
    """Uzun metinli, düğmeli kartta başlık, metin ve düğme üst üste binmez (kart yüksekliği sarılan metne göre)."""
    env.window.show()
    env.center.notify(
        LEVEL_WARNING,
        "Yeniden çeviri bitti",
        "3.938 satır yenilendi · 2.098 satır aynı kaldı · 6 satır denetimden geçmedi",
        (NoticeAction("Değişiklikleri Gör", lambda: None),),
        loud=False,
    )
    env.center.notify(
        LEVEL_ERROR,
        "Otomatik çeviri durdu",
        "Ollama'ya bağlanılamadı. Yapılanlar kaydedildi. Yeniden başlatınca kaldığı yerden devam eder.",
        (NoticeAction("Tekrar Dene", lambda: None),),
        loud=False,
    )
    for card in env.center.stack.cards():
        qtbot.waitUntil(card.isVisible)
        title = card.title_label.geometry()
        text = card.text_label.geometry()
        button = card.action_buttons[0].mapTo(card, card.action_buttons[0].rect().topLeft())
        assert title.bottom() <= text.top()
        assert text.bottom() <= button.y()
        assert button.y() + card.action_buttons[0].height() <= card.height()
        assert text.height() > 1.5 * card.text_label.fontMetrics().height()  # uzun metin iki satıra sarıldı
