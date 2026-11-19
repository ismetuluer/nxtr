"""Kontrol Et → Sorunlar: soldaki gruplu tür listesi ve yeniden kurulan bulgu tablosu."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QListWidgetItem, QStyle, QStyleOptionViewItem
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import KIND_LABELS, QaIssue
from nxceviri.gui.issue_kinds import KIND_GROUPS, OTHER_GROUP, KindList
from nxceviri.gui.qa_page import QaPage

pytestmark = pytest.mark.gui

_NO_MOD = Qt.KeyboardModifier.NoModifier
_CTRL = Qt.KeyboardModifier.ControlModifier

_EXPECTED_GROUPS = [
    (
        "Oyunu bozabilir",
        ["placeholder", "code_position", "newlines", "markup", "missing_markup", "identifier", "protected", "glyph"],
    ),
    ("Ekrana sığmayabilir", ["max_length", "line_too_long", "page_too_tall", "overflow", "bad_break", "too_wide"]),
    (
        "Dil ve tutarlılık",
        ["glossary", "term", "inconsistent", "suspicious", "code_order", "spelling", "profanity", "untranslated"],
    ),
    (
        "Küçük düzeltmeler",
        [
            "ascii_turkish",
            "end_punctuation",
            "spaces",
            "double_space",
            "repeated_word",
            "extra_dots",
            "space_before_punct",
        ],
    ),
]


def _row(i: int) -> TranslationRow:
    return TranslationRow(i, "f", f"k{i}", "Hello", "Merhaba.", "machine", "", (), None)


def _issues(*kinds: str) -> tuple[list[QaIssue], list[TranslationRow]]:
    issues = []
    for n, kind in enumerate(kinds, 1):
        severity = "error" if kind in ("placeholder", "glyph") else "warning"
        issues.append(QaIssue(n, f"k{n}", kind, severity, f"{kind} iletisi"))
    return issues, [_row(n) for n in range(1, len(kinds) + 1)]


@pytest.fixture
def page(qtbot: QtBot) -> QaPage:
    p = QaPage()
    qtbot.addWidget(p)
    p.resize(1400, 800)
    p.show()
    issues, rows = _issues("placeholder", "spaces", "spaces", "line_too_long", "page_too_tall", "glossary")
    p.show_issues(issues, rows)
    return p


def _click(qtbot: QtBot, lst: KindList, item: QListWidgetItem, mod: Qt.KeyboardModifier = _NO_MOD) -> None:
    rect = lst.visualItemRect(item)
    qtbot.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton, mod, rect.center())


def _shown(lst: KindList) -> list[str]:
    return [lst.item(i).text() for i in range(lst.count())]


# --- gruplar ---------------------------------------------------------------------------------------


def test_group_table_matches_spec_and_covers_every_kind() -> None:
    assert [(title, list(kinds)) for title, kinds in KIND_GROUPS] == _EXPECTED_GROUPS
    mapped = [k for _t, kinds in KIND_GROUPS for k in kinds]
    assert len(mapped) == len(set(mapped))
    assert set(mapped) == set(KIND_LABELS)  # çekirdekteki her tür bir gruba bağlı


def test_list_shows_groups_in_severity_order_with_counts(page: QaPage) -> None:
    lst = page.kind_list
    assert _shown(lst) == [
        "Tüm bulgular",
        "Oyunu bozabilir",
        KIND_LABELS["placeholder"],
        "Ekrana sığmayabilir",
        KIND_LABELS["line_too_long"],
        KIND_LABELS["page_too_tall"],
        "Dil ve tutarlılık",
        KIND_LABELS["glossary"],
        "Küçük düzeltmeler",
        KIND_LABELS["spaces"],
    ]
    assert lst.count_of("spaces") == 2
    assert lst.total() == 6
    assert lst.visible_kinds() == ["placeholder", "line_too_long", "page_too_tall", "glossary", "spaces"]


def test_kinds_without_findings_and_empty_groups_are_not_listed(page: QaPage) -> None:
    lst = page.kind_list
    assert "Oyunu bozabilir" in _shown(lst)
    page.show_issues(*_issues("spaces"))
    assert _shown(lst) == ["Tüm bulgular", "Küçük düzeltmeler", KIND_LABELS["spaces"]]
    page.show_issues([], [])
    assert _shown(lst) == ["Tüm bulgular"]
    assert lst.total() == 0


def test_unknown_kind_falls_into_other_group(page: QaPage) -> None:
    page.show_issues(*_issues("yeni_tur", "spaces"))
    assert _shown(page.kind_list)[-2:] == [OTHER_GROUP, "yeni_tur"]
    page.kind_list.select_kinds(["yeni_tur"])
    assert page.proxy.rowCount() == 1


def test_error_kinds_get_danger_marker_others_do_not(page: QaPage) -> None:
    assert page.kind_list.has_errors("placeholder")
    assert not page.kind_list.has_errors("spaces")


# --- seçim -----------------------------------------------------------------------------------------


def test_all_item_is_selected_by_default_and_table_unfiltered(page: QaPage) -> None:
    assert page.kind_list.selected_kinds() == frozenset()
    assert page.kind_list.all_item.isSelected()
    assert page.proxy.rowCount() == 6


def test_clicking_one_kind_filters_table_to_it(qtbot: QtBot, page: QaPage) -> None:
    lst = page.kind_list
    _click(qtbot, lst, lst.kind_item("spaces"))
    assert lst.selected_kinds() == {"spaces"}
    assert page.proxy.rowCount() == 2
    _click(qtbot, lst, lst.kind_item("glossary"))  # tek seçim: öncekinin yerine geçer
    assert lst.selected_kinds() == {"glossary"}
    assert page.proxy.rowCount() == 1
    assert not lst.all_item.isSelected()


def test_ctrl_click_selects_several_kinds(qtbot: QtBot, page: QaPage) -> None:
    lst = page.kind_list
    _click(qtbot, lst, lst.kind_item("spaces"))
    _click(qtbot, lst, lst.kind_item("glossary"), _CTRL)
    assert lst.selected_kinds() == {"spaces", "glossary"}
    assert page.proxy.rowCount() == 3
    _click(qtbot, lst, lst.kind_item("spaces"), _CTRL)  # seçimi geri al
    assert lst.selected_kinds() == {"glossary"}
    _click(qtbot, lst, lst.kind_item("glossary"), _CTRL)  # hiçbiri kalmaz: süzgeç kalkar
    assert lst.selected_kinds() == frozenset()
    assert lst.all_item.isSelected()
    assert page.proxy.rowCount() == 6


def test_group_header_click_selects_every_kind_of_the_group(qtbot: QtBot, page: QaPage) -> None:
    lst = page.kind_list
    _click(qtbot, lst, lst.group_item("Ekrana sığmayabilir"))
    assert lst.selected_kinds() == {"line_too_long", "page_too_tall"}
    assert page.proxy.rowCount() == 2
    assert not lst.group_item("Ekrana sığmayabilir").isSelected()  # başlık kendisi vurgulanmaz
    assert lst.kind_item("line_too_long").isSelected()


def test_all_item_removes_the_filter(qtbot: QtBot, page: QaPage) -> None:
    lst = page.kind_list
    _click(qtbot, lst, lst.kind_item("spaces"))
    _click(qtbot, lst, lst.all_item)
    assert lst.selected_kinds() == frozenset()
    assert lst.all_item.isSelected()
    assert not lst.kind_item("spaces").isSelected()
    assert page.proxy.rowCount() == 6


def test_keyboard_arrows_move_selection(qtbot: QtBot, page: QaPage) -> None:
    lst = page.kind_list
    _click(qtbot, lst, lst.kind_item("placeholder"))
    qtbot.keyClick(lst, Qt.Key.Key_Down)  # "Ekrana sığmayabilir" başlığı: grubun türlerini seçer
    assert lst.selected_kinds() == {"line_too_long", "page_too_tall"}
    qtbot.keyClick(lst, Qt.Key.Key_Down)
    assert lst.selected_kinds() == {"line_too_long"}
    assert page.proxy.rowCount() == 1


def test_selected_kind_dropped_when_it_disappears(qtbot: QtBot, page: QaPage) -> None:
    lst = page.kind_list
    _click(qtbot, lst, lst.kind_item("placeholder"))
    page.show_issues(*_issues("spaces", "glossary"))
    assert lst.selected_kinds() == frozenset()
    assert lst.all_item.isSelected()
    assert page.proxy.rowCount() == 2


def test_selection_survives_row_replacement(qtbot: QtBot, page: QaPage) -> None:
    lst = page.kind_list
    _click(qtbot, lst, lst.kind_item("spaces"))
    page.replace_row_issues(2, [QaIssue(2, "k2", "spaces", "warning", "boşluk")], _row(2))
    assert lst.selected_kinds() == {"spaces"}
    assert page.proxy.rowCount() == 2


def test_items_have_accessible_names(page: QaPage) -> None:
    lst = page.kind_list
    name = lst.kind_item("spaces").data(Qt.ItemDataRole.AccessibleTextRole)
    assert KIND_LABELS["spaces"] in name
    assert "2" in name
    assert lst.accessibleName()


def test_empty_state_shows_hint_not_a_broken_list(qtbot: QtBot) -> None:
    p = QaPage()
    qtbot.addWidget(p)
    p.resize(1200, 700)
    p.show()
    assert _shown(p.kind_list) == ["Tüm bulgular"]
    assert p.kind_list.is_empty()
    assert 0 < len(p.kind_list.empty_text) <= 90


# --- Sığdırma "Göster" ----------------------------------------------------------------------------


def test_overflow_kinds_are_shown_selected_in_list(page: QaPage) -> None:
    page._show_overflow()
    assert page.tabs.currentIndex() == 0
    lst = page.kind_list
    assert lst.selected_kinds() == {"line_too_long", "page_too_tall"}
    assert lst.kind_item("line_too_long").isSelected()
    assert lst.kind_item("page_too_tall").isSelected()
    assert not lst.kind_item("spaces").isSelected()
    assert page.proxy.rowCount() == 2


# --- tablo -----------------------------------------------------------------------------------------


def test_kind_column_is_gone_but_kind_name_stays_in_description_hint(page: QaPage) -> None:
    assert page.model.columnCount() == 1  # tek sütun: Tür (ve öteki) sütunları yok
    index = page.proxy.index(0, 0)
    assert KIND_LABELS["placeholder"] in index.data(Qt.ItemDataRole.ToolTipRole)
    assert KIND_LABELS["placeholder"] in index.data(Qt.ItemDataRole.AccessibleTextRole)
    assert "placeholder iletisi" in index.data(Qt.ItemDataRole.AccessibleTextRole)


def test_single_column_fills_the_viewport_width(qtbot: QtBot, page: QaPage) -> None:
    qtbot.wait(100)
    assert page.table.columnWidth(0) >= page.table.viewport().width() - 4


# --- hayalet kutu ----------------------------------------------------------------------------------


def test_selected_row_draws_continuous_selection_without_ghost_frame(page: QaPage) -> None:
    """Seçili ve odaklı satırda seçim zemini kesintisizdir; satırın kenar bantlarında çerçeve/kutu çizilmez."""
    delegate = page.table.itemDelegate()
    assert delegate is not None
    width, height = 600, page.table.verticalHeader().defaultSectionSize()
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    option = QStyleOptionViewItem()
    option.widget = page.table
    option.palette = page.table.palette()
    option.font = page.table.font()
    option.fontMetrics = page.table.fontMetrics()
    option.rect = QRect(0, 0, width, height)
    option.state = (
        QStyle.StateFlag.State_Enabled
        | QStyle.StateFlag.State_Selected
        | QStyle.StateFlag.State_HasFocus
        | QStyle.StateFlag.State_Active
    )
    painter = QPainter(image)
    delegate.paint(painter, option, page.proxy.index(0, 0))
    painter.end()
    side: set[int] = set()
    for y in range(2, height - 3):
        for x in list(range(1, 8)) + list(range(width - 8, width - 1)):
            side.add(image.pixel(QPoint(x, y)))
    assert len(side) == 1, "satırın kenarında seçim zemininden başka bir şey (çerçeve) çizilmiş"
    assert QColor(side.pop()).alpha() == 255  # zemin tüm satırı dolduruyor: seçim kesintisiz
