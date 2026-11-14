"""Kontrol Et → Sorunlar: bulguların üç satırlık kart satırı olarak gösterilmesi (rol verisi, sabit yükseklik, ipucu,
çift tıklama davranışı)."""

from __future__ import annotations

import html

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QStyle, QStyleOptionViewItem
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import KIND_LABELS, QaIssue
from nxceviri.gui.issue_rows import (
    ROLE_NUMBER,
    ROLE_SEVERITY,
    ROLE_SOURCE,
    ROLE_TRANSLATION,
    IssueRowDelegate,
    IssueRowView,
    line_tops,
    one_line,
    row_height,
)
from nxceviri.gui.qa_page import EDIT_HINT, OPEN_HINT, QaPage
from nxceviri.gui.theme import current_tokens

pytestmark = pytest.mark.gui

LONG = "Çok uzun bir metin, satıra sığmayacak kadar uzun ve sonunda üç nokta ile kısalmalı. " * 8


def _row(i: int, source: str = "Hello", translation: str = "Merhaba.") -> TranslationRow:
    return TranslationRow(i, "f", f"k{i}", source, translation, "machine", "", (), None)


@pytest.fixture
def page(qtbot: QtBot) -> QaPage:
    p = QaPage()
    qtbot.addWidget(p)
    p.resize(1300, 800)
    p.show()
    issues = [
        QaIssue(1, "k1", "placeholder", "error", "Kod eksik"),
        QaIssue(2, "k2", "spaces", "warning", "Boşluk farklı"),
        QaIssue(3, "k3", "spelling", "info", "Yazım", ("x",)),
    ]
    rows = [_row(1, "Press ⟦1⟧A⟦2⟧", "⟦1⟧A tuşuna basın"), _row(2, LONG, LONG), _row(3)]
    p.model.number_of = lambda row_id: row_id * 10
    p.show_issues(issues, rows)
    p.kind_list.select_kinds([])  # bilgiler varsayılan gizli
    return p


def test_row_carries_description_source_translation_and_number(page: QaPage) -> None:
    index = page.proxy.index(0, 0)
    assert index.data() == "Kod eksik"  # açıklama
    assert index.data(ROLE_SOURCE) == "Press ⟦1⟧A⟦2⟧"  # kontrol kodları olduğu gibi
    assert index.data(ROLE_TRANSLATION) == "⟦1⟧A tuşuna basın"
    assert index.data(ROLE_NUMBER) == 10
    assert index.data(ROLE_SEVERITY) == "error"
    assert page.proxy.index(1, 0).data(ROLE_SEVERITY) == "warning"


def test_number_is_zero_without_a_number_source(qtbot: QtBot) -> None:
    p = QaPage()
    qtbot.addWidget(p)
    assert p.model.number_of is None
    p.show_issues([QaIssue(1, "k1", "spaces", "warning", "x")], [_row(1)])
    assert p.proxy.index(0, 0).data(ROLE_NUMBER) == 0  # numara uydurulmaz


def test_view_is_a_single_column_list_with_fixed_row_height(qtbot: QtBot, page: QaPage) -> None:
    table = page.table
    assert isinstance(table, IssueRowView)
    assert page.model.columnCount() == 1
    assert not table.horizontalHeader().isVisible()
    assert table.verticalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.Fixed
    expected = row_height(table.fontMetrics())
    assert table.verticalHeader().defaultSectionSize() == expected
    qtbot.wait(30)
    # Çok uzun metinli satır da, kısa metinli satır da aynı yüksekliktedir (içerikten ölçülmez).
    assert {table.rowHeight(r) for r in range(page.proxy.rowCount())} == {expected}
    assert not table.showGrid()
    assert not table.alternatingRowColors()
    assert table.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection


def test_row_height_follows_font(page: QaPage) -> None:
    font = page.table.font()
    font.setPointSizeF(font.pointSizeF() + 4)
    page.table.setFont(font)
    assert page.table.verticalHeader().defaultSectionSize() == row_height(page.table.fontMetrics())


