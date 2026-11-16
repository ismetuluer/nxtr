"""Çevir tablosunda gruplu görünüm (arayüz): düğme, tercih, başlık satırı, katlama, klavye, menü, kurallar."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, QRect, QSettings, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLayout, QPlainTextEdit, QStyleOptionViewItem
from pytestqt.qtbot import QtBot

from nxceviri.core.errors import ProjectError
from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import SEVERITY_WARNING, QaIssue
from nxceviri.core.qa.live import LiveChecker
from nxceviri.core.translate.status import Status
from nxceviri.gui.find_replace import SCOPE_VISIBLE
from nxceviri.gui.group_header import GroupHeader
from nxceviri.gui.marked_delegate import MarkedDelegate
from nxceviri.gui.shortcuts import COMMANDS_BY_ID
from nxceviri.gui.translate_page import COL_SOURCE, COL_TRANSLATION, TranslatePage

pytestmark = pytest.mark.gui

KEY = "translate/grouped"


def _row(i: int, file: str, status: str = Status.MACHINE, translation: str | None = None) -> TranslationRow:
    text = f"Çeviri {i}" if translation is None else translation
    return TranslationRow(i, f"Data/{file}", f"k{i}", f"Kaynak {i:02d}", text, status, "", (), None, "", "msbt")


# Üç grup: a (1, 4, 7), b (2, 5, 8), c (3, 6, 9); c'de çevrilmemiş ve hatalı satır var.
ROWS = [
    _row(1, "a.msbt"),
    _row(2, "b.msbt"),
    _row(3, "c.msbt", Status.UNTRANSLATED, ""),
    _row(4, "a.msbt"),
    _row(5, "b.msbt"),
    _row(6, "c.msbt", Status.ERROR),
    _row(7, "a.msbt"),
    _row(8, "b.msbt"),
    _row(9, "c.msbt"),
]


def _ini(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat)


def _page(qtbot: QtBot, rows: list[TranslationRow], settings: QSettings | None = None) -> TranslatePage:
    p = TranslatePage()
    qtbot.addWidget(p)
    if settings is not None:
        p.bind_settings(settings)
    p.resize(1100, 600)
    p.show()
    p.set_rows(rows)
    p.model.commit = lambda changes: [
        TranslationRow(
            i, r.file, r.key, r.source, t, Status.APPROVED if t else Status.UNTRANSLATED, "", (), None, "", "msbt"
        )
        for i, t in changes
        if (r := p.model.row_by_id(i)) is not None
    ]
    return p


def _grouped(qtbot: QtBot) -> TranslatePage:
    p = _page(qtbot, ROWS)
    p.group_action.trigger()
    assert p.proxy is p.group_proxy
    return p


def _header_row(p: TranslatePage, name: str) -> int:
    return next(r for r in range(p.proxy.rowCount()) if p.group_proxy.header_group(r) == name)


def _model_of(p: TranslatePage) -> object:
    """Tablonun o anki modeli (mypy daraltması testi kandırmasın diye `object`)."""
    return p.proxy


def _current_id(p: TranslatePage) -> int | None:
    row = p.current_row()
    return None if row is None else row.id


def _select_ids(p: TranslatePage, ids: list[int]) -> None:
    selection = p.table.selectionModel()
    selection.clearSelection()
    for row_id in ids:
        index = p._view_index(p.model.position(row_id) or 0)
        selection.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)


def _click_header(p: TranslatePage, name: str) -> None:
    rect = p.table.visualRect(p.proxy.index(_header_row(p, name), COL_SOURCE))
    QTest.mouseClick(p.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())


# --- düğme, kısayol, tercih -------------------------------------------------------------------


def test_button_hidden_when_project_has_single_group(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(i, "a.msbt") for i in range(1, 5)])
    assert p.group_button.isHidden()
    assert not p.group_action.isEnabled()
    assert not p.group_action.isVisible()
    p.group_action.setChecked(True)  # kısayol/menü çalışmasa da: tek grupta gruplama kapalı davranır
    assert p.proxy is p.filter
    p.set_rows(ROWS)
    assert not p.group_button.isHidden()
    assert p.group_action.isEnabled()


def test_button_is_tool_with_tip_icon_and_accessible_name(qtbot: QtBot) -> None:
    p = _page(qtbot, ROWS)
    b = p.group_button
    assert b.property("role") is None
    assert b.autoRaise()
    assert b.isCheckable()
    assert b.accessibleName() == "Gruplu görünüm"
    assert "öbekle" in b.toolTip()
    assert not b.icon().isNull()
    assert not b.isChecked()  # varsayılan kapalı
    assert p.proxy is p.filter


def test_shortcut_command_has_no_default_key() -> None:
    command = COMMANDS_BY_ID["view.grouped"]
    assert command.default == ""


def test_preference_is_remembered_and_reapplied_per_project(qtbot: QtBot, tmp_path: Path) -> None:
    settings = _ini(tmp_path)
    p = _page(qtbot, ROWS, settings)
    p.group_action.trigger()
    assert str(settings.value(KEY)) == "1"
    again = _page(qtbot, ROWS, _ini(tmp_path))
    assert again.group_action.isChecked()
    assert _model_of(again) is again.group_proxy
    again.set_rows([_row(i, "a.msbt") for i in range(1, 4)])  # tek gruplu proje: kapalı davranır
    assert _model_of(again) is again.filter
    assert again.group_button.isHidden()
    again.set_rows(ROWS)  # tercih unutulmaz
    assert _model_of(again) is again.group_proxy
    again.group_action.trigger()
    assert str(settings.value(KEY)) == "0"
    assert _model_of(again) is again.filter


# --- başlık bilgisi ---------------------------------------------------------------------------


def test_header_info_counts_filtered_rows_and_known_warnings(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    assert [p.group_proxy.header_group(r) for r in (0, 4, 8)] == ["a.msbt", "b.msbt", "c.msbt"]
    a = p.header_info(_header_row(p, "a.msbt"))
    assert a == GroupHeader("a.msbt", count=3, translated=3, warned=False, collapsed=False)
    c = p.header_info(_header_row(p, "c.msbt"))
    assert c is not None
    assert (c.count, c.translated, c.warned) == (3, 1, True)  # hatalı satır uyarıdır; çevrilen yalnızca 9
    assert p.header_info(1) is None  # gerçek satır
    p.search.setText("Kaynak 0")  # 1-9'un hepsi; sayı süzgece göre
    p.search.setText("Kaynak 07")
    a = p.header_info(_header_row(p, "a.msbt"))
    assert a is not None
    assert (a.count, a.translated) == (1, 1)
    assert "1 satır · 1 çevrildi" in p.header_tip(_header_row(p, "a.msbt"))


def test_warning_from_last_check_and_live_cache_only(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _grouped(qtbot)
    checked: list[int] = []
    original = LiveChecker.check

    def counting(self: LiveChecker, row: TranslationRow) -> list[QaIssue]:
        checked.append(row.id)
        return original(self, row)

    monkeypatch.setattr(LiveChecker, "check", counting)
    checked.clear()
    p._header_stats.clear()
    p.header_info(_header_row(p, "b.msbt"))
    assert checked == []  # başlık için toplu anlık denetim yapılmaz
    row5 = p.model.row_by_id(5)
    assert row5 is not None
    p.set_qa_issues([QaIssue(5, "k5", "term", SEVERITY_WARNING, "terim")], [row5])
    b = p.header_info(_header_row(p, "b.msbt"))
    assert b is not None
    assert b.warned
    assert "uyarı" in p.header_tip(_header_row(p, "b.msbt"))


def test_editing_updates_header_without_moving_rows(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    order = [p._row_at(r).id if p._row_at(r) else None for r in range(p.proxy.rowCount())]  # type: ignore[union-attr]
    assert p.model.apply([(3, "Yeni çeviri")])
    assert [p._row_at(r).id if p._row_at(r) else None for r in range(p.proxy.rowCount())] == order  # type: ignore[union-attr]
    c = p.header_info(_header_row(p, "c.msbt"))
    assert c is not None
    assert c.translated == 2


# --- katlama ----------------------------------------------------------------------------------


def test_click_on_header_collapses_and_moves_current_to_header(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    p.select_row(5)
    _click_header(p, "b.msbt")
    assert p.group_proxy.is_collapsed("b.msbt")
    assert p.table.currentIndex().row() == _header_row(p, "b.msbt")
    assert p.selected_rows() == []
    _click_header(p, "b.msbt")
    assert not p.group_proxy.is_collapsed("b.msbt")
    info = p.header_info(_header_row(p, "b.msbt"))
    assert info is not None
    assert not info.collapsed


def test_keyboard_on_header_toggles_group(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    header = _header_row(p, "a.msbt")
    p.table.setCurrentIndex(p.proxy.index(header, COL_TRANSLATION))
    p.table.setFocus()
    QTest.keyClick(p.table, Qt.Key.Key_Left)
    assert p.group_proxy.is_collapsed("a.msbt")
    QTest.keyClick(p.table, Qt.Key.Key_Right)
    assert not p.group_proxy.is_collapsed("a.msbt")
    QTest.keyClick(p.table, Qt.Key.Key_Space)
    assert p.group_proxy.is_collapsed("a.msbt")
    QTest.keyClick(p.table, Qt.Key.Key_Return)
    assert not p.group_proxy.is_collapsed("a.msbt")
    assert p.table.state() != p.table.State.EditingState  # başlıkta düzenleyici açılmaz


def test_collapsed_groups_survive_toggle_within_session(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    p.group_proxy.set_collapsed("c.msbt", True)
    p.group_action.trigger()
    p.group_action.trigger()
    assert p.group_proxy.is_collapsed("c.msbt")


def test_header_context_menu_collapses_and_expands_all(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    menu = p.build_header_menu()
    texts = [a.text() for a in menu.actions()]
    assert texts == ["Bütün Grupları Katla", "Bütün Grupları Aç"]
    menu.actions()[0].trigger()
    assert all(p.group_proxy.is_collapsed(g) for g in ("a.msbt", "b.msbt", "c.msbt"))
    assert p.proxy.rowCount() == 3
    menu.actions()[1].trigger()
    assert p.proxy.rowCount() == 12


def test_no_editor_and_no_row_menu_on_header(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    index = p.proxy.index(0, COL_TRANSLATION)
    assert not p.proxy.flags(index) & Qt.ItemFlag.ItemIsEditable
    built: list[object] = []
    p.build_context_menu = built.append  # type: ignore[method-assign,assignment]
    p._show_context_menu(p.table.visualRect(index).center())
    assert built == []


def test_header_rows_have_fixed_height(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    p._fit_rows()
    single = p.table.fontMetrics().height() + 14
    assert p.table.rowHeight(_header_row(p, "a.msbt")) == single


# --- önceki kararlar ---------------------------------------------------------------------------


def test_collapsing_is_not_filtering(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    p.group_proxy.set_collapsed("a.msbt", True)
    assert p._all_text_tip()[0] == "9"
    assert not p.find_filters_active()
    assert p.status_filter._buttons[""].property("marked") in (None, False)
    assert {r.id for r in p.filtered_rows()} == set(range(1, 10))  # Otomatik Çeviri "süzülen satırlar"
    assert {r.id for r in p.find_rows(SCOPE_VISIBLE)} == set(range(1, 10))


def test_find_next_opens_collapsed_group(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    p.group_proxy.set_collapsed("c.msbt", True)
    assert p.find_goto(6)
    assert not p.group_proxy.is_collapsed("c.msbt")
    assert _current_id(p) == 6


def test_select_all_and_shift_range_skip_headers_and_collapsed_rows(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    p.group_proxy.set_collapsed("b.msbt", True)
    p.table.setFocus()
    QTest.keyClick(p.table, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert sorted(r.id for r in p.selected_rows()) == [1, 3, 4, 6, 7, 9]
    p.select_row(1)
    p.table.selectionModel().select(
        p.proxy.index(p.proxy.rowCount() - 1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    first = p._view_index(p.model.position(1) or 0)
    last = p.proxy.index(p.proxy.rowCount() - 1, 0)
    QTest.mouseClick(p.table.viewport(), Qt.MouseButton.LeftButton, pos=p.table.visualRect(first).center())
    QTest.mouseClick(
        p.table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        p.table.visualRect(last).center(),
    )
    assert sorted(r.id for r in p.selected_rows()) == [1, 3, 4, 6, 7, 9]
    QTest.keyClick(p.table, Qt.Key.Key_Shift)  # Qt'nin genel değiştirici durumu Shift'te kalmasın (sonraki testler)


def test_bulk_actions_touch_only_visible_selected_rows(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    _select_ids(p, [1, 2, 5])
    p.group_proxy.set_collapsed("b.msbt", True)  # 2 ve 5 görünmez: seçimden düşer
    p.clear_selected()
    assert [r.id for r in p.model.rows if not r.translation] == [1, 3]
    p.group_proxy.set_collapsed("b.msbt", False)
    _select_ids(p, [3, 8])
    p.group_proxy.set_collapsed("b.msbt", True)
    p.copy_source_selected()
    assert p.model.row_by_id(3).translation == "Kaynak 03"  # type: ignore[union-attr]
    assert p.model.row_by_id(8).translation == "Çeviri 8"  # type: ignore[union-attr]


def test_column_sort_sorts_inside_groups(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    p.model.sort_by(COL_SOURCE, Qt.SortOrder.DescendingOrder)
    ids = [r.id if r else None for r in (p._row_at(v) for v in range(p.proxy.rowCount()))]
    assert ids == [None, 7, 4, 1, None, 8, 5, 2, None, 9, 6, 3]


def _mapping(p: TranslatePage) -> list[int]:
    flt = p.filter
    return [flt.mapToSource(flt.index(i, 0)).row() for i in range(flt.rowCount())]


def _assert_accepted_matches(p: TranslatePage) -> None:
    assert p.filter.accepted_rows() == _mapping(p)
    keys = p._group_keys()
    assert keys == [p._row_groups[p.model.rows[i].id] for i in _mapping(p)]


def test_accepted_rows_cache_matches_filter_mapping(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    _assert_accepted_matches(p)
    for order in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):  # (a) sütun sıralaması
        p.model.sort_by(COL_SOURCE, order)
        _assert_accepted_matches(p)
    p.status_filter.set_current(Status.MACHINE.value)  # (b) durum süzgeci
    _assert_accepted_matches(p)
    p.search.setText("Kaynak 0")  # (b) arama
    p._apply_search_now()
    _assert_accepted_matches(p)
    before = _mapping(p)
    assert p.model.apply([(1, "Onaylandı artık")])  # (c) durum değişti ama satır yerinde kalır
    assert p.model.row_by_id(1).status == Status.APPROVED  # type: ignore[union-attr]
    assert _mapping(p) == before
    _assert_accepted_matches(p)
    p.set_rows([*ROWS, _row(10, "d.msbt"), _row(11, "a.msbt", Status.UNTRANSLATED, "")])  # (d) sayı artar
    _assert_accepted_matches(p)
    p.set_rows(ROWS[:5])  # (d) sayı azalır
    _assert_accepted_matches(p)
    p.status_filter.set_current("")  # (e) süzgeçler temizlenir
    p.search.setText("")
    p._apply_search_now()
    _assert_accepted_matches(p)
    assert p.filter.accepted_rows() == list(range(5))


def test_accepted_rows_falls_back_when_record_is_inconsistent(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    p.status_filter.set_current(Status.MACHINE.value)
    expected = [p._row_groups[p.model.rows[i].id] for i in _mapping(p)]
    p.filter._accepted = [True] * len(p.model.rows)  # kayıt süzgeçle uyuşmuyor (sayı tutmuyor)
    assert p.filter.accepted_rows() is None
    assert p._group_keys() == expected  # yavaş ama kesin yol (`filtered_rows`)


# --- katlarken kaydedilmemiş metin -------------------------------------------------------------


def _fail_commit(p: TranslatePage) -> None:
    def fail(changes: list[tuple[int, str]]) -> list[TranslationRow]:
        raise ProjectError("Proje dosyasına yazılamadı.", "Diskte yer olduğundan emin olun.")

    p.model.commit = fail


def _pane_text(p: TranslatePage, row_id: int, text: str) -> None:
    p.select_row(row_id)
    p.pane.translation_edit.setPlainText(text)
    assert p.pane.has_pending()


def _fold_by_click(p: TranslatePage) -> None:
    _click_header(p, "b.msbt")


def _fold_by_key(p: TranslatePage) -> None:
    header = p.proxy.index(_header_row(p, "b.msbt"), COL_TRANSLATION)
    p.table.selectionModel().setCurrentIndex(header, QItemSelectionModel.SelectionFlag.NoUpdate)
    p.table.setFocus()
    QTest.keyClick(p.table, Qt.Key.Key_Left)


def _fold_all_by_menu(p: TranslatePage) -> None:
    p.build_header_menu().actions()[0].trigger()


FOLDS = [_fold_by_click, _fold_by_key, _fold_all_by_menu]


@pytest.mark.parametrize("fold", FOLDS)
def test_collapsing_saves_pending_pane_text(qtbot: QtBot, fold: object) -> None:
    p = _grouped(qtbot)
    _pane_text(p, 5, "Panelde yazıldı")
    fold(p)  # type: ignore[operator]
    assert p.group_proxy.is_collapsed("b.msbt")
    assert p.model.row_by_id(5).translation == "Panelde yazıldı"  # type: ignore[union-attr]
    assert not p.pane.has_pending()


@pytest.mark.parametrize("fold", FOLDS)
def test_collapsing_is_refused_when_pane_text_cannot_be_saved(qtbot: QtBot, fold: object) -> None:
    p = _grouped(qtbot)
    _pane_text(p, 5, "Kaydedilemeyen")
    _fail_commit(p)
    fold(p)  # type: ignore[operator]
    assert not p.group_proxy.is_collapsed("b.msbt")
    assert p.pane.has_pending()
    assert p.pane.translation_edit.toPlainText() == "Kaydedilemeyen"


def test_collapse_all_saves_open_cell_editor(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    index = p._view_index(p.model.position(5) or 0, COL_TRANSLATION)
    p.table.setCurrentIndex(index)
    p.table.edit(index)
    editors = p.table.viewport().findChildren(QPlainTextEdit)
    assert editors
    editors[0].setPlainText("Hücrede yazıldı")
    _fold_all_by_menu(p)
    assert p.group_proxy.is_collapsed("b.msbt")
    assert p.model.row_by_id(5).translation == "Hücrede yazıldı"  # type: ignore[union-attr]


def test_find_visible_scope_tip_mentions_collapsed_groups(qtbot: QtBot) -> None:
    p = _grouped(qtbot)
    tip = p.find_bar.scope_tip(SCOPE_VISIBLE)
    assert "katlanmış" in tip


def test_marked_delegate_draws_nothing_on_header(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _grouped(qtbot)
    delegate = MarkedDelegate(None, "source")  # tabloya bağlı değil: tablonun kendi boyaması karışmasın
    built: list[int] = []
    monkeypatch.setattr(delegate, "document", lambda *_a: built.append(1))
    image = QImage(300, 40, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 300, 40)
    option.widget = p.table
    delegate.paint(painter, option, p.proxy.index(0, COL_SOURCE))
    painter.end()
    assert built == []
    assert delegate.sizeHint(option, p.proxy.index(0, COL_SOURCE)).height() == 0


# --- süzgeç şeridindeki yer ve biçem ------------------------------------------------------------


def _filters_layout(p: TranslatePage) -> QLayout:
    body = p.card.body
    for i in range(body.count()):
        item = body.itemAt(i)
        child = item.layout() if item is not None else None
        if child is not None and child.indexOf(p.search) >= 0:
            return child
    raise AssertionError("süzgeç şeridi bulunamadı")


def test_group_button_sits_right_of_stretch_before_machine_button(qtbot: QtBot) -> None:
    p = _page(qtbot, ROWS)
    layout = _filters_layout(p)
    group = layout.indexOf(p.group_button)
    assert layout.indexOf(p.status_filter) < group < layout.indexOf(p.machine_button)
    assert layout.indexOf(p.machine_button) < layout.indexOf(p.pane_button)
    assert p.group_button.property("role") is None
    assert p.group_button.autoRaise()
