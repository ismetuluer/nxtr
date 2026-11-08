"""Son incelemede bulunan arayüz sorunlarının regresyon testleri (rozetler, durum çubuğu, kenar çubuğu, metinler)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from nxceviri.gui.main_window import STEP_QA, STEP_TRANSLATE, MainWindow
from nxceviri.gui.step_nav import BADGE_ROLE, LIST_PADDING, StepNav, text_room
from nxceviri.gui.tasks import Task
from tests.test_statusbar import _make_window, _project

pytestmark = pytest.mark.gui

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _restore_app(qtbot: QtBot) -> Iterator[None]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    yield
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)


def _close(w: MainWindow) -> None:
    w.task = None
    w.dirty = False
    w.close()
    w.deleteLater()


def _badge(w: MainWindow) -> str:
    return str(w.nav.item(STEP_TRANSLATE).data(BADGE_ROLE))


def test_rows_replaced_refreshes_badges_and_status(qtbot: QtBot, tmp_path: Path) -> None:
    """Hazır çeviri içe aktarma ve otomatik düzeltme satırları `set_rows` ile değiştirir; sayılar bayatlamamalı."""
    w = _make_window(qtbot, tmp_path, _project())
    try:
        assert _badge(w) == "%67"
        row = next(r for r in w.project.translation_rows() if r.key == "d02")
        w.project.set_translations([(row.id, "Hoşça kal")], machine=True)
        w.translate_page.set_rows(w.project.translation_rows())
        qtbot.waitUntil(lambda: _badge(w) == "%100", timeout=3000)
        assert w.status_segments.progress_label.text() == "%100"
    finally:
        _close(w)


def test_single_apply_emits_one_data_changed(qtbot: QtBot, tmp_path: Path) -> None:
    """Satırlar iki kez işlenmemeli: her işleme tablo modelinde ikinci bir `dataChanged` dalgası başlatır."""
    w = _make_window(qtbot, tmp_path, _project())
    try:
        model = w.translate_page.model
        seen: list[int] = []
        model.dataChanged.connect(lambda *_a: seen.append(1))
        row = next(r for r in model.rows if not r.translation)
        assert model.apply([(row.id, "Hoşça kal")])
        assert len(seen) == 1
        qtbot.waitUntil(lambda: _badge(w) == "%100", timeout=3000)  # rozet düzenlemenin arkasında kalmaz
    finally:
        _close(w)


def test_error_rows_do_not_count_as_translated(qtbot: QtBot, tmp_path: Path) -> None:
    """Çeviri sayfası "Çevrilen" sayısına Hatalı satırları katmaz; kenar ve durum çubuğu da katmamalı."""
    w = _make_window(qtbot, tmp_path, _project(changed_source=True))
    try:
        assert _badge(w) == "%33"
        assert w.status_segments.progress_label.text() == "%33"
    finally:
        _close(w)


@pytest.mark.parametrize("size", [9, 18])
def test_widest_step_label_fits_beside_five_digit_badge(qtbot: QtBot, size: int) -> None:
    nav = StepNav()
    qtbot.addWidget(nav)
    font = QFont(nav.font())
    font.setPointSize(size)
    nav.setFont(font)
    nav.set_badge(1, "99.999")
    bold = QFont(font)
    bold.setBold(True)
    metrics = QFontMetrics(bold)
    viewport_width = nav.preferred_width() - LIST_PADDING
    assert text_room(viewport_width, metrics.horizontalAdvance("99.999")) >= metrics.horizontalAdvance("Metinleri Tara")


def test_problems_button_ignored_while_busy(qtbot: QtBot, tmp_path: Path) -> None:
    w = _make_window(qtbot, tmp_path, _project(changed_source=True))
    try:
        w.nav.setCurrentRow(STEP_TRANSLATE)
        w.task = cast(Task, object())  # sürmekte olan iş
        qtbot.mouseClick(w.status_segments.problems_button, Qt.MouseButton.LeftButton)
        assert w.pages.currentIndex() == STEP_TRANSLATE
        w.task = None
        qtbot.mouseClick(w.status_segments.problems_button, Qt.MouseButton.LeftButton)
        assert w.pages.currentIndex() == STEP_QA
    finally:
        _close(w)


_NUMBERED = re.compile(r"[1-5]\. (?:Oyunu Ekle|Metinleri Tara|Çevir|Kontrol Et|Dışa Aktar)")


def test_no_numbered_step_names_in_user_text() -> None:
    """Kenar çubuğu adımları numarasız; iletilerde ve belgelerde de numarasız anılır."""
    files = [*sorted((ROOT / "nxceviri" / "gui").glob("*.py")), ROOT / "nxceviri" / "core" / "export" / "layeredfs.py"]
    files.append(ROOT / "docs" / "translation.md")
    found = [
        f"{path.name}: {match.group(0)}"
        for path in files
        for match in _NUMBERED.finditer(path.read_text(encoding="utf-8"))
    ]
    assert found == []
