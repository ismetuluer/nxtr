"""Gruplu görünümün başlık satırı: bilgisi (`GroupHeader`), çizimi ve tablodaki etkileşimi (`GroupTableView`).

Başlık satırı yalnızca `GroupProxy`de vardır; hücre delegate'leri onu çizmez. Tablo, sıradan çizimden sonra
görünen her başlık satırının dikdörtgeninin tamamına (sütunlara bölünmeden, span kullanmadan) bandı çizer: solda
aç/kapa oku, kalın grup adı (uzunsa ortadan kısalır), satır sayısı rozeti; sağda bilinen bir sorun varsa uyarı
simgesi ve çevrilen/toplam ilerlemesi. Tıklama ve klavye (Boşluk/Enter, ←/→) katlama isteği olarak bildirilir;
katlamanın kendisi sayfadadır. Renkler tema belirteçlerinden gelir; simgeler `icons.pixmap` ile keskin çizilir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QHelpEvent, QKeyEvent, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QToolTip, QWidget

from nxceviri.gui.icons import pixmap
from nxceviri.gui.table_columns import FitTableView
from nxceviri.gui.theme import current_tokens

_PAD = 10
_ICON = 14
_BAR_WIDTH = 72
_BAR_HEIGHT = 4
_GAP = 8


@dataclass(frozen=True)
class GroupHeader:
    """Bir grup başlığının gösterdikleri; sayılar süzgeçten geçen satırlara göredir."""

    name: str
    count: int
    translated: int
    warned: bool
    collapsed: bool


def header_tip(info: GroupHeader) -> str:
    """Başlığın ipucu: tam ad, sayılar ve varsa sorun notu."""
    text = f"{info.name}\n{info.count} satır · {info.translated} çevrildi"
    if info.warned:
        text += "\nBu grupta hata ya da uyarı olan satır var."
    return text


def paint_header(
    painter: QPainter, rect: QRect, info: GroupHeader, font: QFont, dpr: float, *, hover: bool, current: bool
) -> None:
    """Başlık bandını `rect` içine çizer."""
    tokens = current_tokens()
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.fillRect(rect, QColor(tokens["surface2"]))
    if current or hover:
        tint = QColor(tokens["selection"])
        if not current:
            tint.setAlpha(140)
        painter.fillRect(rect, tint)
    painter.setPen(QColor(tokens["border"]))
    painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
    mid = rect.center().y()

    # Sağ taraf: ilerleme çubuğu ve (varsa) uyarı simgesi.
    right = rect.right() - _PAD
    bar = QRectF(right - _BAR_WIDTH, mid - _BAR_HEIGHT / 2, _BAR_WIDTH, _BAR_HEIGHT)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(tokens["border"]))
    painter.drawRoundedRect(bar, 2, 2)
    if info.count:
        done = info.translated / info.count
        color = tokens["success"] if info.translated >= info.count else tokens["accent"]
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * done, bar.height()), 2, 2)
    right = int(bar.left()) - _GAP
    if info.warned:
        warn = pixmap("triangle-alert", tokens["warning"], _ICON, dpr)
        painter.drawPixmap(right - _ICON, mid - _ICON // 2, warn)
        right -= _ICON + _GAP

    # Sol taraf: ok, ad, sayı rozeti.
    left = rect.left() + _PAD
    arrow = pixmap("chevron-down", tokens["muted"], _ICON, dpr)
    painter.save()
    painter.translate(left + _ICON / 2, mid)
    if info.collapsed:
        painter.rotate(-90)
    painter.drawPixmap(-_ICON // 2, -_ICON // 2, arrow)
    painter.restore()
    left += _ICON + _GAP

    badge_font = QFont(font)
    badge_metrics = QFontMetrics(badge_font)
    badge_text = str(info.count)
    badge_width = badge_metrics.horizontalAdvance(badge_text) + 12
    bold = QFont(font)
    bold.setBold(True)
    metrics = QFontMetrics(bold)
    room = max(right - left - badge_width - _GAP, 0)
    name = metrics.elidedText(info.name, Qt.TextElideMode.ElideMiddle, room)
    painter.setFont(bold)
    painter.setPen(QColor(tokens["text"]))
    name_width = metrics.horizontalAdvance(name)
    painter.drawText(QRect(left, rect.top(), name_width + 2, rect.height()), Qt.AlignmentFlag.AlignVCenter, name)
    left += name_width + _GAP
    if left + badge_width <= right:
        height = badge_metrics.height() + 2
        badge = QRectF(left, mid - height / 2, badge_width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens["surface"]))
        painter.drawRoundedRect(badge, height / 2, height / 2)
        painter.setFont(badge_font)
        painter.setPen(QColor(tokens["muted"]))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, badge_text)
    painter.restore()


#: Katlama isteği: `None` aç/kapa, `True` katla, `False` aç.
Fold = bool | None


class GroupTableView(FitTableView):
    """Gruplu görünümü bilen tablo: başlık bandını çizer, başlıkta tıklama ve tuşları katlama isteğine çevirir.

    Başlık bilgisi `header_at` ile sorulur (sayfa verir); başlık olmayan satırda `None`dur. Gruplama kapalıyken
    `header_at` hep `None` döner ve tablo sıradan `FitTableView` gibi davranır.
    """

    #: Başlıkta katlama isteği: (görünüm satırı, `Fold`).
    fold_requested = Signal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self.header_at: Callable[[int], GroupHeader | None] = lambda _row: None
        self._hover = -1
        self.setMouseTracking(True)

    def _header_row_at(self, pos: QPoint) -> int:
        row = self.rowAt(pos.y())
        return row if row >= 0 and self.header_at(row) is not None else -1

    def mousePressEvent(self, event: QMouseEvent) -> None:
        row = self._header_row_at(event.position().toPoint())
        if row >= 0 and event.button() == Qt.MouseButton.LeftButton:
            self.setCurrentIndex(self.model().index(row, max(self.currentIndex().column(), 0)))
            self.fold_requested.emit(row, None)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._header_row_at(event.position().toPoint()) >= 0:
            event.accept()  # ikinci tık yeniden katlamasın, düzenleyici açılmasın
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        row = self._header_row_at(event.position().toPoint())
        if row != self._hover:
            self._hover = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self._hover >= 0:
            self._hover = -1
            self.viewport().update()
        super().leaveEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        row = self.currentIndex().row()
        if row >= 0 and self.header_at(row) is not None and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            fold: dict[int, Fold] = {
                Qt.Key.Key_Space: None,
                Qt.Key.Key_Return: None,
                Qt.Key.Key_Enter: None,
                Qt.Key.Key_Left: True,
                Qt.Key.Key_Right: False,
            }
            if event.key() in fold:
                self.fold_requested.emit(row, fold[event.key()])
                event.accept()
                return
        super().keyPressEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            row = self.rowAt(event.pos().y())
            info = self.header_at(row) if row >= 0 else None
            if info is not None:
                QToolTip.showText(event.globalPos(), header_tip(info), self.viewport())
                return True
        return super().viewportEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        viewport: QWidget = self.viewport()
        first = self.rowAt(event.rect().top())
        last = self.rowAt(event.rect().bottom())
        if first < 0:
            return
        last = self.model().rowCount() - 1 if last < 0 else last
        current = self.currentIndex().row()
        painter: QPainter | None = None
        for row in range(first, last + 1):
            info = self.header_at(row)
            if info is None:
                continue
            if painter is None:
                painter = QPainter(viewport)
            rect = QRect(0, self.rowViewportPosition(row), viewport.width(), self.rowHeight(row))
            paint_header(
                painter,
                rect,
                info,
                self.font(),
                viewport.devicePixelRatioF(),
                hover=row == self._hover,
                current=row == current,
            )
        if painter is not None:
            painter.end()
