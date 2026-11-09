"""Tablo sütun davranışları (Çevir ve Kontrol Et tabloları ortak kullanır).

- `FitTableView`: yumuşak (piksel bazlı) kaydırma; hücreye tıklayınca ya da program bir satırı seçince tablo
  yatayda kendiliğinden kaymaz, ama klavye gezinmesinde (ok tuşları, Tab) geçerli hücre görünür kalır.
- `ColumnFitter`: akıllı sığdırma. Esnek sütunlar (Orijinal, Çeviri) her zaman görünür ve kalan genişliği
  paylaşır; dar sütunlar sabit genişliktedir. Pencere küçülünce önce dar sütunlar daralır. Kullanıcı bir
  sütunu elle ayarlayınca genişlikler saklanır ve artık kendiliğinden değişmez.
- `HeaderColumnMenu`: başlığa sağ tık → sütunları gizle/göster; seçim kalıcıdır.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPersistentModelIndex, QPoint, QSettings, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTableView

#: Tekerlek bir adımda bu kadar satır yüksekliği kaydırır.
WHEEL_ROWS = 3
_ROW_PADDING = 14

_Index = QModelIndex | QPersistentModelIndex


def _ints(text: str) -> list[int] | None:
    """ "1,2,3" → [1, 2, 3]; bozuk değerde None (ayar yok sayılır)."""
    if not text:
        return []
    try:
        return [int(x) for x in text.split(",")]
    except ValueError:
        return None


class FitTableView(QTableView):
    """Yumuşak kaydırmalı ve yatayda kendiliğinden kaymayan tablo."""

    def __init__(self) -> None:
        super().__init__()
        self._keyboard_nav = False
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def wheel_step(self) -> int:
        """Tekerlek adımının piksel karşılığı: `WHEEL_ROWS` satır yüksekliği (Qt bir çentikte 3 tek adım kaydırır)."""
        return self.fontMetrics().height() + _ROW_PADDING

    def updateGeometries(self) -> None:
        super().updateGeometries()
        step = self.wheel_step()
        self.verticalScrollBar().setSingleStep(step)
        self.horizontalScrollBar().setSingleStep(step)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self._keyboard_nav = True
        try:
            super().keyPressEvent(event)
        finally:
            self._keyboard_nav = False

    def scrollTo(
        self, index: _Index, hint: QAbstractItemView.ScrollHint = QAbstractItemView.ScrollHint.EnsureVisible
    ) -> None:
        """Satırı dikeyde görünür kılar. Yatay konum yalnızca klavye gezinmesinde değişir (hücre ekran dışında
        kalmasın); tıklama ve program kaynaklı seçim tabloyu yana kaydırmaz."""
        bar = self.horizontalScrollBar()
        keep = bar.value()
        super().scrollTo(index, hint)
        if not self._keyboard_nav:
            bar.setValue(keep)


class ColumnFitter(QObject):
    """Sütun genişliklerini görünür alana sığdırır (bkz. modül açıklaması)."""

    #: Genişlikler değişti: satır yükseklikleri yeniden ölçülmeli.
    resized = Signal()

    def __init__(
        self,
        view: QTableView,
        fixed: dict[int, tuple[int, int]],
        flex: dict[int, tuple[float, int]],
    ) -> None:
        """`fixed`: sütun → (varsayılan, en az genişlik). `flex`: sütun → (ağırlık, en az genişlik)."""
        super().__init__(view)
        self._view = view
        self._fixed = dict(fixed)
        self._flex = dict(flex)
        self._header = view.horizontalHeader()
        self.user_sized = False
        self._fitting = False
        self._settings: QSettings | None = None
        self._key = ""
        self._header.sectionResized.connect(self._on_section_resized)
        self._viewport = view.viewport()
        self._viewport.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._viewport and event.type() == QEvent.Type.Resize:
            self.fit()
        return super().eventFilter(watched, event)

    def _visible(self, cols: dict[int, tuple[int, int]] | dict[int, tuple[float, int]]) -> list[int]:
        return [c for c in cols if not self._view.isColumnHidden(c)]

    def fit(self) -> None:
        """Kullanıcı elle ayarlamadıysa genişlikleri görünür alana dağıtır."""
        if self.user_sized:
            return
        avail = self._view.viewport().width()
        fixed, flex = self._visible(self._fixed), self._visible(self._flex)
        if avail <= 0 or not flex:
            return
        flex_min = sum(self._flex[c][1] for c in flex)
        widths = {c: self._fixed[c][0] for c in fixed}
        # Esnek sütunlara en az genişlikleri kalsın diye dar sütunlar, en az genişliklerine kadar orantılı daralır.
        excess = sum(widths.values()) - max(avail - flex_min, 0)
        room = {c: widths[c] - self._fixed[c][1] for c in fixed}
        total_room = sum(room.values())
        if excess > 0 and total_room > 0:
            for c in fixed:
                widths[c] -= min(room[c], int(excess * room[c] / total_room) + 1)
        free = max(avail - sum(widths.values()), flex_min)
        weight_total = sum(self._flex[c][0] for c in flex)
        left = free
        for c in flex[:-1]:
            share = max(self._flex[c][1], int(free * self._flex[c][0] / weight_total))
            widths[c] = share
            left -= share
        last = flex[-1]
        widths[last] = max(self._flex[last][1], left)
        self._apply(widths)

    def _apply(self, widths: dict[int, int]) -> None:
        changed = False
        self._fitting = True
        try:
            for c, w in widths.items():
                if self._header.sectionSize(c) != w:
                    self._header.resizeSection(c, w)
                    changed = True
        finally:
            self._fitting = False
        if changed:
            self.resized.emit()

    def set_hidden(self, col: int, hidden: bool) -> None:
        """Sütunu gizler/gösterir; bu bir kullanıcı genişlik ayarı sayılmaz."""
        self._fitting = True
        try:
            self._view.setColumnHidden(col, hidden)
        finally:
            self._fitting = False
        self.fit()
        self.resized.emit()

    def reset(self) -> None:
        """Elle ayarlanmış genişlikleri unutur ve yeniden sığdırır."""
        self.user_sized = False
        if self._settings is not None:
            self._settings.remove(self._key)
        self.fit()

    # --- kalıcılık -----------------------------------------------------------------------

    def bind_settings(self, settings: QSettings, key: str) -> None:
        """Kayıtlı genişlikleri geri yükler (sütun sayısı uymuyorsa yok sayılır)."""
        self._settings, self._key = settings, key
        widths = _ints(str(settings.value(key, "")))
        count = self._header.count()
        if widths is None or len(widths) != count:
            return
        self._fitting = True
        try:
            for c, w in enumerate(widths):
                self._header.resizeSection(c, max(self._header.minimumSectionSize(), w))
        finally:
            self._fitting = False
        self.user_sized = True
        self.resized.emit()

    def _save(self) -> None:
        if self._settings is not None:
            h = self._header
            self._settings.setValue(self._key, ",".join(str(h.sectionSize(c)) for c in range(h.count())))

    def _on_section_resized(self, _col: int, _old: int, _new: int) -> None:
        if self._fitting:
            return
        self.user_sized = True
        self._save()
        self.resized.emit()


class HeaderColumnMenu(QObject):
    """Başlığa sağ tık menüsü: sütunları gizle/göster (seçim kalıcı)."""

    #: Bir sütun gizlendi/gösterildi: (sütun, gizli mi).
    toggled = Signal(int, bool)

    def __init__(
        self,
        view: QTableView,
        labels: dict[int, str],
        locked: frozenset[int],
        fitter: ColumnFitter | None = None,
    ) -> None:
        """`labels`: menüde listelenecek sütunlar; `locked`: gizlenemeyenler (işaretli ve soluk görünür)."""
        super().__init__(view)
        self._view = view
        self._labels = dict(labels)
        self._locked = locked
        self._fitter = fitter
        self._settings: QSettings | None = None
        self._key = ""
        header = view.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._popup)

    def hidden(self) -> set[int]:
        return {c for c in self._labels if self._view.isColumnHidden(c)}

    def bind_settings(self, settings: QSettings, key: str) -> None:
        self._settings, self._key = settings, key
        saved = _ints(str(settings.value(key, "")))
        for c in saved or []:
            if c in self._labels and c not in self._locked:
                self._set_hidden(c, True, save=False)

    def _set_hidden(self, col: int, hidden: bool, save: bool = True) -> None:
        if self._fitter is not None:
            self._fitter.set_hidden(col, hidden)
        else:
            self._view.setColumnHidden(col, hidden)
        if save and self._settings is not None:
            self._settings.setValue(self._key, ",".join(str(c) for c in sorted(self.hidden())))
        self.toggled.emit(col, hidden)

    def build_menu(self) -> QMenu:
        """Menüyü kurar (sütunlar başlıktaki görsel sırayla)."""
        menu = QMenu(self._view.horizontalHeader())
        header = self._view.horizontalHeader()
        for visual in range(header.count()):
            col = header.logicalIndex(visual)
            if col not in self._labels:
                continue
            act = menu.addAction(self._labels[col])
            act.setCheckable(True)
            act.setChecked(not self._view.isColumnHidden(col))
            if col in self._locked:
                act.setEnabled(False)
                act.setToolTip("Bu sütun gizlenemez.")
            else:
                act.toggled.connect(lambda on, c=col: self._set_hidden(c, not on))
        if self._fitter is not None:
            menu.addSeparator()
            menu.addAction("Sütun genişliklerini sıfırla").triggered.connect(self._fitter.reset)
        menu.setToolTipsVisible(True)
        return menu

    def _popup(self, pos: QPoint) -> None:
        menu = self.build_menu()
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.popup(self._view.horizontalHeader().mapToGlobal(pos))