def test_tooltip_has_kind_full_texts_and_hints(page: QaPage) -> None:
    tip = page.proxy.index(1, 0).data(Qt.ItemDataRole.ToolTipRole)
    assert KIND_LABELS["spaces"] in tip
    assert "Orijinal:" in tip
    assert "Çeviri:" in tip
    assert LONG[:200] in tip  # tam metin ipucunda
    assert html.escape(OPEN_HINT) in tip
    assert html.escape(EDIT_HINT) in tip


def test_accessible_text_has_severity_kind_and_description(page: QaPage) -> None:
    text = page.proxy.index(0, 0).data(Qt.ItemDataRole.AccessibleTextRole)
    assert text == f"Hata, {KIND_LABELS['placeholder']}: Kod eksik"


def test_one_line_flattens_newlines_and_bounds_length() -> None:
    assert one_line("a\nb") == "a ⏎ b"
    assert len(one_line("x" * 5000)) <= 300


def test_long_texts_are_elided_not_wrapped(page: QaPage) -> None:
    """Uzun metin satırdan taşmaz: çizilen görüntüde satırın alt dolgusu (son metin satırının altı) boştur."""
    delegate = page.table.itemDelegate()
    assert delegate is not None
    height, width = page.table.verticalHeader().defaultSectionSize(), 500
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    option = QStyleOptionViewItem()
    option.widget = page.table
    option.palette = page.table.palette()
    option.font = page.table.font()
    option.fontMetrics = page.table.fontMetrics()
    option.rect = image.rect()
    option.state = QStyle.StateFlag.State_Enabled
    painter = QPainter(image)
    delegate.paint(painter, option, page.proxy.index(1, 0))  # her iki metin de çok uzun
    painter.end()
    _first, _second, third = line_tops(image.rect(), page.table.fontMetrics().height())
    below = third + page.table.fontMetrics().height() + 2
    for y in range(below, height - 2):
        assert {image.pixel(QPoint(x, y)) for x in range(60, width - 60)} == {image.pixel(QPoint(60, y))}
    right_edge = {image.pixel(QPoint(x, third + 4)) for x in range(width - 12, width)}
    assert len(right_edge) == 1  # sağ dolguya taşan yazı yok


def _center_of(page: QaPage, row: int, part: str) -> QPoint:
    rect = page.table.visualRect(page.proxy.index(row, 0))
    _first, _second, third = line_tops(rect, page.table.fontMetrics().height())
    y = {"description": rect.top() + 12, "translation": third + page.table.fontMetrics().height() // 2}[part]
    return QPoint(rect.left() + 200, y)


def _double_click(qtbot: QtBot, page: QaPage, pos: QPoint) -> None:
    """Qt çift tıklamayı, aynı satıra önce basılmışsa bildirir: önce tek tıklama."""
    qtbot.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    qtbot.mouseDClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=pos)


def test_double_click_on_description_opens_row_in_translate_page(qtbot: QtBot, page: QaPage) -> None:
    opened: list[int] = []
    page.open_row.connect(opened.append)
    _double_click(qtbot, page, _center_of(page, 0, "description"))
    assert set(opened) == {1}  # doubleClicked ve activated birlikte gelebilir (boş olamaz)
    assert page.table.state() != QAbstractItemView.State.EditingState


def test_double_click_on_translation_edits_in_place(qtbot: QtBot, page: QaPage) -> None:
    opened: list[int] = []
    edited: list[tuple[int, str]] = []
    page.open_row.connect(opened.append)
    page.translation_edited.connect(lambda i, t: edited.append((i, t)))
    _double_click(qtbot, page, _center_of(page, 0, "translation"))
    assert page.table.state() == QAbstractItemView.State.EditingState
    assert opened == []  # çeviri satırında çift tıklama düzenler, çeviri ekranını açmaz
    assert edited == []  # metin değişmeden sinyal yayılmaz


