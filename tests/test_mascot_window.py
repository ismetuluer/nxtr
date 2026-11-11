"""Maskot ana pencerede: işte çalışır, bitince sevinir, hatada endişelenir, uzun boşta uyur; Ayarlar'dan kapanır."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.gui import main_window as mw
from nxceviri.gui import mascot, motion
from nxceviri.gui.main_window import MASCOT_SLEEP_S, MainWindow
from nxceviri.gui.mascot import (
    KEY_MASCOT,
    MOOD_DONE,
    MOOD_ERROR,
    MOOD_IDLE,
    MOOD_SLEEP,
    MOOD_WORKING,
    set_mascot_enabled,
)
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_INFO, LEVEL_SUCCESS, Notice, NoticeCard
from tests.test_statusbar import _make_window, _project

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    monkeypatch.setattr(mascot, "animations_enabled", lambda: False)
    monkeypatch.setattr(mw, "MASCOT_DONE_MS", 50)
    w = _make_window(qtbot, tmp_path, _project())
    w.notifier._tray.show_message = lambda *_a: None  # type: ignore[method-assign]
    w.notifier._sound = lambda _level: None
    yield w
    set_mascot_enabled(True)
    w.dirty = False
    w.close()


def test_job_makes_the_mascot_work_then_cheer_then_rest(qtbot: QtBot, window: MainWindow) -> None:
    assert window.mascot.mood == MOOD_IDLE
    seen: list[str] = []

    def work(_ctx: object) -> object:
        return 1

    window._run(work, "Deneme", on_success=lambda _r: seen.append(window.mascot.mood), on_failure=lambda _t: None)
    assert window.mascot.mood == MOOD_WORKING
    qtbot.waitUntil(lambda: not window.busy, timeout=5000)
    assert seen == [MOOD_WORKING]  # sonuç işlenirken hâlâ çalışıyor
    assert window.mascot.mood == MOOD_DONE  # genel "bitti" bildirimiyle sevindi
    qtbot.waitUntil(lambda: window.mascot.mood == MOOD_IDLE, timeout=3000)


def test_error_notice_worries_and_info_does_not(window: MainWindow) -> None:
    window.notify(LEVEL_INFO, "Bilgi")
    assert window.mascot.mood == MOOD_IDLE
    window.notify(LEVEL_ERROR, "Olmadı", "Bağlanılamadı")
    assert window.mascot.mood == MOOD_ERROR


def test_long_system_idle_sleeps_and_activity_wakes(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(motion, "idle_seconds", lambda: MASCOT_SLEEP_S + 1)
    window._mascot_check_idle()
    assert window.mascot.mood == MOOD_SLEEP
    monkeypatch.setattr(motion, "idle_seconds", lambda: 0.5)  # kullanıcı bir tuşa bastı
    window._mascot_check_idle()
    assert window.mascot.mood == MOOD_IDLE


def test_does_not_sleep_while_a_job_runs(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    window.mascot.set_mood(MOOD_WORKING)
    monkeypatch.setattr(motion, "idle_seconds", lambda: MASCOT_SLEEP_S + 1)
    window._mascot_check_idle()
    assert window.mascot.mood == MOOD_WORKING


def test_no_application_wide_python_event_filter(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Uygulama çapında Python olay süzgeci yok: her Qt olayında Python'a girmek çeviri sürerken çökmelere yol açtı."""
    from PySide6.QtWidgets import QApplication

    installed: list[object] = []
    real = QApplication.installEventFilter

    def spy(self: QApplication, flt: object) -> None:
        installed.append(flt)
        real(self, flt)  # type: ignore[arg-type]

    monkeypatch.setattr(QApplication, "installEventFilter", spy)
    w = _make_window(qtbot, tmp_path, _project())
    assert not [f for f in installed if type(f).__module__.startswith("nxceviri")]
    assert w._mascot_poll.isActive()
    w.dirty = False
    w.close()


def test_idle_seconds_is_a_small_non_negative_number() -> None:
    value = motion.idle_seconds()
    assert isinstance(value, float)
    assert 0.0 <= value < 10 * 365 * 24 * 3600


def test_settings_switch_hides_all_mascots_and_is_saved(qtbot: QtBot, window: MainWindow) -> None:
    window.show()
    qtbot.waitExposed(window)
    assert window.mascot.isVisible()
    mascot.save_mascot_setting(window.settings, False)
    assert not window.mascot.isVisible()
    assert window.settings.value(KEY_MASCOT) == "false"
    assert not mascot.mascot_setting(window.settings)


def test_notice_card_shows_mascot_instead_of_icon(qtbot: QtBot) -> None:
    card = NoticeCard(Notice(LEVEL_SUCCESS, "Bitti", ""))
    qtbot.addWidget(card)
    assert card.mascot is not None
    assert card.icon_label.isHidden()
    qtbot.waitUntil(lambda: card.mascot is not None and card.mascot.mood == MOOD_DONE, timeout=2000)
    info = NoticeCard(Notice(LEVEL_INFO, "Bilgi", ""))
    qtbot.addWidget(info)
    assert info.mascot is None  # bilgi kartında simge kalır
    set_mascot_enabled(False)
    plain = NoticeCard(Notice(LEVEL_ERROR, "Hata", ""))
    qtbot.addWidget(plain)
    assert plain.mascot is None
    assert not plain.icon_label.isHidden()
    set_mascot_enabled(True)


def test_settings_dialog_has_the_switch(qtbot: QtBot, window: MainWindow) -> None:
    from nxceviri.gui.settings_dialog import PAGE_VIEW, SettingsDialog
    from nxceviri.gui.theme import ThemeMode

    page = window.translate_page
    dialog = SettingsDialog(
        window,
        window.settings,
        window.shortcuts,
        page.view_actions,
        window.secrets,
        theme=ThemeMode.DARK,
        font_size=10,
        wrap=page.wrap_box,
        issue_colors=page.colors_box,
        error_rows=page.error_rows_box,
        updates_available=False,
        page=PAGE_VIEW,
    )
    qtbot.addWidget(dialog)
    assert dialog.mascot_check.isChecked()
    dialog.mascot_check.setChecked(False)
    assert window.settings.value(KEY_MASCOT) == "false"
    assert not mascot.mascot_enabled()
