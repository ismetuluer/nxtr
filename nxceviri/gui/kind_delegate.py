"""Kod türü tablosunun "Tür" sütunu: açılır liste yalnızca hücre düzenlenirken oluşturulur.

Binlerce kod etiketli projede her satıra bir `QComboBox` koymak ekran açılışını saniyelerce dondurur; bunun yerine
hücre bir kalem gibi çizilir, çift tıklanınca açılır liste çıkar.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QObject, QPersistentModelIndex, Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from nxceviri.core.translate.codekinds import KIND_NAMES

KIND_ROLE = Qt.ItemDataRole.UserRole  # hücrenin türü (görünen ad değil, tür anahtarı)


def kind_name(kind: str) -> str:
    """Türün okunur adı; kullanıcının kendi adlandırdığı tür olduğu gibi gösterilir."""
    return KIND_NAMES.get(kind, kind)


class KindDelegate(QStyledItemDelegate):
    """Tür seçimi: düzenleyici `QComboBox`; seçim yapılınca `kind_chosen(kod, tür)` yayılır."""

    kind_chosen = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QWidget:
        combo = QComboBox(parent)
        for kind, name in KIND_NAMES.items():
            combo.addItem(name, kind)
        current = str(index.data(KIND_ROLE))
        if combo.findData(current) < 0:  # kullanıcının kendi adlandırdığı tür
            combo.addItem(current, current)
        combo.activated.connect(lambda _i, box=combo: self._finish(box))
        opener = QTimer(combo)  # düzenleyici açılınca liste de açılsın: tek tıkla seçim
        opener.setSingleShot(True)
        opener.timeout.connect(combo.showPopup)
        opener.start(0)
        return combo

    def _finish(self, combo: QComboBox) -> None:
        self.commitData.emit(combo)
        self.closeEditor.emit(combo)

    def setEditorData(self, editor: QWidget, index: QModelIndex | QPersistentModelIndex) -> None:
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(max(editor.findData(str(index.data(KIND_ROLE))), 0))

    def setModelData(
        self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        if not isinstance(editor, QComboBox):
            return
        kind = str(editor.currentData())
        if kind == str(index.data(KIND_ROLE)):
            return
        model.setData(index, kind, KIND_ROLE)
        model.setData(index, kind_name(kind), Qt.ItemDataRole.DisplayRole)
        self.kind_chosen.emit(str(model.index(index.row(), 0).data()), kind)
