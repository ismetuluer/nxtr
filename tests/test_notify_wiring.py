"""Bildirim merkezinin uygulamaya bağlanması: kısa iş özeti, sayfa mesajları, arka plan işleri, güncelleme."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.progress import TaskContext
from nxceviri.core.translate.runner import ACTION_RETRANSLATE, ACTION_TRANSLATE, Rejection, RunSummary
from nxceviri.core.update import UpdateInfo
from nxceviri.gui.jobs import short_summary
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_SUCCESS, LEVEL_WARNING, split_notice
from tests.test_statusbar import _make_window, _project

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    w.notifier._tray.show_message = lambda *_a: None  # type: ignore[method-assign]
    w.notifier._sound = lambda _level: None
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _wait_idle(qtbot: QtBot, w: MainWindow) -> None:
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)


def test_short_summary_is_one_line_without_paths_or_suggestions() -> None:
    summary = RunSummary(
        translated=3938,
        unchanged=2098,
        rejected=6,
        cleaned=5,
        rejections=[Rejection("despelote_loc/x/Nina1_01/conversation/2", "Kaleyi …", ("Eksik kontrol kodu: [1]",))],
    )
    level, title, text = short_summary(ACTION_RETRANSLATE, summary)
    assert level == LEVEL_WARNING
    assert title == "Yeniden çeviri bitti"
    assert text == "3.938 satır yenilendi · 2.098 satır aynı kaldı · 6 satır denetimden geçmedi"
    assert "/" not in text
    assert "Kaleyi" not in text


def test_short_summary_success() -> None:
    level, title, text = short_summary(ACTION_TRANSLATE, RunSummary(translated=12, from_memory=3))
    assert (level, title, text) == (LEVEL_SUCCESS, "Otomatik çeviri bitti", "12 satır çevrildi · 3 satır bellekten")


def test_split_notice_makes_short_title() -> None:
    assert split_notice("Ollama'ya bağlanılamadı. Ollama'nın çalıştığından emin olun.") == (
        "Ollama'ya bağlanılamadı",
        "Ollama'nın çalıştığından emin olun.",
    )
    title, rest = split_notice("Kısa mesaj")
    assert (title, rest) == ("Kısa mesaj", "")


def test_page_notice_becomes_a_card_not_a_page_box(window: MainWindow) -> None:
    window.translate_page.show_notice("danger", "Kayıt başarısız. Disk dolu olabilir.")
    cards = window.notifier.stack.cards()
    assert [c.title_label.text() for c in cards] == ["Kayıt başarısız"]
    assert cards[0].notice.level == LEVEL_ERROR


def test_background_task_success_and_failure_notify(qtbot: QtBot, window: MainWindow) -> None:
    window._run(lambda _ctx: 1, "Fontlar taranıyor", on_success=lambda _r: None, on_failure=lambda _t: None)
    _wait_idle(qtbot, window)
    assert window.notifier.history[0].title == "Font tarama bitti"

    def boom(_ctx: TaskContext) -> object:
        raise OSError("disk")

    window._run(boom, "Tarama", on_success=lambda _r: None, on_failure=lambda _t: None)
    _wait_idle(qtbot, window)
    notice = window.notifier.history[0]
    assert notice.level == LEVEL_ERROR
    assert notice.title == "Tarama başarısız"
    assert notice.actions[0].label == "Tekrar Dene"


def test_handler_notice_replaces_generic_one(qtbot: QtBot, window: MainWindow) -> None:
    window._run(
        lambda _ctx: 1,
        "Tarama",
        on_success=lambda _r: window.notify(LEVEL_SUCCESS, "Tarama bitti", "373 dosya"),
        on_failure=lambda _t: None,
    )
    _wait_idle(qtbot, window)
    assert [n.title for n in window.notifier.history] == ["Tarama bitti"]
    assert window.notifier.history[0].text == "373 dosya"


def test_new_version_is_announced(window: MainWindow) -> None:
    window._update_checked(UpdateInfo(current="0.1.0", version="9.9.9", sha="", notes=""))
    notice = window.notifier.history[0]
    assert notice.title == "Yeni sürüm: 9.9.9"
    assert [a.label for a in notice.actions] == ["Şimdi Güncelle", "Sonra"]


def test_install_failure_is_announced_with_retry(window: MainWindow) -> None:
    window.notify_update_failure("Dosya kullanımda.")
    notice = window.notifier.history[0]
    assert notice.level == LEVEL_ERROR
    assert notice.title == "Güncelleme kurulamadı"
    assert "Dosya kullanımda." in notice.text


def test_job_changes_dialog_edits_and_shows_context(window: MainWindow) -> None:
    from nxceviri.gui.changes_dialog import NEW_TEXT_ROLE

    rows = {r.key: r for r in window.project.translation_rows()}
    job = "retranslate-test"
    window.project.set_translations([(rows["d02"].id, "Hoşça kal")], machine=True, job=job)
    window._reload_rows()
    window._set_last_job(job)
    window.show_job_changes()
    dialog = window.changes_dialog
    assert dialog is not None
    item = dialog.table.item(0, 4)
    assert item is not None
    item.setData(NEW_TEXT_ROLE, "Görüşürüz")
    saved = {r.key: r.translation for r in window.project.translation_rows()}
    assert saved["d02"] == "Görüşürüz"
    dialog.context_box.setChecked(True)
    tip = dialog.context_tip(0)
    assert "Hello there" in tip  # önceki satır
    assert "▶ bu satır" in tip
    dialog.close()
