"""Yazım Denetimi penceresi büyük projede arka planda taranır: pencere hemen açılır, kapatılınca sonuç uygulanmaz."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.spell.report import UnknownWordCache
from nxceviri.gui.main_window import SPELL_SYNC_ROWS, MainWindow
from tests import test_spell_suggest_gui as base
from tests.test_spell_suggest_gui import _open, _project

pytestmark = pytest.mark.gui

window = base.window  # aynı pencere donanımı

BIG = 35_000


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch) -> threading.Event:
    """Arka plan taramasını `set()` edilene dek bekletir (zamanlamadan bağımsız, kararlı testler için)."""
    opened = threading.Event()
    original: Callable[..., object] = UnknownWordCache.scan

    def slow(*args: object, **kwargs: object) -> object:
        opened.wait(30)
        return original(*args, **kwargs)

    monkeypatch.setattr(UnknownWordCache, "scan", staticmethod(slow))
    return opened


def test_big_project_opens_at_once_and_shows_waiting_state(
    qtbot: QtBot, window: MainWindow, gate: threading.Event
) -> None:
    window._replace_project(_project(filler=BIG))
    start = time.perf_counter()
    win = _open(window)
    assert time.perf_counter() - start < 0.5  # tarama beklenmez
    assert win.isVisible()
    assert win.scanning.isVisibleTo(win)  # maskotlu yükleniyor durumu
    assert not win.table.isVisibleTo(win)
    assert not win.empty_label.isVisibleTo(win)
    gate.set()
    qtbot.waitUntil(lambda: window._spell_scan is None and win.table.rowCount() > 0, timeout=120_000)
    assert not win.scanning.isVisibleTo(win)
    assert win.table.isVisibleTo(win)
    assert {win.table.item(r, 0).text() for r in range(win.table.rowCount())} >= {"buradaşın", "şapkadir"}  # type: ignore[union-attr]


def test_closing_window_during_scan_discards_the_result(
    qtbot: QtBot, window: MainWindow, gate: threading.Event
) -> None:
    window._replace_project(_project(filler=BIG))
    win = _open(window)
    assert window._spell_scan is not None
    win.close()
    gate.set()
    qtbot.waitUntil(lambda: window._spell_scan is None, timeout=120_000)
    assert win.table.rowCount() == 0  # kapalı pencereye sonuç uygulanmadı
    assert not win.isVisible()


def test_project_change_during_scan_discards_the_result(
    qtbot: QtBot, window: MainWindow, gate: threading.Event
) -> None:
    window._replace_project(_project(filler=BIG))
    win = _open(window)
    assert window._spell_scan is not None
    window._replace_project(_project())  # tarama sürerken proje değişti
    gate.set()
    qtbot.waitUntil(lambda: window._spell_scan is None, timeout=120_000)
    # eski projenin satırları yeni projenin önbelleğine karışmadı; yeni proje kendi satırlarıyla kuruldu
    qtbot.waitUntil(lambda: win.table.rowCount() > 0, timeout=30_000)
    words = {win.table.item(r, 0).text() for r in range(win.table.rowCount())}  # type: ignore[union-attr]
    assert words == {"buradaşın", "şapkadir", "şiril", "kitapp"}
    assert len(window._spell_cache._rows) == len(window.translate_page.model.rows)


def test_fresh_cache_fills_instantly_without_background_scan(qtbot: QtBot, window: MainWindow) -> None:
    window._replace_project(_project(filler=SPELL_SYNC_ROWS + 500))
    win = _open(window)
    qtbot.waitUntil(lambda: window._spell_scan is None and win.table.rowCount() > 0, timeout=120_000)
    win.close()
    start = time.perf_counter()
    win = _open(window)  # önbellek tazeyken yeniden açılış
    assert window._spell_scan is None
    assert win.table.rowCount() > 0
    assert not win.scanning.isVisibleTo(win)
    assert time.perf_counter() - start < 0.5
