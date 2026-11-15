"""Gruplu görünüm vekili (`GroupProxy`): eşleme, birebir geçiş, katlama, sinyallerin çevrilmesi."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from PySide6.QtCore import QItemSelectionModel, QModelIndex, QPersistentModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QTableView
from pytestqt.qtbot import QtBot

from nxceviri.gui.group_proxy import HEADER_ROLE, GroupProxy

pytestmark = pytest.mark.gui

_Index = QModelIndex | QPersistentModelIndex


class _Filter(QSortFilterProxyModel):
    """TranslationFilter gibi: dinamik süzme kapalı, süzgeç yalnızca `set_needle` ile değişir."""

    def __init__(self) -> None:
        super().__init__()
        self.needle = ""
        self.setDynamicSortFilter(False)

    def set_needle(self, needle: str) -> None:
        self.beginFilterChange()
        self.needle = needle
        self.endFilterChange()

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:
        text = str(self.sourceModel().index(source_row, 0, source_parent).data())
        return self.needle in text


# (ad, grup): "a" grubunun satırları bitişik değil.
ROWS = [("a1", "a"), ("b1", "b"), ("a2", "a"), ("c1", "c"), ("b2", "b"), ("a3", "a")]


def _chain() -> tuple[QStandardItemModel, _Filter, GroupProxy]:
    model = QStandardItemModel(0, 2)
    for name, group in ROWS:
        model.appendRow([QStandardItem(name), QStandardItem(group)])
    flt = _Filter()
    flt.setSourceModel(model)
    proxy = GroupProxy()
    proxy.setSourceModel(flt)
    return model, flt, proxy


def _group(flt: _Filter) -> Callable[[], list[str]]:
    return lambda: [str(flt.index(row, 1).data()) for row in range(flt.rowCount())]


def _texts(proxy: GroupProxy) -> list[str]:
    out = []
    for r in range(proxy.rowCount()):
        name = proxy.header_group(r)
        out.append(f"[{name}]" if name is not None else str(proxy.index(r, 0).data()))
    return out


def test_pass_through_is_identity() -> None:
    _model, flt, proxy = _chain()
    assert not proxy.grouped
    assert proxy.rowCount() == flt.rowCount() == 6
    assert proxy.columnCount() == 2
    for r in range(6):
        assert proxy.mapToSource(proxy.index(r, 1)) == flt.index(r, 1)
        assert proxy.mapFromSource(flt.index(r, 1)) == proxy.index(r, 1)
        assert proxy.source_row(r) == r
        assert proxy.view_row(r) == r
        assert proxy.header_group(r) is None
    assert proxy.order() is None
    flt.set_needle("2")
    assert _texts(proxy) == ["a2", "b2"]


def test_groups_in_rank_order_and_non_adjacent_rows_gathered() -> None:
    _model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"b": 0, "a": 1, "c": 2})
    assert _texts(proxy) == ["[b]", "b1", "b2", "[a]", "a1", "a2", "a3", "[c]", "c1"]
    assert proxy.order() == [1, 4, 0, 2, 5, 3]
    assert [proxy.order_position(r) for r in range(6)] == [2, 0, 3, 5, 1, 4]
    assert proxy.source_row(0) == -1
    assert proxy.view_row(5) == 6  # a3
    assert proxy.mapFromSource(flt.index(3, 0)) == proxy.index(8, 0)
    assert not proxy.mapToSource(proxy.index(0, 0)).isValid()
    assert proxy.index(0, 0).data(HEADER_ROLE) == "b"
    assert proxy.index(1, 0).data(HEADER_ROLE) is None
    # Grubu sıralamada olmayan grup sona, ilk görülme sırasıyla eklenir.
    proxy.set_grouping(_group(flt), {"c": 0})
    assert _texts(proxy)[:3] == ["[c]", "c1", "[a]"]


def test_order_inside_group_follows_source_order() -> None:
    model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"a": 0, "b": 1, "c": 2})
    flt.sort(0, Qt.SortOrder.DescendingOrder)  # kaynak sıralanınca grup içi sıra da değişir, grup sırası değişmez
    assert _texts(proxy) == ["[a]", "a3", "a2", "a1", "[b]", "b2", "b1", "[c]", "c1"]
    assert model.rowCount() == 6


def test_header_is_not_selectable_or_editable() -> None:
    _model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"a": 0})
    flags = proxy.flags(proxy.index(0, 0))
    assert not flags & Qt.ItemFlag.ItemIsSelectable
    assert not flags & Qt.ItemFlag.ItemIsEditable
    assert proxy.flags(proxy.index(1, 0)) & Qt.ItemFlag.ItemIsSelectable


def test_collapse_and_expand() -> None:
    _model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"a": 0, "b": 1, "c": 2})
    removed: list[tuple[int, int]] = []
    proxy.rowsRemoved.connect(lambda _p, first, last: removed.append((first, last)))
    proxy.set_collapsed("a", True)
    assert removed == [(1, 3)]
    assert _texts(proxy) == ["[a]", "[b]", "b1", "b2", "[c]", "c1"]
    assert proxy.is_collapsed("a")
    assert proxy.view_row(0) == -1  # a1 katlı grupta
    assert proxy.order() == [0, 2, 5, 1, 4, 3]  # katlı satırlar sırada kalır
    inserted: list[tuple[int, int]] = []
    proxy.rowsInserted.connect(lambda _p, first, last: inserted.append((first, last)))
    proxy.set_collapsed("a", False)
    assert inserted == [(1, 3)]
    assert _texts(proxy)[:4] == ["[a]", "a1", "a2", "a3"]


def test_reveal_opens_collapsed_group() -> None:
    _model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"a": 0, "b": 1, "c": 2})
    proxy.set_collapsed("b", True)
    assert proxy.view_row(4) == -1
    view = proxy.reveal(4)  # b2
    assert not proxy.is_collapsed("b")
    assert view == proxy.view_row(4) == 6
    assert proxy.reveal(0) == 1  # açık gruptaki satır: yalnızca yeri döner
    assert proxy.reveal(99) == -1


def test_collapsed_group_stays_collapsed_through_filter_change() -> None:
    _model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"a": 0, "b": 1, "c": 2})
    proxy.set_collapsed("a", True)
    flt.set_needle("1")
    assert _texts(proxy) == ["[a]", "[b]", "b1", "[c]", "c1"]
    flt.set_needle("")
    assert _texts(proxy)[:2] == ["[a]", "[b]"]


def test_empty_groups_have_no_header() -> None:
    _model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"a": 0, "b": 1, "c": 2})
    flt.set_needle("c")
    assert _texts(proxy) == ["[c]", "c1"]


def test_data_changed_is_forwarded_with_group_header() -> None:
    model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"a": 0, "b": 1, "c": 2})
    seen: list[tuple[int, int]] = []
    proxy.dataChanged.connect(lambda top, bottom, _roles=(): seen.append((top.row(), bottom.row())))
    model.item(5, 0).setText("a3x")  # a3: görünümde 3. satır, başlığı 0
    assert (3, 3) in seen
    assert (0, 0) in seen
    seen.clear()
    proxy.set_grouping(None)
    model.item(5, 0).setText("a3y")
    assert seen == [(5, 5)]


@pytest.mark.parametrize("grouped", [False, True])
def test_selection_and_current_survive_filter_change(qtbot: QtBot, grouped: bool) -> None:
    _model, flt, proxy = _chain()
    if grouped:
        proxy.set_grouping(_group(flt), {"a": 0, "b": 1, "c": 2})
    view = QTableView()
    qtbot.addWidget(view)
    view.setModel(proxy)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    target = proxy.view_row(4)  # b2
    view.setCurrentIndex(proxy.index(target, 0))
    view.selectRow(target)
    flt.set_needle("2")  # b2 yerinde kalmaz ama seçili ve geçerli kalmalı
    current = view.currentIndex()
    assert current.isValid()
    assert proxy.mapToSource(current).data() == "b2"
    names = {proxy.mapToSource(i).data() for i in view.selectionModel().selectedRows()}
    assert names == {"b2"}
    flt.set_needle("1")  # seçili satır süzgeçten çıktı: seçim boşalır, yanlış satıra kaymaz
    assert {proxy.mapToSource(i).data() for i in view.selectionModel().selectedRows()} == set()


def test_source_change_batches_filter_signals_into_one_layout(qtbot: QtBot) -> None:
    _model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"a": 0, "b": 1, "c": 2})
    view = QTableView()
    qtbot.addWidget(view)
    view.setModel(proxy)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.selectRow(proxy.view_row(5))  # a3
    layouts: list[int] = []
    proxy.layoutChanged.connect(lambda *_a: layouts.append(1))
    with proxy.source_change():
        flt.set_needle("3")  # birden çok aralık kaldırılır
        assert not layouts  # sonda bir kez
    assert layouts == [1]
    assert _texts(proxy) == ["[a]", "a3"]
    assert [proxy.mapToSource(i).data() for i in view.selectionModel().selectedRows()] == ["a3"]


def test_qt_end_filter_change_emits_row_signals() -> None:
    """Qt davranışı (6.12): `endFilterChange` dinamik süzme kapalıyken satır ekleme/kaldırma sinyalleri yayar,
    yerleşim değişikliği ya da sıfırlama yaymaz. Vekil hepsini karşılar; bu test gelenin ne olduğunu sabitler."""
    _model, flt, _proxy = _chain()
    seen: list[str] = []
    flt.rowsRemoved.connect(lambda *_a: seen.append("removed"))
    flt.rowsInserted.connect(lambda *_a: seen.append("inserted"))
    flt.layoutChanged.connect(lambda *_a: seen.append("layout"))
    flt.modelReset.connect(lambda *_a: seen.append("reset"))
    flt.set_needle("2")
    flt.set_needle("")
    assert set(seen) <= {"removed", "inserted"}
    assert "removed" in seen
    assert "inserted" in seen


def test_qt_select_all_includes_unselectable_header_in_ranges(qtbot: QtBot) -> None:
    """Qt davranışı (6.12): Ctrl+A tek aralık seçer; aralığı sınırları seçilemez başlığı kapsasa da
    `selectedRows` başlığı vermez. Seçili satırlar aralıklardan okunurken başlıklar ayrıca atlanmalıdır."""
    _model, flt, proxy = _chain()
    proxy.set_grouping(_group(flt), {"a": 0, "b": 1, "c": 2})
    view = QTableView()
    qtbot.addWidget(view)
    view.setModel(proxy)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    view.selectAll()
    rows = {i.row() for i in view.selectionModel().selectedRows()}
    assert 0 not in rows  # başlık
    assert rows == {proxy.view_row(r) for r in range(6)}
    covered: set[int] = set()
    for part in view.selectionModel().selection():  # type: ignore[attr-defined]
        covered.update(range(part.top(), part.bottom() + 1))
    headers = {r for r in range(proxy.rowCount()) if proxy.header_group(r) is not None}
    assert covered & headers  # aralık başlığı kapsar
    view.selectionModel().select(
        proxy.index(0, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    )
    assert 0 not in {i.row() for i in view.selectionModel().selectedRows()}
