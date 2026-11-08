"""Durum sütunu: yazı yerine simge (ipucunda açıklama ve sorunlar).

Çevrilmedi gri boş daire, makine mavi bilgisayar, redakte yeşil bilgisayar (onay işaretli), onaylandı yeşil kişi
(onay işaretli), hatalı kırmızı üçgen; hata veya uyarısı olan satırda yanında ayrıca üçgen görünür (uyarı sarı,
hata kırmızı). Renkler temadan gelir; simgeler Lucide'dendir.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, QSize, Qt
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from nxceviri.core.translate.status import Status
from nxceviri.gui.icons import icon, pixmap
from nxceviri.gui.theme import current_tokens

#: Durum → (simge adı, tema rengi).
STATUS_ICONS: dict[Status, tuple[str, str]] = {
    Status.UNTRANSLATED: ("circle-dashed", "muted"),
    Status.MACHINE: ("monitor", "accent"),
    Status.REDACTED: ("monitor-check", "success"),
    Status.APPROVED: ("user-check", "success"),
    Status.ERROR: ("triangle-alert", "danger"),
}
#: Hata veya uyarısı olan satırda durum simgesinin yanındaki üçgen.
ISSUE_ICON = "triangle-alert"
ISSUE_TOKENS = {"error": "danger", "warning": "warning"}
STATUS_ROLE = Qt.ItemDataRole.UserRole + 20
ICON_SIZE = 16
_GAP = 4
_PADDING = 16

_Index = QModelIndex | QPersistentModelIndex


def status_icon(status: Status) -> QIcon:
    """Durum süzgecindeki seçenek için simge (hücredekiyle aynı)."""
    name, token = STATUS_ICONS[status]
    return icon(name, current_tokens()[token])


def issue_icon(severity: str = "warning") -> QIcon:
    return icon(ISSUE_ICON, current_tokens()[ISSUE_TOKENS[severity]])


def cell_width() -> int:
    """Durum sütununun varsayılan genişliği: iki simge sığar."""
    return 2 * ICON_SIZE + _GAP + 2 * _PADDING


class StatusDelegate(QStyledItemDelegate):
    """Durum hücresini ortalanmış simgelerle çizer; metin çizilmez, satır yüksekliğini etkilemez."""

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        return QSize(cell_width(), ICON_SIZE + _PADDING)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.icon = QIcon()
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        cell = index.data(STATUS_ROLE)
        if cell is None:
            return
        status, severity = cell
        tokens = current_tokens()
        name, token = STATUS_ICONS[status]
        shown = [(name, tokens[token])]
        if severity is not None and status != Status.ERROR:
            shown.append((ISSUE_ICON, tokens[ISSUE_TOKENS[severity]]))
        dpr = opt.widget.devicePixelRatioF() if opt.widget is not None else 1.0
        width = len(shown) * ICON_SIZE + (len(shown) - 1) * _GAP
        x = opt.rect.left() + (opt.rect.width() - width) // 2
        y = opt.rect.top() + (opt.rect.height() - ICON_SIZE) // 2
        for icon_name, color in shown:
            painter.drawPixmap(QPoint(x, y), pixmap(icon_name, color, ICON_SIZE, dpr))
            x += ICON_SIZE + _GAP
