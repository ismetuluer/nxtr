"""Kenar çubuğu: simgeli adım listesi, sağda rozetler ve üstte proje başlığı.

`StepNav`, `QListWidget`'in tüm arayüzünü korur (`setCurrentRow`, `currentRowChanged`, `item(i)`, öğe bayrakları);
yalnızca çizimi bir `QStyledItemDelegate` ile yapılır. Öğelerin simge adı, rozet metni ve durumu öğe verisindedir,
böylece simgeler her çizimde geçerli tema renkleriyle üretilir ve tema değişince bayatlamaz.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QResizeEvent
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from nxceviri.gui import icons
from nxceviri.gui.theme import current_tokens

#: (adım adı, simge adı); sıra `MainWindow.STEP_*` sabitleriyle aynıdır.
STEPS: tuple[tuple[str, str], ...] = (
    ("Oyunu Ekle", "circle-plus"),
    ("Metinleri Tara", "scan-search"),
    ("Çevir", "languages"),
    ("Kontrol Et", "shield-check"),
    ("Dışa Aktar", "package"),
)
DONE_ICON = "circle-check"

ICON_ROLE = Qt.ItemDataRole.UserRole + 1
BADGE_ROLE = Qt.ItemDataRole.UserRole + 2
STATE_ROLE = Qt.ItemDataRole.UserRole + 3
DONE_ROLE = Qt.ItemDataRole.UserRole + 4

ICON_SIZE = 18
_PAD = 10
_GAP = 8
#: Rozet durumu → tema belirteci.
_BADGE_TOKENS = {"neutral": "muted", "success": "success", "warning": "warning", "danger": "danger"}
#: Rozet alanı en az bu metin kadar genişlik ayırır (örn. büyük sayılar kırpılmasın).
_WIDEST_BADGE = "%100"
_MIN_WIDTH = 188
#: Öğe çiziminin kenarlardan içeri çekildiği piksel (`paint` içindeki `adjusted`).
_ITEM_INSET = 2
#: Listenin iç dolgusu (sol + sağ); QSS'teki `padding: … 8px … 8px` ile aynı olmalı.
LIST_PADDING = 16

_Index = QModelIndex | QPersistentModelIndex


def _fixed_width(badge_width: int) -> int:
    """Adım adı dışında kalan yatay pay: kenar boşlukları, simge ve (varsa) rozet."""
    badge = badge_width + _GAP if badge_width else 0
    return 2 * _ITEM_INSET + 1 + 2 * _PAD + ICON_SIZE + _GAP + badge


def text_room(viewport_width: int, badge_width: int) -> int:
    """Adım adına kalan genişlik (piksel). `paint` ve `StepNav.preferred_width` aynı hesabı kullanır."""
    return viewport_width - _fixed_width(badge_width)


class _StepDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        return QSize(0, max(36, option.fontMetrics.height() + 16))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        tokens = current_tokens()
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        done = bool(index.data(DONE_ROLE))
        rect = option.rect.adjusted(_ITEM_INSET, _ITEM_INSET, -_ITEM_INSET, -_ITEM_INSET)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if selected or (hovered and enabled):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens["selection" if selected else "surface2"]))
            painter.drawRoundedRect(rect, 8, 8)
        text_color = QColor(tokens["text" if enabled else "muted"])
        icon_color = tokens["success"] if (done and enabled) else tokens["accent" if enabled else "muted"]
        mark = icons.icon(str(index.data(ICON_ROLE)), icon_color, ICON_SIZE).pixmap(ICON_SIZE, ICON_SIZE)
        painter.drawPixmap(QPoint(rect.left() + _PAD, rect.center().y() - ICON_SIZE // 2 + 1), mark)

        font = QFont(option.font)
        font.setBold(selected)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        right = rect.right() - _PAD
        badge = str(index.data(BADGE_ROLE) or "")
        if badge:
            state = str(index.data(STATE_ROLE) or "neutral")
            badge_color = QColor(tokens[_BADGE_TOKENS.get(state, "muted")] if enabled else tokens["muted"])
            painter.setPen(badge_color)
            width = metrics.horizontalAdvance(badge)
            painter.drawText(
                QRect(right - width, rect.top(), width, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                badge,
            )
            right -= width + _GAP
        left = rect.left() + _PAD + ICON_SIZE + _GAP
        room = max(0, text_room(option.rect.width(), metrics.horizontalAdvance(badge) if badge else 0))
        painter.setPen(text_color)
        text = metrics.elidedText(str(index.data(Qt.ItemDataRole.DisplayRole)), Qt.TextElideMode.ElideRight, room)
        painter.drawText(
            QRect(left, rect.top(), room, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )
        painter.restore()


class StepNav(QListWidget):
    """Beş adımlı kenar çubuğu listesi (`objectName` = `stepNav`)."""

    #: Yazı tipi değişince (genişlik yeniden hesaplansın diye).
    preferred_width_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("stepNav")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(_StepDelegate(self))
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        for name, icon_name in STEPS:
            item = QListWidgetItem(name)
            item.setData(ICON_ROLE, icon_name)
            item.setData(BADGE_ROLE, "")
            item.setData(STATE_ROLE, "neutral")
            item.setData(DONE_ROLE, False)
            self.addItem(item)

    def set_badge(self, step: int, text: str = "", state: str = "neutral") -> None:
        item = self.item(step)
        item.setData(BADGE_ROLE, text)
        item.setData(STATE_ROLE, state)
        self.viewport().update()

    def set_done(self, step: int, done: bool) -> None:
        item = self.item(step)
        item.setData(DONE_ROLE, done)
        item.setData(ICON_ROLE, DONE_ICON if done else STEPS[step][1])
        self.viewport().update()

    def preferred_width(self) -> int:
        """En uzun adım adı (seçilince kalın), simge ve en geniş rozet için gereken genişlik."""
        bold = QFont(self.font())
        bold.setBold(True)
        metrics = QFontMetrics(bold)
        text = max(metrics.horizontalAdvance(self.item(i).text()) for i in range(self.count()))
        badge = max(
            [metrics.horizontalAdvance(_WIDEST_BADGE)]
            + [metrics.horizontalAdvance(str(self.item(i).data(BADGE_ROLE) or "")) for i in range(self.count())]
        )
        return max(_MIN_WIDTH, text + _fixed_width(badge) + LIST_PADDING)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self.preferred_width_changed.emit()


class ProjectHeader(QWidget):
    """Kenar çubuğunun üstündeki proje adı ve oyun bilgisi (uzunsa sonu kısaltılır, tamamı ipucundadır)."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("navHeader")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 16, 8)
        lay.setSpacing(2)
        self.name_label = QLabel()
        self.name_label.setProperty("role", "navTitle")
        self.detail_label = QLabel()
        self.detail_label.setProperty("role", "muted")
        lay.addWidget(self.name_label)
        lay.addWidget(self.detail_label)
        self._name = ""
        self._detail = ""
        self.set_project("")

    def set_project(self, name: str, detail: str = "") -> None:
        self._name = name
        self._detail = detail
        self.name_label.setToolTip(name)
        self.detail_label.setToolTip(detail)
        self.detail_label.setVisible(bool(detail))
        self._elide()

    def _elide(self) -> None:
        room = max(40, self.width() - 36)
        for label, full in ((self.name_label, self._name), (self.detail_label, self._detail)):
            label.setText(QFontMetrics(label.font()).elidedText(full, Qt.TextElideMode.ElideRight, room))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()
