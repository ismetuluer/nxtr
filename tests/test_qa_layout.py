"""Kontrol Et sayfasının tablo yerleşimi: başlıklar kırpılmaz, sütunlar içeriğine göre, başlık hizası içerikle aynı."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QHeaderView, QTableView
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_ERROR, SEVERITY_WARNING, QaIssue
from nxceviri.core.qa.fonts import KIND_TTF, FontInfo, FontReport
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.gui.qa_page import COL_KIND, COL_SEVERITY, QaPage
from nxceviri.gui.theme import ThemeMode, apply_theme

pytestmark = pytest.mark.gui

LATIN = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_LEFT = int(Qt.AlignmentFlag.AlignLeft)
_RIGHT = int(Qt.AlignmentFlag.AlignRight)


@pytest.fixture
def page(qtbot: QtBot) -> QaPage:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    apply_theme(app, ThemeMode.LIGHT)
    widget = QaPage()
    qtbot.addWidget(widget)
    widget.resize(1100, 700)
    widget.show()
    return widget


def _row(row_id: int, key: str, source: str) -> TranslationRow:
    return TranslationRow(row_id, "a.tsv", key, source, "", "untranslated", "", (), None, f"Grup/{key}")


def _settle(qtbot: QtBot, view: QTableView) -> None:
    qtbot.wait(30)
    QApplication.processEvents()
    assert view.isVisible()


def _bold(view: QTableView) -> QFontMetrics:
    font = QFont(view.horizontalHeader().font())
    font.setBold(True)
    return QFontMetrics(font)


# --- A: sınır tablosu başlıkları kırpılmaz --------------------------------------------------------


def test_limits_headers_fit_their_columns(qtbot: QtBot, page: QaPage) -> None:
    page.tabs.setCurrentIndex(1)
    rows = [_row(1, "menu_a", "kısa"), _row(2, "talk_1", "uzun bir konuşma satırı")]
    page.limits.set_data(rows, FitConfig(), {"Grup": FitRules(20, 2)})
    view = page.limits.view
    _settle(qtbot, view)
    header = view.horizontalHeader()
    metrics = _bold(view)
    for col in range(header.count()):
        text = str(view.model().headerData(col, Qt.Orientation.Horizontal))
        assert metrics.horizontalAdvance(text) + 16 <= header.sectionSize(col), text


def test_limits_last_column_does_not_take_all_free_width(qtbot: QtBot, page: QaPage) -> None:
    page.tabs.setCurrentIndex(1)
    page.limits.set_data([_row(1, "menu_a", "kısa")], FitConfig(), {})
    view = page.limits.view
    _settle(qtbot, view)
    header = view.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
    assert header.sectionSize(4) < header.sectionSize(0)


def test_limits_headers_follow_content_alignment(page: QaPage) -> None:
    page.limits.set_data([_row(1, "menu_a", "kısa")], FitConfig(), {})
    model = page.limits.view.model()
    role = Qt.ItemDataRole.TextAlignmentRole
    horizontal = Qt.Orientation.Horizontal
    assert int(model.headerData(0, horizontal, role)) & _LEFT
    for col in range(1, 5):
        assert int(model.headerData(col, horizontal, role)) & _RIGHT
        assert int(model.index(0, col).data(role)) & _RIGHT


# --- B: kapalıyken tek satır ----------------------------------------------------------------------


def test_fit_result_hidden_while_fit_is_off(qtbot: QtBot, page: QaPage) -> None:
    page.tabs.setCurrentIndex(1)
    page.show_issues([], [])
    assert not page.fit_enabled.isChecked()
    assert not page.fit_result.isVisibleTo(page)
    page.fit_enabled.setChecked(True)
    assert page.fit_result.isVisibleTo(page)
    page.fit_enabled.setChecked(False)
    assert not page.fit_result.isVisibleTo(page)


# --- C: sınır tablosu kalan yüksekliği doldurur ---------------------------------------------------


def test_limits_table_fills_remaining_height(qtbot: QtBot, page: QaPage) -> None:
    page.tabs.setCurrentIndex(1)
    page.resize(1100, 1000)
    qtbot.wait(30)
    scroll = page.tabs.currentWidget()
    assert scroll is not None
    bottom = page.limits.mapTo(scroll, page.limits.rect().bottomLeft()).y()
    assert bottom >= scroll.height() - 80  # kart sekmenin altına kadar uzar; altta boş bant kalmaz


# --- D: bulgu tablosu ------------------------------------------------------------------------------


def _issues() -> tuple[list[QaIssue], list[TranslationRow]]:
    issues = [
        QaIssue(1, "a", "placeholder", SEVERITY_ERROR, "Kod eksik"),
        QaIssue(2, "b", "end_punctuation", SEVERITY_WARNING, "Sonda orijinalde olmayan bir nokta var"),
    ]
    return issues, [_row(1, "a", "x"), _row(2, "b", "y")]


def test_severity_column_is_icon_only(qtbot: QtBot, page: QaPage) -> None:
    page.show_issues(*_issues())
    _settle(qtbot, page.table)
    assert page.table.columnWidth(COL_SEVERITY) <= 48
    model = page.proxy
    for row, label in ((0, "Hata"), (1, "Uyarı")):
        index = model.index(row, COL_SEVERITY)
        assert index.data(Qt.ItemDataRole.DisplayRole) == ""
        assert not index.data(Qt.ItemDataRole.DecorationRole).isNull()
        assert label in index.data(Qt.ItemDataRole.ToolTipRole)
        assert index.data(Qt.ItemDataRole.AccessibleTextRole) == label


def test_severity_sort_still_orders_by_label(qtbot: QtBot, page: QaPage) -> None:
    page.show_issues(*_issues())
    page.proxy.sort(COL_SEVERITY, Qt.SortOrder.DescendingOrder)
    assert page.proxy.index(0, COL_SEVERITY).data(Qt.ItemDataRole.AccessibleTextRole) == "Uyarı"
    page.proxy.sort(COL_SEVERITY, Qt.SortOrder.AscendingOrder)
    assert page.proxy.index(0, COL_SEVERITY).data(Qt.ItemDataRole.AccessibleTextRole) == "Hata"


def test_kind_column_fits_longest_kind(qtbot: QtBot, page: QaPage) -> None:
    page.show_issues(*_issues())
    _settle(qtbot, page.table)
    metrics = page.table.fontMetrics()
    longest = max(metrics.horizontalAdvance(name) for name in KIND_LABELS.values())
    assert longest + 16 <= page.table.columnWidth(COL_KIND)


def test_issue_headers_left_aligned(page: QaPage) -> None:
    for col in range(page.model.columnCount()):
        value = page.model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.TextAlignmentRole)
        assert int(value) & _LEFT or col == COL_SEVERITY


# --- E: font tablosu -------------------------------------------------------------------------------


def _font_report() -> FontReport:
    long_name = "Cok/Uzun/Bir/Klasor/Yolu/ornek_font_dosyasi_adi_cok_uzun.ttf"
    return FontReport([FontInfo("Ornek", long_name, KIND_TTF, LATIN, False)])


def test_font_table_modes_and_tooltips(qtbot: QtBot, page: QaPage) -> None:
    page.tabs.setCurrentIndex(2)
    page.show_font_report(_font_report(), "")
    _settle(qtbot, page.font_table)
    header = page.font_table.horizontalHeader()
    assert header.sectionResizeMode(3) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(4) != QHeaderView.ResizeMode.Stretch
    assert header.sectionSize(4) <= 200
    assert page.font_table.textElideMode() == Qt.TextElideMode.ElideMiddle
    for col in range(5):
        item = page.font_table.item(0, col)
        assert item is not None
        assert item.toolTip()
    advice = page.font_table.item(0, 3)
    assert advice is not None
    assert advice.text() in advice.toolTip()
    path_item = page.font_table.item(0, 4)
    assert path_item is not None
    assert path_item.toolTip() == "Cok/Uzun/Bir/Klasor/Yolu/ornek_font_dosyasi_adi_cok_uzun.ttf"


def test_font_headers_left_aligned(page: QaPage) -> None:
    page.show_font_report(_font_report(), "")
    for col in range(5):
        item = page.font_table.horizontalHeaderItem(col)
        assert item is not None
        assert int(item.textAlignment()) & _LEFT
