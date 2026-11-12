"""Çöp toplama denetimi: Python'un döngü toplayıcısı rastgele bir anda (Qt çağrısının ortasında ya da iş parçacığında)
değil, ana olay döngüsünde güvenli bir noktada çalışır. Sert çökmelerin (GC sırasında abort / erişim ihlali) önlemi."""

from __future__ import annotations

import gc
from collections.abc import Iterator

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.gui.gcguard import GarbageCollector


@pytest.fixture
def collector(qtbot: QtBot) -> Iterator[GarbageCollector]:
    was = gc.isenabled()
    guard = GarbageCollector(interval_ms=10)
    yield guard
    guard.stop()
    if was:
        gc.enable()


def test_automatic_gc_is_off_while_guard_runs(collector: GarbageCollector) -> None:
    assert not gc.isenabled()
    assert collector.active


def test_cycles_are_collected_from_the_event_loop(qtbot: QtBot, collector: GarbageCollector) -> None:
    class Node:
        def __init__(self) -> None:
            self.other: Node | None = None

    before = collector.collected
    for _ in range(gc.get_threshold()[0] + 50):
        a, b = Node(), Node()
        a.other, b.other = b, a  # döngü: yalnızca döngü toplayıcı temizler
    qtbot.waitUntil(lambda: collector.collected > before, timeout=3000)


def test_stop_restores_automatic_gc(qtbot: QtBot) -> None:
    was = gc.isenabled()
    gc.enable()
    guard = GarbageCollector(interval_ms=10)
    guard.stop()
    assert gc.isenabled()
    assert not guard.active
    if not was:
        gc.disable()


def test_release_thread_waits_until_the_thread_has_stopped(qtbot: QtBot) -> None:
    import time

    from nxceviri.gui.tasks import Task, release_thread

    task = Task(lambda _ctx: time.sleep(0.2), "deneme")
    task.start()
    release_thread(task)  # finished beklenmeden bile çağrılsa: durana kadar bekler
    assert task.isFinished()


def test_machine_dialog_is_deleted_after_use(qtbot: QtBot, tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Otomatik Çeviri penceresi her açılışta ana pencerenin çocuğu olarak kalıyordu (sızıntı)."""
    from pathlib import Path

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QDialog

    from nxceviri.gui import machine_dialogs
    from tests.test_statusbar import _make_window, _project

    assert isinstance(tmp_path, Path)
    w = _make_window(qtbot, tmp_path, _project())
    monkeypatch.setattr(machine_dialogs.MachineDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    for _ in range(3):
        assert w.ask_machine_settings(w._machine_scopes()) is not None
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    assert not w.findChildren(machine_dialogs.MachineDialog)
    w.dirty = False
    w.close()
