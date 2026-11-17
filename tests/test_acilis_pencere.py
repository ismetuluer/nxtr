"""Açılış: ana pencere kurulurken başka üst düzey pencere bir anlığına görünmemeli (ekran titremesi)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QObject, QSettings
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.widgets import Card


class _WindowShowSpy(QObject):
    """Ebeveynsiz (üst düzey) gösterilen widget'ları toplar."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[str] = []

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            self.shown.append(type(obj).__name__)
        return False


def _spy() -> _WindowShowSpy:
    spy = _WindowShowSpy()
    app = QApplication.instance()
    assert app is not None
    app.installEventFilter(spy)
    return spy


def test_baslikli_kart_kurulurken_ayri_pencere_acmaz(qtbot: QtBot) -> None:
    spy = _spy()
    try:
        card = Card("Başlık")
    finally:
        QApplication.instance().removeEventFilter(spy)  # type: ignore[union-attr]
    qtbot.addWidget(card)
    assert spy.shown == []
    assert not card.title.isHidden()


def test_basliksiz_kartin_baslik_satiri_gizli(qtbot: QtBot) -> None:
    card = Card("")
    qtbot.addWidget(card)
    card.show()
    assert not card.title.parentWidget().isVisible()  # type: ignore[union-attr]


@pytest.mark.parametrize("collapsed", [False, True])
def test_ana_pencere_kurulurken_baska_pencere_gorunmez(qtbot: QtBot, tmp_path: Path, collapsed: bool) -> None:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    settings.setValue("ui/nav_collapsed", "1" if collapsed else "0")
    spy = _spy()
    try:
        window = MainWindow(settings)
    finally:
        QApplication.instance().removeEventFilter(spy)  # type: ignore[union-attr]
    qtbot.addWidget(window)
    window.dirty = False
    assert spy.shown == []
    assert window.nav_header.isHidden() is collapsed