def test_f2_edits_and_enter_opens(qtbot: QtBot, page: QaPage) -> None:
    opened: list[int] = []
    page.open_row.connect(opened.append)
    page.table.setCurrentIndex(page.proxy.index(1, 0))
    page.table.activated.emit(page.proxy.index(1, 0))
    assert opened == [2]
    qtbot.keyClick(page.table, Qt.Key.Key_F2)
    assert page.table.state() == QAbstractItemView.State.EditingState


def _paint_to_image(page: QaPage, row: int, *, selected: bool = False, width: int = 500) -> QImage:
    delegate = page.table.itemDelegate()
    assert delegate is not None
    height = page.table.verticalHeader().defaultSectionSize()
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    option = QStyleOptionViewItem()
    option.widget = page.table
    option.palette = page.table.palette()
    option.font = page.table.font()
    option.fontMetrics = page.table.fontMetrics()
    option.rect = image.rect()
    option.state = QStyle.StateFlag.State_Enabled | (
        QStyle.StateFlag.State_Selected if selected else QStyle.StateFlag(0)
    )
    painter = QPainter(image)
    delegate.paint(painter, option, page.proxy.index(row, 0))
    painter.end()
    return image


def test_codes_are_drawn_as_chips_not_plain_brackets(page: QaPage) -> None:
    """Kodlu metin çeviri tablosundaki gibi çip olarak çizilir: HTML'de `⟦` kalmaz, çip simgesi ve numarası olur."""
    delegate = page.table.itemDelegate()
    assert isinstance(delegate, IssueRowDelegate)
    markup = delegate.line_html(page.proxy.index(0, 0), ROLE_SOURCE, selected=False)
    assert "⟦" not in markup
    assert "font-weight:600" in markup  # çip biçimi
    assert "Press" in markup
    assert delegate.line_html(page.proxy.index(2, 0), ROLE_SOURCE, selected=False) == ""  # kodsuz metin belge kurmaz


def test_chip_line_paints_chip_background_in_both_states(page: QaPage) -> None:
    tokens = current_tokens()
    chip_bg = QColor(tokens["selection"]).rgb()
    plain_bg = QColor(tokens["surface2"]).rgb()
    _first, _second, third = line_tops(QRect(0, 0, 500, 100), page.table.fontMetrics().height())
    for selected in (False, True):
        image = _paint_to_image(page, 0, selected=selected)
        band = {
            image.pixel(x, y) for y in range(third, third + page.table.fontMetrics().height()) for x in range(40, 200)
        }
        assert chip_bg in band or selected  # seçiliyken zemin zaten aynı renktir
        assert plain_bg not in band or selected
        assert len(band) > 2  # metin gerçekten çizildi


def test_chip_line_does_not_spill_below_row(page: QaPage) -> None:
    delegate = page.table.itemDelegate()
    assert isinstance(delegate, IssueRowDelegate)
    source = "⟦1⟧ " + "uzun metin " * 60 + "⟦2⟧"
    page.model.rows[2] = _row(2, source, source)
    image = _paint_to_image(page, 1)
    height = image.height()
    _first, _second, third = line_tops(image.rect(), page.table.fontMetrics().height())
    below = third + page.table.fontMetrics().height() + 2
    for y in range(below, height - 2):
        assert {image.pixel(QPoint(x, y)) for x in range(60, 440)} == {image.pixel(QPoint(60, y))}
    assert len({image.pixel(QPoint(x, third + 4)) for x in range(488, 500)}) == 1  # sağ dolguya taşmaz


def test_line_documents_are_cached(page: QaPage) -> None:
    delegate = page.table.itemDelegate()
    assert isinstance(delegate, IssueRowDelegate)
    _paint_to_image(page, 0)
    size = delegate.cache_size()
    assert size > 0
    _paint_to_image(page, 0)
    assert delegate.cache_size() == size
