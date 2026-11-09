"""Çevir ve Kontrol Et tabloları: No sütunu, doğal sıralama, durum simgeleri, sütun gizleme, akıllı sığdırma,
yumuşak kaydırma ve Excel tarzı çoklu süzgeç."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QAbstractItemView
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import QaIssue
from nxceviri.core.translate.status import STATUS_LABELS, Status
from nxceviri.gui.qa_page import (
    COL_DESCRIPTION,
    COL_KIND,
    QaPage,
)
from nxceviri.gui.qa_page import (
    COL_SOURCE as QA_SOURCE,
)
from nxceviri.gui.qa_page import (
    COL_TRANSLATION as QA_TRANSLATION,
)
from nxceviri.gui.status_cell import STATUS_ICONS, STATUS_ROLE
from nxceviri.gui.table_columns import FitTableView
from nxceviri.gui.translate_page import (
    COL_FILE,
    COL_KEY,
    COL_NO,
    COL_PREVIOUS,
    COL_SOURCE,
    COL_STATUS,
    COL_TRANSLATION,
    TranslatePage,
)
from nxceviri.gui.value_filter import FilterPopup, ValueFilter

pytestmark = pytest.mark.gui


def _row(
    i: int,
    source: str,
    translation: str = "",
    status: str = Status.UNTRANSLATED,
    key: str = "",
    file: str = "Data/a_en.bundle",
    codes: tuple[str, ...] = (),
) -> TranslationRow:
    return TranslationRow(
        id=i,
        file=file,
        key=key or f"K/{i}",
        source=source,
        translation=translation,
        status=status,
        note="",
        code_labels=codes,
        max_length=None,
        context=key or f"K/{i}",
    )


def _page(
    qtbot: QtBot, rows: list[TranslationRow], width: int = 1100, settings: QSettings | None = None
) -> TranslatePage:
    p = TranslatePage()
    qtbot.addWidget(p)
    if settings is not None:
        p.bind_settings(settings)
    p.resize(width, 700)
    p.show()
    p.set_rows(rows)
    return p


def _ini(tmp_path: Path, name: str = "t.ini") -> QSettings:
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


def _visible_cols(p: TranslatePage) -> list[int]:
    h = p.table.horizontalHeader()
    return [c for c in range(h.count()) if not h.isSectionHidden(c)]


def _column(p: TranslatePage, col: int) -> list[str]:
    return [str(p.proxy.index(r, col).data()) for r in range(p.proxy.rowCount())]


# --- No sütunu ------------------------------------------------------------------------------


def test_no_column_is_leftmost_narrow_and_right_aligned(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(10, "B"), _row(20, "A"), _row(30, "C")])
    h = p.table.horizontalHeader()
    assert h.visualIndex(COL_NO) == 0
    assert h.sectionSize(COL_NO) <= 60
    index = p.proxy.index(0, COL_NO)
    assert index.data(Qt.ItemDataRole.TextAlignmentRole) & Qt.AlignmentFlag.AlignRight
    assert _column(p, COL_NO) == ["1", "2", "3"]  # kimlikler 10/20/30 olsa da No 1'den başlar


def test_no_is_stable_under_sort_and_filter(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "Banana"), _row(2, "apple"), _row(3, "Cherry")])
    p.model.sort_by(COL_SOURCE)
    assert _column(p, COL_SOURCE) == ["apple", "Banana", "Cherry"]
    assert _column(p, COL_NO) == ["2", "1", "3"]  # No satırla birlikte gider, sıralamayla değişmez
    p.search.setText("cherry")
    assert _column(p, COL_NO) == ["3"]
    p.model.sort_by(COL_NO, Qt.SortOrder.DescendingOrder)
    p.search.clear()
    assert _column(p, COL_NO) == ["3", "2", "1"]


def test_no_sorts_numerically(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(i, f"S{i}") for i in range(1, 13)])
    p.model.sort_by(COL_NO, Qt.SortOrder.DescendingOrder)
    assert _column(p, COL_NO)[:3] == ["12", "11", "10"]


def test_hash_search_jumps_to_row_without_filtering(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(i, f"Satır {i}") for i in range(1, 201)])
    p.search.setText("#120")
    assert p.proxy.rowCount() == 200  # "#120" metin araması değildir: tablo süzülmez
    current = p.current_row()
    assert current is not None
    assert current.id == 120
    p.search.setText("# 7")
    row = p.current_row()
    assert row is not None
    assert row.id == 7
    p.search.setText("#999")  # olmayan satır: seçim değişmez, hata yok
    row = p.current_row()
    assert row is not None
    assert row.id == 7
    assert p.model.row_by_number(0) is None


def test_hash_search_respects_other_filters(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "A", status=Status.APPROVED), _row(2, "B"), _row(3, "C")])
    p.status_filter.setCurrentIndex(p.status_filter.findData(Status.UNTRANSLATED.value))
    assert not p.go_to_number(1)  # 1 numaralı satır durum süzgeciyle gizli
    assert p.go_to_number(2)


# --- doğal sıralama -------------------------------------------------------------------------


def test_natural_sort_in_every_text_column(qtbot: QtBot) -> None:
    texts = ["Item 10", "Item 2", "Item 100", "Item 1"]
    p = _page(qtbot, [_row(i, t, t, key=t, file=f"Data/{t}.bundle") for i, t in enumerate(texts, 1)])
    expected = ["Item 1", "Item 2", "Item 10", "Item 100"]
    p.model.sort_by(COL_SOURCE)
    assert _column(p, COL_SOURCE) == expected
    p.model.sort_by(COL_TRANSLATION)
    assert _column(p, COL_TRANSLATION) == expected
    p.model.sort_by(COL_KEY)
    assert _column(p, COL_KEY) == expected
    p.model.sort_by(COL_FILE)
    assert _column(p, COL_FILE) == [f"{t}.bundle" for t in expected]
    p.model.sort_by(COL_SOURCE, Qt.SortOrder.DescendingOrder)
    assert _column(p, COL_SOURCE) == expected[::-1]


def test_natural_sort_keeps_turkish_letters(qtbot: QtBot) -> None:
    texts = ["şeker 2", "çilek 10", "cam 1", "çilek 9", "dünya"]
    p = _page(qtbot, [_row(i, t) for i, t in enumerate(texts, 1)])
    p.model.sort_by(COL_SOURCE)
    assert _column(p, COL_SOURCE) == ["cam 1", "çilek 9", "çilek 10", "dünya", "şeker 2"]


def test_qa_table_sorts_naturally(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    rows = {i: _row(i, f"Satır {i}", f"Satır {i}") for i in (1, 2, 10, 100)}
    issues = [QaIssue(i, f"K/{i}", "spaces", "warning", "Sorun") for i in (10, 100, 2, 1)]
    page.model.set_issues(issues, rows)
    page.proxy.sort(QA_SOURCE, Qt.SortOrder.AscendingOrder)
    assert [page.proxy.index(r, QA_SOURCE).data() for r in range(4)] == [f"Satır {i}" for i in (1, 2, 10, 100)]


# --- durum simgeleri ------------------------------------------------------------------------


def test_status_cell_uses_icons_and_tooltips(qtbot: QtBot) -> None:
    rows = [
        _row(1, "A", status=Status.UNTRANSLATED),
        _row(2, "B", "Be", Status.MACHINE),
        _row(3, "C", "Ce", Status.REDACTED),
        _row(4, "D", "De", Status.APPROVED),
        _row(5, "E", "Ee", Status.ERROR),
        _row(6, "Hi ⟦1⟧", "Selam", Status.MACHINE, codes=("renk",)),
    ]
    p = _page(qtbot, rows)
    model = p.model
    for r in rows[:5]:
        index = model.index(model.position(r.id) or 0, COL_STATUS)
        status, _severity = index.data(STATUS_ROLE)
        assert status == Status(r.status)
        assert STATUS_LABELS[status] in index.data(Qt.ItemDataRole.ToolTipRole)
        assert STATUS_ICONS[status][0]
    # Kontrol kodu eksik: durum simgesinin yanında üçgen (hata) çıkar ve ipucunda sorun yazar.
    broken = model.index(model.position(6) or 0, COL_STATUS)
    assert broken.data(STATUS_ROLE)[1] == "error"
    assert "Makine" in broken.data(Qt.ItemDataRole.ToolTipRole)
    assert "✖" in broken.data(Qt.ItemDataRole.ToolTipRole)
    header_tip = model.headerData(COL_STATUS, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
    assert "kırmızı üçgen" in header_tip
    assert "mavi bilgisayar" in header_tip


def test_status_cell_warning_severity(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "Hi", "Merhaba " * 30, Status.MACHINE)])
    index = p.model.index(0, COL_STATUS)
    status, severity = index.data(STATUS_ROLE)
    assert (status, severity) == (Status.MACHINE, "warning")


def test_status_cell_paints_an_icon_not_text(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "A", "Be", Status.MACHINE)])
    qtbot.waitUntil(lambda: p.table.columnWidth(COL_STATUS) > 0)
    rect = p.table.visualRect(p.proxy.index(0, COL_STATUS))
    image: QImage = p.table.viewport().grab(rect).toImage()
    background = image.pixelColor(1, 1)
    painted = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if abs(image.pixelColor(x, y).red() - background.red()) + abs(image.pixelColor(x, y).blue() - background.blue())
        > 80
    )
    assert painted > 10  # simge çizildi
    assert rect.width() <= 70  # sütun dar


def test_status_filter_items_have_icons(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "A", "Be", Status.MACHINE), _row(2, "B")])
    for i in range(p.status_filter.count()):
        if p.status_filter.itemData(i) in {s.value for s in Status}:
            assert not p.status_filter.itemIcon(i).isNull()


# --- sütun gizle / göster -------------------------------------------------------------------


def _toggle(p: TranslatePage, name: str) -> None:
    menu = p.column_menu.build_menu()
    action = next(a for a in menu.actions() if a.text() == name)
    action.toggle()


def test_header_menu_hides_columns_and_remembers(qtbot: QtBot, tmp_path: Path) -> None:
    settings = _ini(tmp_path)
    p = _page(qtbot, [_row(1, "A", "B")], settings=settings)
    menu = p.column_menu.build_menu()
    actions = {a.text(): a for a in menu.actions() if a.text()}
    assert actions["Orijinal"].isChecked()
    assert not actions["Orijinal"].isEnabled()
    assert actions["Çeviri"].isChecked()
    assert not actions["Çeviri"].isEnabled()
    for name in ("No", "Durum", "Dosya", "Anahtar"):
        assert actions[name].isEnabled()
        assert actions[name].isChecked()
    _toggle(p, "Dosya")
    _toggle(p, "No")
    assert p.table.isColumnHidden(COL_FILE)
    assert p.table.isColumnHidden(COL_NO)
    assert COL_SOURCE in _visible_cols(p)
    assert COL_TRANSLATION in _visible_cols(p)

    q = _page(qtbot, [_row(1, "A", "B")], settings=_ini(tmp_path))
    assert q.table.isColumnHidden(COL_FILE)
    assert q.table.isColumnHidden(COL_NO)
    assert not q.table.isColumnHidden(COL_STATUS)
    _toggle(q, "Dosya")
    assert not q.table.isColumnHidden(COL_FILE)
    r = _page(qtbot, [_row(1, "A", "B")], settings=_ini(tmp_path))
    assert not r.table.isColumnHidden(COL_FILE)
    assert r.table.isColumnHidden(COL_NO)


def test_header_context_menu_policy(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "A", "B")])
    assert p.table.horizontalHeader().contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_hiding_a_column_drops_its_filter(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "A", key="X/1"), _row(2, "B", key="Y/2")])
    p.key_filter.set_selected(["X/1"])
    assert p.proxy.rowCount() == 1
    _toggle(p, "Anahtar")
    assert not p.key_filter.active
    assert p.proxy.rowCount() == 2


def test_qa_table_header_menu_and_resizable_columns(qtbot: QtBot, tmp_path: Path) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.bind_settings(_ini(tmp_path))
    page.resize(1000, 700)
    page.show()
    h = page.table.horizontalHeader()
    assert all(h.sectionResizeMode(c) == h.ResizeMode.Interactive for c in range(h.count()))
    menu = page.column_menu.build_menu()
    kind = next(a for a in menu.actions() if a.text() == "Tür")
    assert kind.isEnabled()
    locked = next(a for a in menu.actions() if a.text() == "Orijinal")
    assert not locked.isEnabled()
    kind.toggle()
    assert page.table.isColumnHidden(COL_KIND)
    h.resizeSection(QA_TRANSLATION, 321)
    other = QaPage()
    qtbot.addWidget(other)
    other.bind_settings(_ini(tmp_path))
    other.resize(1000, 700)
    other.show()
    assert other.table.isColumnHidden(COL_KIND)
    assert other.table.horizontalHeader().sectionSize(QA_TRANSLATION) == 321
    assert COL_DESCRIPTION != COL_KIND


# --- akıllı sığdırma ------------------------------------------------------------------------


@pytest.mark.parametrize("width", [1200, 900, 700])
def test_source_and_translation_always_fit(qtbot: QtBot, width: int) -> None:
    p = _page(qtbot, [_row(i, f"Satır {i}", f"Line {i}") for i in range(1, 50)], width=width)
    qtbot.waitUntil(lambda: p.table.viewport().width() > 0)
    h = p.table.horizontalHeader()
    viewport = p.table.viewport().width()
    for col in (COL_SOURCE, COL_TRANSLATION):
        assert h.sectionSize(col) >= 120
        assert h.sectionViewportPosition(col) + h.sectionSize(col) <= viewport  # tamamen görünür
    assert p.table.horizontalScrollBar().maximum() == 0
    assert abs(sum(h.sectionSize(c) for c in _visible_cols(p)) - viewport) < 8


def test_narrow_columns_shrink_first(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "A", "B")], width=1200)
    h = p.table.horizontalHeader()
    wide = {c: h.sectionSize(c) for c in (COL_FILE, COL_KEY, COL_SOURCE)}
    p.resize(640, 700)
    qtbot.waitUntil(lambda: h.sectionSize(COL_FILE) < wide[COL_FILE])
    assert h.sectionSize(COL_KEY) < wide[COL_KEY]
    assert h.sectionSize(COL_SOURCE) >= 120
    qtbot.waitUntil(lambda: p.table.horizontalScrollBar().maximum() == 0)


def test_hidden_column_frees_space_for_text(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "A", "B")], width=1000)
    h = p.table.horizontalHeader()
    before = h.sectionSize(COL_TRANSLATION)
    _toggle(p, "Dosya")
    _toggle(p, "Anahtar")
    assert h.sectionSize(COL_TRANSLATION) > before
    assert abs(sum(h.sectionSize(c) for c in _visible_cols(p)) - p.table.viewport().width()) < 8


def test_user_widening_beyond_window_shows_scrollbar_and_click_does_not_scroll(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(i, f"Satır {i}", f"Line {i}") for i in range(1, 30)], width=900)
    h = p.table.horizontalHeader()
    h.resizeSection(COL_SOURCE, 1500)
    h.resizeSection(COL_TRANSLATION, 1500)
    bar = p.table.horizontalScrollBar()
    qtbot.waitUntil(lambda: bar.maximum() > 0)  # yalnızca kullanıcı elle genişlettiği için
    bar.setValue(0)
    for column in (COL_TRANSLATION, COL_FILE, COL_KEY):
        p.table.setCurrentIndex(p.proxy.index(3, column))
        p.table.scrollTo(p.proxy.index(3, column), QAbstractItemView.ScrollHint.PositionAtCenter)
        assert bar.value() == 0
    p.table.selectRow(5)
    assert bar.value() == 0


def test_keyboard_navigation_keeps_current_cell_visible(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(i, f"Satır {i}", f"Line {i}") for i in range(1, 30)], width=900)
    h = p.table.horizontalHeader()
    h.resizeSection(COL_SOURCE, 1500)
    h.resizeSection(COL_TRANSLATION, 1500)
    bar = p.table.horizontalScrollBar()
    qtbot.waitUntil(lambda: bar.maximum() > 0)
    bar.setValue(0)
    p.table.setCurrentIndex(p.proxy.index(3, COL_SOURCE))
    p.table.setFocus()
    assert bar.value() == 0
    qtbot.keyClick(p.table, Qt.Key.Key_Right)  # Çeviri sütununa: 1500 px'lik hücre, bir kısmı görünmeli
    current = p.table.currentIndex()
    assert current.column() != COL_SOURCE
    cell = p.table.visualRect(current)
    assert cell.intersects(p.table.viewport().rect())
    for _ in range(4):  # çok sağa git: geçerli hücre hep görünür kalır
        qtbot.keyClick(p.table, Qt.Key.Key_Right)
        assert p.table.visualRect(p.table.currentIndex()).intersects(p.table.viewport().rect())


def test_reset_widths_returns_to_auto_fit(qtbot: QtBot, tmp_path: Path) -> None:
    settings = _ini(tmp_path)
    p = _page(qtbot, [_row(1, "A", "B")], width=1000, settings=settings)
    p.table.horizontalHeader().resizeSection(COL_SOURCE, 500)
    assert settings.contains("translate/column_widths")
    menu = p.column_menu.build_menu()
    next(a for a in menu.actions() if a.text() == "Sütun genişliklerini sıfırla").trigger()
    assert not settings.contains("translate/column_widths")
    assert not p.fitter.user_sized
    assert (
        abs(sum(p.table.horizontalHeader().sectionSize(c) for c in _visible_cols(p)) - p.table.viewport().width()) < 8
    )


def test_previous_column_shares_space(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, "A", "B")], width=1100)
    p.previous_box.setEnabled(True)
    p.previous_box.setChecked(True)
    h = p.table.horizontalHeader()
    assert not p.table.isColumnHidden(COL_PREVIOUS)
    assert abs(sum(h.sectionSize(c) for c in _visible_cols(p)) - p.table.viewport().width()) < 8
    assert h.visualIndex(COL_PREVIOUS) == h.visualIndex(COL_TRANSLATION) + 1


# --- yumuşak kaydırma -----------------------------------------------------------------------


def test_tables_scroll_per_pixel(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(i, f"S{i}") for i in range(1, 400)])
    qa = QaPage()
    qtbot.addWidget(qa)
    for table in (p.table, qa.table):
        assert isinstance(table, FitTableView)
        assert table.verticalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel
        assert table.horizontalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel
    p.table.scrollToBottom()
    step = p.table.verticalScrollBar().singleStep()
    assert step == p.table.wheel_step()
    assert step >= p.table.fontMetrics().height()  # bir çentik (3 adım) ≈ 3 satır
    assert 3 * step == 3 * (p.table.fontMetrics().height() + 14)


# --- çoklu süzgeç ---------------------------------------------------------------------------


def _grouped(n_each: int = 3) -> list[TranslationRow]:
    rows: list[TranslationRow] = []
    for g in ("Dialogue", "Menu", "Item"):
        for i in range(n_each):
            rows.append(_row(len(rows) + 1, f"{g} {i}", key=f"{g}/k{i}"))
    return rows


def test_multi_group_filter(qtbot: QtBot) -> None:
    p = _page(qtbot, _grouped())
    assert [v for v, _n in p.group_filter.values] == ["Dialogue", "Item", "Menu"]
    p.group_filter.set_selected(["Dialogue", "Menu"])
    assert p.proxy.rowCount() == 6
    assert {r.key.split("/")[0] for r in p.filtered_rows()} == {"Dialogue", "Menu"}
    assert p.group_filter.active
    p.group_filter.clear()
    assert p.proxy.rowCount() == 9


def test_multi_key_filter_and_combination(qtbot: QtBot) -> None:
    p = _page(qtbot, _grouped())
    p.key_filter.set_selected(["Dialogue/k0", "Menu/k1", "Item/k2"])
    assert p.proxy.rowCount() == 3
    p.group_filter.set_selected(["Menu"])
    assert [r.key for r in p.filtered_rows()] == ["Menu/k1"]
    assert p._clear_filters()
    assert p.proxy.rowCount() == 9
    assert not p.key_filter.active
    assert not p.group_filter.active


def test_filter_popup_applies_selection(qtbot: QtBot) -> None:
    p = _page(qtbot, _grouped())
    popup = p.open_filter(COL_KEY)
    assert isinstance(popup, FilterPopup)
    assert popup.model.rowCount() == 9
    popup.all_box.click()  # hepsi işaretliydi: kaldır
    assert not popup.ok_button.isEnabled()
    popup.search.setText("menu")  # aramayla daralır; "Tümü" yalnızca görünenleri işaretler
    assert popup.model.rowCount() == 3
    popup.all_box.click()
    assert popup.ok_button.isEnabled()
    popup.ok_button.click()
    assert p.key_filter.selected == frozenset({"Menu/k0", "Menu/k1", "Menu/k2"})
    assert p.proxy.rowCount() == 3
    again = p.open_filter(COL_KEY)
    again.clear_button.click()
    assert not p.key_filter.active
    assert p.proxy.rowCount() == 9


def test_filter_popup_all_checked_means_no_filter(qtbot: QtBot) -> None:
    p = _page(qtbot, _grouped())
    popup = p.open_filter(COL_FILE)
    popup.ok_button.click()
    assert not p.group_filter.active


def test_filter_funnel_click_opens_panel(qtbot: QtBot) -> None:
    p = _page(qtbot, _grouped())
    header = p.filter_header
    rect = header.funnel_rect(COL_KEY)
    opened: list[int] = []
    header.filter_clicked.connect(opened.append)
    qtbot.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert opened == [COL_KEY]
    assert header.sortIndicatorSection() != COL_KEY  # huni tıklaması sıralamayı tetiklemez
    for popup in p.table.findChildren(FilterPopup):
        popup.close()


def test_filter_performance_with_ten_thousand_keys(qtbot: QtBot) -> None:
    rows = [_row(i, f"Metin {i}", key=f"Dialogue/line_{i}") for i in range(1, 10001)]
    p = _page(qtbot, rows)
    start = time.perf_counter()
    popup = p.open_filter(COL_KEY)
    popup.all_box.click()  # hepsini kaldır
    popup.search.setText("line_99")
    assert popup.model.rowCount() == 111  # line_99, line_990..999, line_9900..9999
    popup.all_box.click()  # görünen 111 değeri işaretle
    popup.ok_button.click()
    assert p.proxy.rowCount() == 111
    p.key_filter.clear()
    assert p.proxy.rowCount() == 10000
    assert time.perf_counter() - start < 1.0


def test_filter_values_use_natural_order(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(i, "x", key=f"Dialogue/line_{n}") for i, n in enumerate((10, 2, 1, 100), 1)])
    assert [v for v, _n in p.key_filter.values] == [f"Dialogue/line_{n}" for n in (1, 2, 10, 100)]


def test_filters_are_remembered_per_project(qtbot: QtBot, tmp_path: Path) -> None:
    settings = _ini(tmp_path)
    p = TranslatePage()
    qtbot.addWidget(p)
    p.bind_settings(settings)
    p.set_project_key("proje-a")
    p.set_rows(_grouped())
    p.group_filter.set_selected(["Item"])
    p.key_filter.set_selected(["Item/k0", "Item/k1"])
    assert p.proxy.rowCount() == 2

    q = TranslatePage()
    qtbot.addWidget(q)
    q.bind_settings(_ini(tmp_path))
    q.set_project_key("proje-a")
    q.set_rows(_grouped())
    assert q.group_filter.selected == frozenset({"Item"})
    assert q.key_filter.selected == frozenset({"Item/k0", "Item/k1"})
    assert q.proxy.rowCount() == 2

    other = TranslatePage()
    qtbot.addWidget(other)
    other.bind_settings(_ini(tmp_path))
    other.set_project_key("proje-b")
    other.set_rows(_grouped())
    assert not other.group_filter.active
    assert other.proxy.rowCount() == 9

    q.group_filter.clear()
    q.key_filter.clear()
    again = TranslatePage()
    again.bind_settings(_ini(tmp_path))
    again.set_project_key("proje-a")
    again.set_rows(_grouped())
    assert not again.group_filter.active


def test_unsaved_project_filters_are_not_persisted(qtbot: QtBot, tmp_path: Path) -> None:
    settings = _ini(tmp_path)
    p = TranslatePage()
    qtbot.addWidget(p)
    p.bind_settings(settings)
    p.set_project_key(None)
    p.set_rows(_grouped())
    p.group_filter.set_selected(["Menu"])
    assert not [k for k in settings.allKeys() if k.startswith("translate/filters")]


def test_selection_drops_values_that_disappeared(qtbot: QtBot) -> None:
    p = _page(qtbot, _grouped())
    p.group_filter.set_selected(["Menu", "Item"])
    p.set_rows([r for r in _grouped() if not r.key.startswith("Menu")])
    assert p.group_filter.selected == frozenset({"Item"})
    p.set_rows([r for r in _grouped() if r.key.startswith("Dialogue")])
    assert not p.group_filter.active  # seçili değerlerin hiçbiri kalmadıysa süzgeç kalkar


def test_value_filter_json_roundtrip_prefers_shorter_form() -> None:
    vf = ValueFilter("x")
    vf.set_values({f"k{i}": 1 for i in range(100)})
    vf.set_selected([f"k{i}" for i in range(98)])
    text = vf.to_json()
    assert '"out"' in text
    assert len(text) < 60  # 98 değer yerine dışlanan 2 değer yazılır
    other = ValueFilter("x")
    other.set_values({f"k{i}": 1 for i in range(100)})
    other.load_json(text)
    assert other.selected == vf.selected
    other.load_json("bozuk{")
    assert other.selected is None
    vf.set_selected(["k1"])
    assert '"in"' in vf.to_json()
