"""Testlerde arka plan işinin (Task) bitmesini ve sonuç sinyallerinin işlenmesini bekleme."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from nxceviri.gui.main_window import MainWindow


def finish_task(window: MainWindow) -> None:
    """Süren iş bitene ve sonucu ana iş parçacığında işlenene dek bekler (Denetle artık arka planda çalışır)."""
    for _ in range(1000):
        task = window.task
        if task is None:
            return
        task.wait(10000)
        QApplication.processEvents()
    raise AssertionError("Arka plan işi bitmedi")
