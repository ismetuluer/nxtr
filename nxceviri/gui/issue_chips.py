"""Sorunlar panosu yardımcıları: satır kıran yerleşim, tür çipleri ve açılır "Gelişmiş" bölümü."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_ERROR, SEVERITY_WARNING
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.widgets import format_int, tip_html

_SEVERITY_ICONS = {SEVERITY_ERROR: ("circle-x", "danger"), SEVERITY_WARNING: ("triangle-alert", "warning")}
_INFO_ICON = ("info", "muted")


class FlowLayout(QLayout):
    """Öğeleri soldan sağa dizer, sığmayanı alt satıra kaydırır."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._gap = spacing
        self.setContentsMargins(QMargins(0, 0, 0, 0))

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect: QRect, *, apply: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_height = area.x(), area.y(), 0
        for item in self._items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            if x + hint.width() > area.right() + 1 and line_height > 0:
                x, y, line_height = area.x(), y + line_height + self._gap, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._gap
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


class ChipBar(QWidget):
    """Bulgu türü çipleri: yalnızca bulgusu olan türler görünür, çoklu seçim; hiçbiri seçili değilse hepsi."""

    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.chips: dict[str, QToolButton] = {}
        flow = FlowLayout(self)
        for kind in KIND_LABELS:
            chip = QToolButton()
            chip.setCheckable(True)
            chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.hide()
            chip.toggled.connect(lambda _c: self.selection_changed.emit())
            flow.addWidget(chip)
            self.chips[kind] = chip
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.hide()

    def set_counts(self, counts: Mapping[str, int], severities: Mapping[str, str]) -> None:
        """Her türün bulgu sayısını ve en ağır önemini yazar; bulgusu kalmayan türün seçimi bırakılır."""
        dropped = False
        for kind, chip in self.chips.items():
            n = counts.get(kind, 0)
            if n == 0 and chip.isChecked():
                chip.blockSignals(True)
                chip.setChecked(False)
                chip.blockSignals(False)
                dropped = True
            chip.setVisible(n > 0)
            chip.setText(f"{KIND_LABELS[kind]} {format_int(n)}")
            name, tone = _SEVERITY_ICONS.get(severities.get(kind, ""), _INFO_ICON)
            bind_icon(chip, name, size=14, tone=tone)
            chip.setToolTip(tip_html("Bu türdeki bulguları göster. Birden çok tür seçilebilir."))
        self.setVisible(any(counts.get(k, 0) > 0 for k in self.chips))
        self.updateGeometry()
        if dropped:
            self.selection_changed.emit()

    def visible_kinds(self) -> list[str]:
        return [k for k, c in self.chips.items() if not c.isHidden()]

    def selected_kinds(self) -> frozenset[str]:
        return frozenset(k for k, c in self.chips.items() if c.isChecked())


class Disclosure(QWidget):
    """Başlığa tıklayınca açılıp kapanan bölüm ("Gelişmiş")."""

    def __init__(self, title: str) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setProperty("role", "link")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        bind_icon(self.toggle, "chevron-down", size=14)
        self.toggle.toggled.connect(self._toggled)
        lay.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        self.body.hide()
        lay.addWidget(self.body)

    def _toggled(self, open_: bool) -> None:
        self.body.setVisible(open_)
        bind_icon(self.toggle, "chevron-up" if open_ else "chevron-down", size=14)
