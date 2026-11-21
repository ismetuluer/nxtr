"""Konsol temalarında adım işaretleri (daire, küp, düğüm, imleç) ve Gece Mavisi'nin üst gezinmesi."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLayout
from pytestqt.qtbot import QtBot

from nxceviri.gui.console_themes import CIFT_KUMANDA, CONSOLE_THEMES, extra_qss
from nxceviri.gui.main_window import STEP_QA, STEP_TRANSLATE, MainWindow
from nxceviri.gui.step_markers import marker_slot, paint_marker
from nxceviri.gui.step_nav import BADGE_ROLE, StepNav
from nxceviri.gui.theme import (
    DEFAULT_PALETTE,
    TOKENS,
    ThemeMode,
    apply_theme,
    current_style,
    current_tokens,
    palette_style,
)
from nxceviri.gui.theme_style import DEFAULT_STYLE, STEP_MARKERS
from tests.test_console_themes import themed_app  # noqa: F401
from tests.test_statusbar import _make_window, _project

MARKER_THEMES = {
    "Çift Kumanda": "knob",
    "Mor Küp": "cube",
    "Yeşil Işık": "node",
    "Piksel Gri": "cursor",
    "Gece Mavisi": "icon",
}


def _top(window: MainWindow) -> bool:
    """Üst gezinme etkin mi (mypy'nin art arda iddiaları ölü kod saymaması için işlev üzerinden okunur)."""
    return window.nav_is_top


def _flag(value: bool) -> bool:
    return value


def _column(window: MainWindow) -> QLayout:
    layout = window.nav_column.layout()
    assert layout is not None
    return layout


def _qss(name: str) -> str:
    style, layer = CONSOLE_THEMES[name]
    return extra_qss({**TOKENS[style.scheme or "dark"], **layer}, style, 14)


def test_markers_chosen_per_theme() -> None:
    for name, marker in MARKER_THEMES.items():
        assert CONSOLE_THEMES[name][0].step_marker == marker
    assert DEFAULT_STYLE.step_marker == "icon"
    assert CONSOLE_THEMES["Gece Mavisi"][0].nav_position == "top"
    assert {st.nav_position for st, _ in CONSOLE_THEMES.values()} == {"side", "top"}
    with pytest.raises(ValueError, match="adım işareti"):
        replace(DEFAULT_STYLE, step_marker="yok")


@pytest.mark.parametrize("kind", [m for m in STEP_MARKERS if m != "icon"])
@pytest.mark.parametrize("state", ["done", "current", "pending"])
def test_marker_paints_pixels_in_every_state(kind: str, state: str, themed_app: QApplication) -> None:  # noqa: F811
    style = replace(DEFAULT_STYLE, step_marker=kind)
    image = QImage(80, 40, QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    paint_marker(
        painter,
        style,
        QPoint(20, 20),
        state,
        3,
        done=state == "done",
        ink=QColor("#ffffff"),
        ground=QColor("#000000"),
        accent=QColor("#ffd95c"),
        muted=QColor("#888888"),
        font=themed_app.font(),
    )
    painter.end()
    drawn = sum(image.pixelColor(x, y) != QColor("#000000") for x in range(80) for y in range(40))
    assert drawn >= 3
    assert marker_slot(style) >= 12


def test_default_theme_slot_is_icon_size(themed_app: QApplication) -> None:  # noqa: F811
    apply_theme(themed_app, ThemeMode.LIGHT, palette=DEFAULT_PALETTE)
    assert current_style().step_marker == "icon"
    assert marker_slot(current_style()) == 18


def _grab(nav: StepNav) -> QImage:
    return nav.viewport().grab().toImage()


def test_marker_theme_repaints_nav_differently(qtbot: QtBot, themed_app: QApplication) -> None:  # noqa: F811
    nav = StepNav()
    qtbot.addWidget(nav)
    nav.resize(220, 300)
    nav.show()
    nav.setCurrentRow(2)
    apply_theme(themed_app, ThemeMode.LIGHT, palette=DEFAULT_PALETTE)
    before = _grab(nav)
    nav.set_done(0, True)
    for name in ("Çift Kumanda", "Mor Küp", "Yeşil Işık", "Piksel Gri"):
        apply_theme(themed_app, ThemeMode.LIGHT, palette=name)
        assert _grab(nav) != before
        nav.set_collapsed(True)  # daraltılmış çubuk her türde çalışır
        assert _grab(nav).width() > 0
        nav.set_collapsed(False)


def test_node_wire_reaches_between_items(qtbot: QtBot, themed_app: QApplication) -> None:  # noqa: F811
    apply_theme(themed_app, ThemeMode.LIGHT, palette="Yeşil Işık")
    nav = StepNav()
    qtbot.addWidget(nav)
    nav.resize(220, 300)
    nav.show()
    nav.setCurrentRow(4)
    nav.set_done(0, True)
    image = _grab(nav)
    gap_y = nav.visualItemRect(nav.item(0)).bottom()  # birinci ile ikinci öğenin arası
    accent = QColor(current_tokens()["accent"])
    assert any(image.pixelColor(x, gap_y) == accent for x in range(10, 40))


def test_disabled_menu_items_dimmer_in_console_themes() -> None:
    for name in CONSOLE_THEMES:
        assert "QMenu::item:disabled" in _qss(name), name
    assert extra_qss({}, DEFAULT_STYLE, 14) == ""


def test_green_row_bar_only_on_tree_and_list() -> None:
    qss = _qss("Yeşil Işık")
    assert "QTreeWidget::item:selected, QListWidget::item:selected { border-left: 2px solid" in qss
    assert "QTableView::item:selected, QTreeWidget::item:selected, QListWidget::item:selected { color" in qss


# --- Gece Mavisi: üst gezinme ---------------------------------------------------------------------


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path, themed_app: QApplication) -> Iterator[MainWindow]:  # noqa: F811
    w = _make_window(qtbot, tmp_path, _project())
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_gece_mavisi_moves_nav_to_top_and_back(window: MainWindow) -> None:
    nav = window.nav
    nav.setCurrentRow(STEP_QA)
    seen: list[int] = []
    nav.currentRowChanged.connect(seen.append)
    window._set_palette("Çift Kumanda")
    assert not _top(window)
    assert nav.parent() is window.nav_column
    window._set_palette("Gece Mavisi")
    assert _top(window)
    assert nav.parent() is window.nav_top
    assert window.nav_header.parent() is window.nav_top
    assert window.nav_top.isVisible()
    assert not window.nav_column.isVisible()
    assert _flag(nav.horizontal)
    assert nav.currentRow() == STEP_QA
    assert _column(window).indexOf(nav) == -1
    assert not window.menu_actions["view.nav"].isEnabled()
    nav.setCurrentRow(STEP_TRANSLATE)
    assert seen[-1] == STEP_TRANSLATE
    assert window.pages.currentIndex() == STEP_TRANSLATE
    window._set_palette("Yeşil Işık")
    assert not _top(window)
    assert not _flag(nav.horizontal)
    assert nav.parent() is window.nav_column
    assert window.nav_column.isVisible()
    assert not window.nav_top.isVisible()
    assert _column(window).indexOf(nav) == 1
    assert _column(window).indexOf(window.nav_header) == 0
    assert nav.currentRow() == STEP_TRANSLATE
    assert window.menu_actions["view.nav"].isEnabled()
    assert nav.count() == 5


def test_top_nav_keeps_badges_and_arrow_keys(window: MainWindow) -> None:
    window._set_palette("Gece Mavisi")
    nav = window.nav
    nav.set_badge(STEP_TRANSLATE, "%70", "neutral")
    assert nav.item(STEP_TRANSLATE).data(BADGE_ROLE) == "%70"
    # Hap dizisi sığar: listenin genişliği hapların toplamından küçük değildir.
    assert nav.width() >= sum(nav.visualItemRect(nav.item(i)).width() for i in range(nav.count()))
    nav.setCurrentRow(2)
    nav.setFocus()
    QTest.keyClick(nav, Qt.Key.Key_Right)
    assert nav.currentRow() == 3
    QTest.keyClick(nav, Qt.Key.Key_Left)
    assert nav.currentRow() == 2


def test_nav_collapse_preference_survives_top_mode(window: MainWindow) -> None:
    window.set_nav_collapsed(True, animate=False)
    window._set_palette("Gece Mavisi")
    window.set_nav_collapsed(True, animate=False)  # üst kipte sessizce saklanır
    assert not _flag(window.nav.collapsed)
    window._set_palette(CIFT_KUMANDA)
    assert _flag(window.nav.collapsed)
    assert not window.nav_header.isVisible()


def test_startup_in_gece_mavisi_builds_top_nav(qtbot: QtBot, tmp_path: Path, themed_app: QApplication) -> None:  # noqa: F811
    apply_theme(themed_app, ThemeMode.DARK, palette="Gece Mavisi")
    assert palette_style("Gece Mavisi").nav_position == "top"
    w = _make_window(qtbot, tmp_path, None)
    assert _top(w)
    assert w.nav.parent() is w.nav_top
    w.dirty = False
    w.close()
