"""Kontrol Et sekme çubuğu: karolar, seçim, rozetler ve erişilebilir adlar."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import QaIssue
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.qa_tabbar import TILE_SIZE
from nxceviri.gui.tab_badges import TONE_DANGER, TONE_SUCCESS, TONE_WARNING

pytestmark = pytest.mark.gui

TITLES = ["Sorunlar", "Sığdırma", "Font ve harfler", "Grafik"]


def _row(i: int) -> TranslationRow:
    return TranslationRow(i, "f", f"k{i}", "Hello", "Merhaba.", "machine", "", (), None)


@pytest.fixture
def page(qtbot: QtBot) -> QaPage:
    p = QaPage()
    qtbot.addWidget(p)
    p.resize(1400, 800)
    p.show()
    return p


def _badge(page: QaPage, index: int) -> tuple[str, str, str] | None:
    badge = page.tab_bar.tile(index).badge
    return None if badge is None else (badge.tone, badge.text, badge.glyph)


def test_tiles_exist_with_label_size_and_exclusive_selection(page: QaPage) -> None:
    tiles = page.tab_bar.tiles()
    assert [t.title for t in tiles] == TITLES
    for tile in tiles:
        assert isinstance(tile, QAbstractButton)
        assert tile.isCheckable()
        assert tile.size() == TILE_SIZE
        assert tile.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert tile.accessibleName() == tile.title
    assert [t.isChecked() for t in tiles] == [True, False, False, False]
    assert not page.tabs.tabBar().isVisibleTo(page)  # eski şerit gizli; karolar onun yerini tutar


def test_clicking_tile_switches_page_and_back(qtbot: QtBot, page: QaPage) -> None:
    shown: list[str] = []
    page.fit_tab_shown.connect(lambda: shown.append("fit"))
    page.graphics_tab_shown.connect(lambda: shown.append("graphics"))
    qtbot.mouseClick(page.tab_bar.tile(1), Qt.MouseButton.LeftButton)
    assert page.tabs.currentIndex() == 1
    assert [t.isChecked() for t in page.tab_bar.tiles()] == [False, True, False, False]
    qtbot.mouseClick(page.tab_bar.tile(3), Qt.MouseButton.LeftButton)
    assert page.tabs.currentIndex() == 3
    assert shown == ["fit", "graphics"]
    page.tabs.setCurrentIndex(2)  # kodla geçiş de karoyu eşler
    assert [t.isChecked() for t in page.tab_bar.tiles()] == [False, False, True, False]


def test_no_badges_before_anything_ran(page: QaPage) -> None:
    assert [_badge(page, i) for i in range(4)] == [None] * 4


def test_issues_badge_counts_errors_and_warnings(page: QaPage) -> None:
    issues = [
        QaIssue(1, "k1", "placeholder", "error", "kod"),
        QaIssue(2, "k2", "spaces", "warning", "boşluk"),
        QaIssue(3, "k3", "spelling", "info", "yazım"),  # bilgi sayılmaz
    ]
    page.show_issues(issues, [_row(1), _row(2), _row(3)])
    assert _badge(page, 0) == (TONE_DANGER, "2", "")
    assert page.tab_bar.tile(0).accessibleName() == "Sorunlar, 2 bulgu"
    many = [QaIssue(i, f"k{i}", "spaces", "warning", "boşluk") for i in range(1, 2224)]
    page.show_issues(many, [_row(i) for i in range(1, 2224)])
    assert _badge(page, 0) == (TONE_DANGER, "2,2B", "")
    assert page.tab_bar.tile(0).accessibleName() == "Sorunlar, 2.223 bulgu"
    page.show_issues([QaIssue(1, "k1", "untranslated", "info", "çevrilmedi")], [_row(1)])
    assert _badge(page, 0) is None
    page.reset()
    assert _badge(page, 0) is None


def test_fit_badge_counts_overflow_rows(page: QaPage) -> None:
    page.fit_enabled.setChecked(True)
    issues = [
        QaIssue(1, "k1", "line_too_long", "warning", "uzun"),
        QaIssue(1, "k1", "page_too_tall", "warning", "uzun"),
        QaIssue(2, "k2", "line_too_long", "warning", "uzun"),
    ]
    page.show_issues(issues, [_row(1), _row(2)])
    assert _badge(page, 1) == (TONE_WARNING, "2", "")
    assert page.tab_bar.tile(1).accessibleName() == "Sığdırma, 2 satır taşıyor"
    page.show_issues([], [_row(1)])
    assert _badge(page, 1) is None


def test_font_badge_states(page: QaPage) -> None:
    page.show_font_report(None, "")
    assert _badge(page, 2) is None  # taranmadı
    page.show_font_report(None, "ğş")
    assert _badge(page, 2) == (TONE_DANGER, "!", "")
    assert page.tab_bar.tile(2).accessibleName() == "Font ve harfler, eksik harf var: ğ ş"
    page.show_font_report(None, "ğş", [("Eklenti", "Fontları kendisi yönetir.")])
    badge = page.tab_bar.tile(2).badge
    assert badge is not None
    assert (badge.tone, badge.glyph) == (TONE_SUCCESS, "check")


def test_graphics_badge_states(page: QaPage) -> None:
    page.set_graphics_status(None)
    assert _badge(page, 3) is None
    page.set_graphics_status((0, 0))
    assert _badge(page, 3) == (TONE_SUCCESS, "", "brush")
    page.set_graphics_status((2, 1))
    assert _badge(page, 3) == (TONE_DANGER, "", "brush")
    assert page.tab_bar.tile(3).accessibleName() == "Grafik, 3 resim çevrilmemiş ya da sorunlu"
    page.set_graphics_status(None)
    assert _badge(page, 3) is None


def test_tiles_paint_without_error(page: QaPage) -> None:
    page.show_issues([QaIssue(1, "k1", "placeholder", "error", "kod")], [_row(1)])
    page.set_graphics_status((1, 0))
    page.show_font_report(None, "ğ")
    for tile in page.tab_bar.tiles():
        assert not tile.grab().isNull()
