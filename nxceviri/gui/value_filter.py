"""Excel tarzı çoklu seçimli süzgeç: başlıkta huni simgesi, açılan panelde arama ve onay kutulu değerler.

- `ValueFilter`: bir sütunun süzgeç durumu (seçili değerler; `None` = süzgeç yok) ve değer sayıları.
- `FilterHeader`: huni simgesini çizen ve tıklamasını ileten tablo başlığı (etkin süzgeçte huni dolu).
- `FilterPopup`: arama kutusu + "Tümü" + sanal değer listesi (binlerce anahtarda akıcı) + Temizle/Tamam.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QGuiApplication, QMouseEvent, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListView,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.languages import natural_sort_key
from nxceviri.gui.icons import ICON_DIR
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import button, format_int

_Index = QModelIndex | QPersistentModelIndex
FUNNEL_SIZE = 14
_FUNNEL_MARGIN = 6
#: Boş değerin listede görünen adı.
EMPTY_LABEL = "(boş)"

_funnel_cache: dict[tuple[str, bool, float], QPixmap] = {}


def funnel_pixmap(color: str, filled: bool, dpr: float = 1.0) -> QPixmap:
    """Huni simgesi (Lucide `funnel`); `filled` iken içi dolu çizilir (etkin süzgeç)."""
    key = (color, filled, dpr)
    cached = _funnel_cache.get(key)
    if cached is not None:
        return cached
    pixmap = QPixmap()
    try:
        text = (ICON_DIR / "funnel.svg").read_text(encoding="utf-8")
    except OSError:
        return pixmap
    if filled:
        text = text.replace('fill="none"', f'fill="{color}"', 1)
    renderer = QSvgRenderer(QByteArray(text.replace("currentColor", color).encode("utf-8")))
    if renderer.isValid():
        side = max(1, round(FUNNEL_SIZE * dpr))
        pixmap = QPixmap(side, side)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, side, side))
        painter.end()
        pixmap.setDevicePixelRatio(dpr)
    _funnel_cache[key] = pixmap
    return pixmap


class ValueFilter(QObject):
    """Bir sütunun çoklu seçimli süzgeci. `selected` boş (`None`) ise süzgeç yoktur, her değer geçer."""

    changed = Signal()

    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title
        self.values: list[tuple[str, int]] = []  # (değer, satır sayısı), doğal sırayla
        self.selected: frozenset[str] | None = None

    @property
    def active(self) -> bool:
        return self.selected is not None

    def accepts(self, value: str) -> bool:
        return self.selected is None or value in self.selected

    def set_values(self, counts: dict[str, int]) -> None:
        """Tablodaki değerleri ve sayılarını bildirir; artık olmayan seçili değerler düşer (sinyal gönderilmez)."""
        self.values = sorted(counts.items(), key=lambda kv: natural_sort_key(kv[0]))
        if self.selected is not None:
            kept = self.selected & counts.keys()
            self.selected = kept or None

    def set_selected(self, selected: Iterable[str] | None) -> None:
        new = None if selected is None else frozenset(selected)
        if new == self.selected:
            return
        self.selected = new
        self.changed.emit()

    def clear(self) -> None:
        self.set_selected(None)

    # --- kalıcılık: seçim ya da dışlananlar, hangisi kısaysa ------------------------------

    def to_json(self) -> str:
        """Kaydedilecek metin; süzgeç yoksa boş. Binlerce değerde seçimin tümleyeni daha kısaysa o yazılır."""
        if self.selected is None:
            return ""
        every = {v for v, _n in self.values}
        excluded = every - self.selected
        if len(excluded) < len(self.selected):
            return json.dumps({"out": sorted(excluded)}, ensure_ascii=False)
        return json.dumps({"in": sorted(self.selected)}, ensure_ascii=False)

    def load_json(self, text: str) -> None:
        """`to_json` çıktısını yükler (bozuksa süzgeç kaldırılır); değerler önce `set_values` ile bildirilmiş olmalı."""
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = None
        every = {v for v, _n in self.values}
        chosen: set[str] | None = None
        if isinstance(data, dict) and isinstance(data.get("in"), list):
            chosen = {str(v) for v in data["in"]} & every
        elif isinstance(data, dict) and isinstance(data.get("out"), list):
            chosen = every - {str(v) for v in data["out"]}
        self.selected = frozenset(chosen) if chosen else None


class _ValueModel(QAbstractListModel):
    """Panelin sanal listesi: görünen (aramaya uyan) değerler ve işaretli olanlar."""

    def __init__(self, values: list[tuple[str, int]], checked: set[str]) -> None:
        super().__init__()
        self._all = values
        self.shown = values
        self.checked = checked

    def set_query(self, query: str) -> None:
        q = query.strip().casefold()
        self.beginResetModel()
        self.shown = self._all if not q else [kv for kv in self._all if q in kv[0].casefold()]
        self.endResetModel()

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(self.shown)

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        value, count = self.shown[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{value or EMPTY_LABEL}  ({format_int(count)})"
        if role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if value in self.checked else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.ToolTipRole:
            return value or EMPTY_LABEL
        return None

    def flags(self, index: _Index) -> Qt.ItemFlag:
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable

    def setData(self, index: _Index, value: object, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.CheckStateRole or not index.isValid():
            return False
        item = self.shown[index.row()][0]
        if value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value):
            self.checked.add(item)
        else:
            self.checked.discard(item)
        self.dataChanged.emit(index, index, [role])
        return True

    def set_shown_checked(self, on: bool) -> None:
        names = {v for v, _n in self.shown}
        if on:
            self.checked |= names
        else:
            self.checked -= names
        if self.shown:
            self.dataChanged.emit(self.index(0), self.index(len(self.shown) - 1), [Qt.ItemDataRole.CheckStateRole])

    def shown_state(self) -> Qt.CheckState:
        if not self.shown:
            return Qt.CheckState.Unchecked
        hits = sum(1 for v, _n in self.shown if v in self.checked)
        if hits == 0:
            return Qt.CheckState.Unchecked
        return Qt.CheckState.Checked if hits == len(self.shown) else Qt.CheckState.PartiallyChecked


class FilterPopup(QFrame):
    """Süzgeç paneli. Tamam/Temizle `filter` üzerine yazar ve paneli kapatır."""

    def __init__(self, vf: ValueFilter, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("filterPopup")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._filter = vf
        all_values = {v for v, _n in vf.values}
        checked = set(all_values if vf.selected is None else vf.selected)
        self.model = _ValueModel(vf.values, checked)
        self._all_values = all_values
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Ara…")
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)
        self.all_box = QCheckBox("Tümü")
        self.all_box.setTristate(True)
        lay.addWidget(self.all_box)
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setUniformItemSizes(True)  # binlerce değerde ölçüm yapılmaz
        self.list.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.list.setMinimumSize(260, 200)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.clear_button = button("Temizle")
        self.ok_button = button("Tamam", "primary")
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.ok_button)
        lay.addLayout(row)
        self.search.textChanged.connect(self._query_changed)
        self.all_box.clicked.connect(self._all_clicked)
        self.model.dataChanged.connect(lambda *_args: self._refresh_state())
        self.model.modelReset.connect(self._refresh_state)
        self.clear_button.clicked.connect(self._clear)
        self.ok_button.clicked.connect(self._apply)
        self._refresh_state()

    def _query_changed(self, text: str) -> None:
        self.model.set_query(text)

    def _all_clicked(self) -> None:
        # Üç durumlu kutu: tıklayınca "karışık" yerine tamamen işaretle ya da kaldır.
        self.model.set_shown_checked(self.model.shown_state() != Qt.CheckState.Checked)

    def _refresh_state(self) -> None:
        self.all_box.blockSignals(True)
        self.all_box.setCheckState(self.model.shown_state())
        self.all_box.blockSignals(False)
        self.ok_button.setEnabled(bool(self.model.checked))
        self.ok_button.setToolTip("" if self.model.checked else "En az bir değer işaretleyin.")

    def _apply(self) -> None:
        checked = self.model.checked
        self._filter.set_selected(None if checked >= self._all_values else checked)
        self.close()

    def _clear(self) -> None:
        self._filter.clear()
        self.close()

    def popup_below(self, global_pos: QPoint) -> None:
        self.adjustSize()
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        pos = QPoint(global_pos)
        if screen is not None:
            area = screen.availableGeometry()
            pos.setX(max(area.left(), min(pos.x(), area.right() - self.width())))
        self.move(pos)
        self.show()
        self.search.setFocus()


class FilterHeader(QHeaderView):
    """Süzgeçli sütunların başlığına huni çizer; hunine tıklamak `filter_clicked` gönderir (sıralamayı tetiklemez)."""

    filter_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._filters: dict[int, ValueFilter] = {}
        self._pressed_funnel = False

    def set_filter(self, col: int, vf: ValueFilter) -> None:
        self._filters[col] = vf
        vf.changed.connect(self.viewport().update)

    def funnel_rect(self, col: int) -> QRect:
        """Sütun başlığında hunin yeri (görünür başlık koordinatlarında)."""
        left = self.sectionViewportPosition(col)
        width = self.sectionSize(col)
        return QRect(
            left + width - FUNNEL_SIZE - _FUNNEL_MARGIN,
            (self.height() - FUNNEL_SIZE) // 2,
            FUNNEL_SIZE,
            FUNNEL_SIZE,
        )

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int) -> None:  # noqa: N803 - Qt imzası
        vf = self._filters.get(logicalIndex)
        if vf is None or self.isSectionHidden(logicalIndex):
            super().paintSection(painter, rect, logicalIndex)
            return
        # Başlık metni ve sıralama oku huninin soluna sığar; üst üste binmez.
        inner = QRect(rect)
        inner.setRight(rect.right() - FUNNEL_SIZE - 2 * _FUNNEL_MARGIN + 2)
        super().paintSection(painter, inner, logicalIndex)
        tokens = current_tokens()
        rest = QRect(inner.right() + 1, rect.top(), rect.right() - inner.right(), rect.height())
        painter.fillRect(rest, QColor(tokens["surface2"]))
        painter.fillRect(QRect(rest.left(), rest.bottom(), rest.width(), 1), QColor(tokens["border"]))
        shot = funnel_pixmap(tokens["accent" if vf.active else "muted"], vf.active, self.devicePixelRatioF())
        painter.drawPixmap(self.funnel_rect(logicalIndex).topLeft(), shot)

    def _funnel_at(self, pos: QPoint) -> int | None:
        col = self.logicalIndexAt(pos)
        if col in self._filters and self.funnel_rect(col).adjusted(-3, -4, 3, 4).contains(pos):
            return col
        return None

    def mousePressEvent(self, e: QMouseEvent) -> None:
        col = self._funnel_at(e.position().toPoint())
        self._pressed_funnel = col is not None
        if col is not None:
            self.filter_clicked.emit(col)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._pressed_funnel:
            self._pressed_funnel = False
            e.accept()
            return
        super().mouseReleaseEvent(e)
