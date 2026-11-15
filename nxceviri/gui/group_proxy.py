"""Çeviri tablosunun gruplu görünümü için vekil model (`GroupProxy`).

Süzgeç vekilinin (TranslationFilter) üstünde durur; tablo bu modeli görür. İki kipi vardır:

- **Birebir geçiş** (varsayılan): satır ve sütunlar süzgeçle aynıdır, sinyaller olduğu gibi iletilir.
- **Gruplu**: satırlar gruplarına göre öbeklenir, her öbeğin üstünde bir başlık satırı durur. Başlık
  yalnızca bu modelde vardır (kaynağı yoktur; seçilemez, düzenlenemez). Grup sırası verilen sıralamadır
  (`rank`), grup içi sıra kaynağın sırasıdır; bitişik olmayan satırlar da tek başlık altında toplanır.
  Katlanan grubun satırları görünümden çıkar ama `order()` içinde kalır (katlamak süzmek değildir).

Gruplu kipte kaynağın satır ekleme/kaldırma sinyalleri yerleşim değişikliğine çevrilir; seçim ve geçerli
satır kalıcı dizinlerle korunur. Bir süzgeç değişikliği çok sayıda aralık sinyali yayabildiği için, kaynağı
değiştiren çağrı `source_change()` içinde yapılırsa düzen tek seferde yeniden kurulur.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, overload

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractProxyModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

_Index = QModelIndex | QPersistentModelIndex

#: Başlık satırında grubun adı; gerçek satırda `None`.
HEADER_ROLE = Qt.ItemDataRole.UserRole + 40

#: Kaynağın bütün satırlarının grup adları (kaynak sırasıyla).
KeysFn = Callable[[], Sequence[str]]

# Başlığın kaynağı yoksa yerleşim değişikliğinde grup adıyla yeniden bulunur.
_Anchor = tuple[QPersistentModelIndex | None, str | None, int]


class GroupProxy(QAbstractProxyModel):
    """Süzgecin üstünde gruplu görünüm; gruplama kapalıyken birebir geçiş."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._keys: KeysFn | None = None
        self._rank: Mapping[str, int] = {}
        self._collapsed: set[str] = set()
        self._names: list[str] = []  # grup sırası
        self._members: dict[str, list[int]] = {}  # grup → kaynak satırlar (kaynak sırasıyla)
        self._group_of: list[str] = []  # kaynak satır → grup
        self._order: list[int] = []  # kaynak satırlar grup sırasıyla (katlılar dahil)
        self._position: list[int] = []  # kaynak satır → `_order` içindeki yeri
        self._view: list[int] = []  # görünüm satırı → kaynak satır; başlık: -(grup sırası + 1)
        self._to_view: list[int] = []  # kaynak satır → görünüm satırı; katlı grupta -1
        self._header_at: dict[str, int] = {}  # grup → başlığın görünüm satırı
        self._saved: tuple[list[QModelIndex], list[_Anchor]] | None = None
        self._batch = 0  # `source_change` derinliği
        self._batch_open = False  # toplu değişiklikte yerleşim bildirimi başladı mı

    # --- kip ve sorgular --------------------------------------------------------------------

    @property
    def grouped(self) -> bool:
        return self._keys is not None

    def set_grouping(self, keys: KeysFn | None, rank: Mapping[str, int] | None = None) -> None:
        """Gruplamayı açar (`keys`: kaynak satırlarının grup adları) ya da kapatır (`None`). Model sıfırlanır.

        `rank` grup sırasıdır; içinde olmayan gruplar sona, kaynakta ilk görüldükleri sırayla eklenir."""
        self.beginResetModel()
        self._keys = keys
        self._rank = dict(rank or {})
        self._rebuild()
        self.endResetModel()

    def is_collapsed(self, name: str) -> bool:
        return name in self._collapsed

    def set_collapsed(self, name: str, collapsed: bool) -> None:
        """Grubu katlar/açar; satırlar görünümden çıkar/girer (süzgeç ve sayılar değişmez)."""
        if collapsed == (name in self._collapsed):
            return
        header = self._header_at.get(name) if self.grouped else None
        if header is None:  # grup şu an görünmüyor: yalnızca durum hatırlanır
            self._collapsed.symmetric_difference_update({name})
            return
        count = len(self._members[name])
        if collapsed:
            self.beginRemoveRows(QModelIndex(), header + 1, header + count)
            self._collapsed.add(name)
            self._layout()
            self.endRemoveRows()
        else:
            self.beginInsertRows(QModelIndex(), header + 1, header + count)
            self._collapsed.discard(name)
            self._layout()
            self.endInsertRows()

    def set_all_collapsed(self, collapsed: bool) -> None:
        """Bütün grupları katlar ya da açar (tek yerleşim değişikliği; seçim ve geçerli satır korunur)."""
        wanted = set(self._names) if collapsed else set()
        if not self.grouped or wanted == self._collapsed & set(self._names):
            if not collapsed:
                self._collapsed.clear()
            return
        self._begin_layout()
        if collapsed:
            self._collapsed.update(self._names)
        else:
            self._collapsed.clear()
        self._end_layout(rebuild=False)

    def collapsed_groups(self) -> frozenset[str]:
        return frozenset(self._collapsed)

    def source_row(self, view_row: int) -> int:
        """Görünüm satırının kaynak (süzgeç) satırı; başlıkta ya da aralık dışında -1."""
        if not self.grouped:
            return view_row
        if 0 <= view_row < len(self._view):
            return max(self._view[view_row], -1)
        return -1

    def view_row(self, source_row: int) -> int:
        """Kaynak satırının görünüm satırı; katlı gruptaysa ya da aralık dışındaysa -1."""
        if not self.grouped:
            return source_row
        return self._to_view[source_row] if 0 <= source_row < len(self._to_view) else -1

    def header_group(self, view_row: int) -> str | None:
        """Görünüm satırı bir başlıksa grubunun adı, değilse `None`."""
        if self.grouped and 0 <= view_row < len(self._view) and self._view[view_row] < 0:
            return self._names[-self._view[view_row] - 1]
        return None

    def header_row(self, name: str) -> int:
        """Grubun başlık satırı; grup görünmüyorsa -1."""
        return self._header_at.get(name, -1) if self.grouped else -1

    def group_of(self, source_row: int) -> str | None:
        if self.grouped and 0 <= source_row < len(self._group_of):
            return self._group_of[source_row]
        return None

    def group_members(self, name: str) -> Sequence[int]:
        """Grubun süzgeçten geçen kaynak satırları (katlı olsa da)."""
        return self._members.get(name, ())

    def order(self) -> Sequence[int] | None:
        """Kaynak satırları görünüm sırasıyla, katlı gruplarınkiler dahil; birebir geçişte `None` (kaynak sırası)."""
        return self._order if self.grouped else None

    def order_position(self, source_row: int) -> int:
        """Kaynak satırının `order()` içindeki yeri (birebir geçişte kendisi); aralık dışında -1."""
        if not self.grouped:
            return source_row
        return self._position[source_row] if 0 <= source_row < len(self._position) else -1

    def reveal(self, source_row: int) -> int:
        """Kaynak satırının görünüm satırı; satır katlı bir gruptaysa grup önce açılır. Satır yoksa -1."""
        if not self.grouped:
            source: QAbstractItemModel | None = self.sourceModel()  # kaynak bağlanmadan önce None
            return source_row if source is not None and 0 <= source_row < source.rowCount() else -1
        name = self.group_of(source_row)
        if name is None:
            return -1
        if name in self._collapsed:
            self.set_collapsed(name, False)
        return self._to_view[source_row]

    @contextmanager
    def source_change(self) -> Iterator[None]:
        """Kaynağı değiştiren çağrıyı sarar: gruplu kipte ara sinyaller birikir, düzen sonda bir kez kurulur."""
        self._batch += 1
        try:
            yield
        finally:
            self._batch -= 1
            if not self._batch and self._batch_open:
                self._batch_open = False
                self._end_layout()

    # --- düzen ------------------------------------------------------------------------------

    def _rebuild(self) -> None:
        if self._keys is None:
            self._names, self._members, self._group_of, self._order, self._position = [], {}, [], [], []
            self._view, self._to_view, self._header_at = [], [], {}
            return
        group_of = list(self._keys())
        members: dict[str, list[int]] = {}
        for row, name in enumerate(group_of):
            members.setdefault(name, []).append(row)
        first = {name: i for i, name in enumerate(members)}
        last = len(self._rank)
        self._names = sorted(members, key=lambda g: (self._rank.get(g, last), first[g]))
        self._members, self._group_of = members, group_of
        self._order = [row for name in self._names for row in members[name]]
        self._position = [0] * len(group_of)
        for position, row in enumerate(self._order):
            self._position[row] = position
        self._layout()

    def _layout(self) -> None:
        view: list[int] = []
        to_view = [-1] * len(self._group_of)
        header_at: dict[str, int] = {}
        for number, name in enumerate(self._names):
            header_at[name] = len(view)
            view.append(-(number + 1))
            if name in self._collapsed:
                continue
            start = len(view)
            rows = self._members[name]
            view.extend(rows)
            for offset, row in enumerate(rows):
                to_view[row] = start + offset
        self._view, self._to_view, self._header_at = view, to_view, header_at

    def _anchor(self, index: QModelIndex) -> _Anchor:
        source = self.mapToSource(index)
        if source.isValid():
            return QPersistentModelIndex(source), None, index.column()
        return None, self.header_group(index.row()), index.column()

    def _begin_layout(self) -> None:
        self.layoutAboutToBeChanged.emit()
        saved = self.persistentIndexList()
        self._saved = (saved, [self._anchor(i) for i in saved])

    def _end_layout(self, rebuild: bool = True) -> None:
        if rebuild:
            self._rebuild()
        else:
            self._layout()
        if self._saved is not None:
            before, anchors = self._saved
            self._saved = None
            after: list[QModelIndex] = []
            for source, name, column in anchors:
                if source is not None:
                    after.append(self.mapFromSource(source) if source.isValid() else QModelIndex())
                else:
                    row = self._header_at.get(name) if name is not None else None
                    after.append(QModelIndex() if row is None else self.createIndex(row, column))
            self.changePersistentIndexList(before, after)
        self.layoutChanged.emit()

    # --- kaynağın sinyalleri ----------------------------------------------------------------

    def setSourceModel(self, source: QAbstractItemModel | None) -> None:
        """Kaynağı bağlar; `None` vekili kaynaktan koparır (sinyal işlemez, katlı gruplar hatırlanır)."""
        old: QAbstractItemModel | None = self.sourceModel()
        if old is not None:
            for signal, slot in self._connections(old):
                signal.disconnect(slot)
        self.beginResetModel()
        super().setSourceModel(source)  # type: ignore[arg-type]  # Qt kaynak olarak boş göstericiyi kabul eder
        if source is not None:
            for signal, slot in self._connections(source):
                signal.connect(slot)
        self._rebuild()
        self.endResetModel()

    def _connections(self, source: QAbstractItemModel) -> list[tuple[Any, Callable[..., None]]]:
        return [
            (source.modelAboutToBeReset, self._source_about_to_reset),
            (source.modelReset, self._source_reset),
            (source.layoutAboutToBeChanged, self._source_layout_about),
            (source.layoutChanged, self._source_layout_done),
            (source.rowsAboutToBeRemoved, self._source_rows_about_removed),
            (source.rowsRemoved, self._source_rows_removed),
            (source.rowsAboutToBeInserted, self._source_rows_about_inserted),
            (source.rowsInserted, self._source_rows_inserted),
            (source.rowsAboutToBeMoved, self._source_layout_about),
            (source.rowsMoved, self._source_layout_done),
            (source.columnsAboutToBeInserted, self._source_about_to_reset),
            (source.columnsInserted, self._source_reset),
            (source.columnsAboutToBeRemoved, self._source_about_to_reset),
            (source.columnsRemoved, self._source_reset),
            (source.columnsAboutToBeMoved, self._source_about_to_reset),
            (source.columnsMoved, self._source_reset),
            (source.dataChanged, self._source_data_changed),
            (source.headerDataChanged, self._source_header_changed),
        ]

    def _source_about_to_reset(self, *_args: object) -> None:
        self.beginResetModel()

    def _source_reset(self, *_args: object) -> None:
        self._rebuild()
        self.endResetModel()

    def _source_layout_about(self, *_args: object) -> None:
        if self.grouped and self._batch:
            if not self._batch_open:
                self._batch_open = True
                self._begin_layout()
            return
        self._begin_layout()

    def _source_layout_done(self, *_args: object) -> None:
        if self.grouped and self._batch:
            return
        self._end_layout()

    def _source_rows_about_removed(self, parent: QModelIndex, first: int, last: int) -> None:
        if self.grouped:
            self._source_layout_about()
        elif not parent.isValid():
            self.beginRemoveRows(QModelIndex(), first, last)

    def _source_rows_removed(self, parent: QModelIndex, *_args: object) -> None:
        if self.grouped:
            self._source_layout_done()
        elif not parent.isValid():
            self.endRemoveRows()

    def _source_rows_about_inserted(self, parent: QModelIndex, first: int, last: int) -> None:
        if self.grouped:
            self._source_layout_about()
        elif not parent.isValid():
            self.beginInsertRows(QModelIndex(), first, last)

    def _source_rows_inserted(self, parent: QModelIndex, *_args: object) -> None:
        if self.grouped:
            self._source_layout_done()
        elif not parent.isValid():
            self.endInsertRows()

    def _source_data_changed(self, top: QModelIndex, bottom: QModelIndex, roles: Sequence[int] = ()) -> None:
        if not top.isValid() or not bottom.isValid():
            return
        left, right = top.column(), bottom.column()
        if not self.grouped:
            self.dataChanged.emit(self.createIndex(top.row(), left), self.createIndex(bottom.row(), right), roles)
            return
        rows: list[int] = []
        headers: list[int] = []
        names: set[str] = set()
        for source_row in range(top.row(), min(bottom.row(), len(self._to_view) - 1) + 1):
            view = self._to_view[source_row]
            if view >= 0:
                rows.append(view)
            name = self._group_of[source_row]
            if name not in names:
                names.add(name)
                headers.append(self._header_at[name])
        if rows:
            self.dataChanged.emit(self.createIndex(min(rows), left), self.createIndex(max(rows), right), roles)
        if headers:  # başlıktaki sayı ve ilerleme bu satırlardan hesaplanır
            last = self.columnCount() - 1
            self.dataChanged.emit(self.createIndex(min(headers), 0), self.createIndex(max(headers), last))

    def _source_header_changed(self, orientation: Qt.Orientation, first: int, last: int) -> None:
        if orientation == Qt.Orientation.Horizontal or not self.grouped:
            self.headerDataChanged.emit(orientation, first, last)

    # --- QAbstractItemModel -----------------------------------------------------------------

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        if parent.isValid():
            return 0
        if self.grouped:
            return len(self._view)
        source: QAbstractItemModel | None = self.sourceModel()  # kaynak bağlanmadan önce None
        return 0 if source is None else source.rowCount()

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        source: QAbstractItemModel | None = self.sourceModel()  # kaynak bağlanmadan önce None
        return 0 if parent.isValid() or source is None else source.columnCount()

    def index(self, row: int, column: int, parent: _Index = QModelIndex()) -> QModelIndex:  # noqa: B008
        if parent.isValid() or not 0 <= row < self.rowCount() or not 0 <= column < self.columnCount():
            return QModelIndex()
        return self.createIndex(row, column)

    @overload
    def parent(self) -> QObject | None: ...
    @overload
    def parent(self, child: _Index) -> QModelIndex: ...
    def parent(self, child: _Index | None = None) -> QObject | QModelIndex | None:
        if child is None:
            return QObject.parent(self)
        return QModelIndex()

    def sibling(self, row: int, column: int, idx: _Index) -> QModelIndex:
        return self.index(row, column)

    def hasChildren(self, parent: _Index = QModelIndex()) -> bool:  # noqa: B008 - Qt imzası
        return not parent.isValid() and self.rowCount() > 0

    def buddy(self, index: _Index) -> QModelIndex:
        return self.index(index.row(), index.column())

    def mapToSource(self, proxyIndex: _Index) -> QModelIndex:  # noqa: N803 - Qt imzası
        source: QAbstractItemModel | None = self.sourceModel()  # kaynak bağlanmadan önce None
        if not proxyIndex.isValid() or source is None:
            return QModelIndex()
        row = proxyIndex.row()
        if self.grouped:
            row = self._view[row] if row < len(self._view) else -1
            if row < 0:
                return QModelIndex()
        return source.index(row, proxyIndex.column())

    def mapFromSource(self, sourceIndex: _Index) -> QModelIndex:  # noqa: N803 - Qt imzası
        if not sourceIndex.isValid():
            return QModelIndex()
        row = self.view_row(sourceIndex.row())
        return QModelIndex() if row < 0 else self.createIndex(row, sourceIndex.column())

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        source: QAbstractItemModel | None = self.sourceModel()  # kaynak bağlanmadan önce None
        if not index.isValid() or source is None:
            return None
        row = index.row()
        if self.grouped:
            row = self._view[row]
            if row < 0:
                return self._names[-row - 1] if role == HEADER_ROLE else None
        return source.data(source.index(row, index.column()), role)

    def flags(self, index: _Index) -> Qt.ItemFlag:
        if index.isValid() and self.header_group(index.row()) is not None:
            return Qt.ItemFlag.ItemIsEnabled
        source: QAbstractItemModel | None = self.sourceModel()  # kaynak bağlanmadan önce None
        if source is None:
            return Qt.ItemFlag.NoItemFlags
        return source.flags(self.mapToSource(index))

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        source: QAbstractItemModel | None = self.sourceModel()  # kaynak bağlanmadan önce None
        if source is None:
            return None
        if orientation == Qt.Orientation.Horizontal or not self.grouped:
            return source.headerData(section, orientation, role)
        return None
