"""Kenar çubuğu: simgeli adımlar, rozetler ve proje başlığı."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import ImportedFile, Project, SourceRecord
from nxceviri.core.secrets import MemoryStore
from nxceviri.gui.main_window import STEP_ADD, STEP_QA, STEP_SCAN, STEP_TRANSLATE, MainWindow
from nxceviri.gui.step_nav import BADGE_ROLE, DONE_ROLE, ICON_ROLE, STATE_ROLE, STEPS, ProjectHeader, StepNav


@pytest.fixture(autouse=True)
def _restore_app(qtbot: QtBot) -> Iterator[None]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    yield
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)


def test_steps_and_icons(qtbot: QtBot) -> None:
    nav = StepNav()
    qtbot.addWidget(nav)
    assert nav.count() == 5
    assert [nav.item(i).text() for i in range(5)] == [name for name, _icon in STEPS]
    assert [nav.item(i).data(ICON_ROLE) for i in range(5)] == [icon for _name, icon in STEPS]
    assert nav.objectName() == "stepNav"


def test_set_badge_and_state(qtbot: QtBot) -> None:
    nav = StepNav()
    qtbot.addWidget(nav)
    nav.set_badge(2, "%64", "success")
    assert nav.item(2).data(BADGE_ROLE) == "%64"
    assert nav.item(2).data(STATE_ROLE) == "success"
    nav.set_badge(2)
    assert nav.item(2).data(BADGE_ROLE) == ""
    assert nav.item(2).data(STATE_ROLE) == "neutral"


def test_set_done_swaps_icon(qtbot: QtBot) -> None:
    nav = StepNav()
    qtbot.addWidget(nav)
    nav.set_done(0, True)
    assert nav.item(0).data(ICON_ROLE) == "circle-check"
    assert nav.item(0).data(DONE_ROLE) is True
    nav.set_done(0, False)
    assert nav.item(0).data(ICON_ROLE) == STEPS[0][1]


def test_disabled_item_not_selectable_by_click(qtbot: QtBot) -> None:
    nav = StepNav()
    qtbot.addWidget(nav)
    nav.show()
    nav.setCurrentRow(0)
    item = nav.item(3)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
    rect = nav.visualItemRect(item)
    qtbot.mouseClick(nav.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert nav.currentRow() == 0


def test_qlistwidget_api_unchanged(qtbot: QtBot) -> None:
    nav = StepNav()
    qtbot.addWidget(nav)
    with qtbot.waitSignal(nav.currentRowChanged):
        nav.setCurrentRow(2)
    assert nav.currentRow() == 2


def test_preferred_width_grows_with_font_and_fits_badge(qtbot: QtBot) -> None:
    nav = StepNav()
    qtbot.addWidget(nav)
    widths = {}
    for size in (9, 18):
        font = QFont(nav.font())
        font.setPointSize(size)
        nav.setFont(font)
        nav.set_badge(1, "99.999")
        widths[size] = nav.preferred_width()
    assert widths[18] > widths[9]
    bold = QFont(nav.font())
    bold.setBold(True)
    metrics = QFontMetrics(bold)
    needed = metrics.horizontalAdvance("Metinleri Tara") + metrics.horizontalAdvance("99.999") + 18
    assert widths[18] > needed


def test_project_header_elides_long_name(qtbot: QtBot) -> None:
    header = ProjectHeader()
    qtbot.addWidget(header)
    header.setFixedWidth(150)
    header.show()
    name = "Çok uzun bir proje adı " * 4
    header.set_project(name, "Oyun · 0100ABCD · 1.0.2")
    assert header.name_label.text().endswith("…")
    assert len(header.name_label.text()) < len(name)
    assert header.name_label.toolTip() == name
    assert header.detail_label.isVisibleTo(header)
    header.set_project("Proje")
    assert header.name_label.text() == "Proje"
    assert not header.detail_label.isVisibleTo(header)


def _project(*, broken: bool = False) -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                "Dialogue.tsv",
                "0100",
                "unity",
                "base",
                (
                    TextEntry("d01", 0, "Hello there", ()),
                    TextEntry("d02", 1, "Press ⟦1⟧ now.", (ControlCode(b"\x0e\x05", "Kod 0x05"),)),
                    TextEntry("m01", 2, "Start", ()),
                ),
            )
        ]
    )
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [
            (rows["d01"].id, "Merhaba"),
            (rows["d02"].id, "Şimdi bas." if broken else "Şimdi ⟦1⟧ bas."),
        ],
        machine=True,
    )
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project(broken=True))
    w.show()
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _badge(w: MainWindow, step: int) -> str:
    return str(w.nav.item(step).data(BADGE_ROLE))


@pytest.mark.gui
def test_window_updates_badges(window: MainWindow) -> None:
    assert _badge(window, STEP_TRANSLATE) == "%33"  # 3 satırdan 1'i çevrili; Hatalı satır sayılmaz
    assert _badge(window, STEP_QA) == ""  # henüz denetlenmedi
    assert _badge(window, STEP_ADD) == ""
    window.sources = [
        SourceRecord(Path("oyun.nsp"), "base", "0100ABCD12340000", "0100ABCD12340000", 0, "1.0.0", "Oyun", 1)
    ]
    window._refresh_nav()
    assert _badge(window, STEP_ADD) == "1"
    assert window.nav.item(STEP_ADD).data(DONE_ROLE) is True
    window.run_checks()
    assert _badge(window, STEP_QA) == "1"  # eksik kontrol kodu hatası
    assert window.nav.item(STEP_QA).data(STATE_ROLE) == "danger"


@pytest.mark.gui
def test_translate_badge_follows_edits_made_through_the_table(qtbot: QtBot, window: MainWindow) -> None:
    assert _badge(window, STEP_TRANSLATE) == "%33"
    row = next(r for r in window.translate_page.model.rows if not r.translation)
    assert window.translate_page.model.apply([(row.id, "Başla")])
    qtbot.waitUntil(lambda: _badge(window, STEP_TRANSLATE) == "%67", timeout=3000)
    assert window.nav.item(STEP_TRANSLATE).data(DONE_ROLE) is False  # Hatalı satır varken adım tamamlanmış sayılmaz


@pytest.mark.gui
def test_new_project_resets_qa_badge_and_header(window: MainWindow) -> None:
    window.run_checks()
    assert _badge(window, STEP_QA) == "1"
    window.dirty = False
    window.new_project()
    assert _badge(window, STEP_QA) == ""
    assert _badge(window, STEP_TRANSLATE) == ""
    assert window.nav_header.name_label.text() == "Kaydedilmemiş proje"


@pytest.mark.gui
def test_scan_step_enabled_state_unchanged(window: MainWindow) -> None:
    assert not (window.nav.item(STEP_SCAN).flags() & Qt.ItemFlag.ItemIsEnabled)
    assert window.nav.item(STEP_TRANSLATE).flags() & Qt.ItemFlag.ItemIsEnabled
    window.nav.setCurrentRow(STEP_TRANSLATE)
    assert window.pages.currentIndex() == STEP_TRANSLATE


@pytest.mark.gui
def test_nav_width_follows_font_size(window: MainWindow) -> None:
    before = window.nav_column.width()
    window._set_font_size(18)
    assert window.nav_column.width() > before
    window._set_font_size(10)
