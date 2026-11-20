"""Kontrol Et'in sekme çubuğu: simge üstte, ad altta, köşesinde durum rozeti olan karolar."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QSizePolicy, QWidget

from nxceviri.gui.icons import pixmap
from nxceviri.gui.tab_badges import Badge, accessible_name
from nxceviri.gui.theme import current_tokens

TILE_SIZE = QSize(104, 72)
_ICON = 26
_BADGE_H = 18
_GLYPH = 11


class TabTile(QAbstractButton):
    """Seçilebilir karo. Simge ve ad kendi çizilir (renkler temadan, çizim anında okunur); rozet sağ üst köşededir."""

    def __init__(self, title: str, icon_name: str) -> None:
        super().__init__()
        self._title = title
        self._icon_name = icon_name
        self._badge: Badge | None = None
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(TILE_SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setText(title)
        self._refresh_name()

    @property
    def title(self) -> str:
        return self._title

    @property
    def badge(self) -> Badge | None:
        return self._badge

    def set_badge(self, badge: Badge | None) -> None:
        if badge == self._badge:
            return
        self._badge = badge
        self._refresh_name()
        self.update()

    def _refresh_name(self) -> None:
        name = accessible_name(self._title, self._badge)
        self.setAccessibleName(name)
        self.setToolTip(name if self._badge is not None else "")

    def sizeHint(self) -> QSize:
        return TILE_SIZE

    def paintEvent(self, _event: QPaintEvent) -> None:
        t = current_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        selected = self.isChecked()
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["selection"]))
            painter.drawRoundedRect(body, 10, 10)
        elif self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["surface2"]))
            painter.drawRoundedRect(body, 10, 10)
        if self.hasFocus():
            painter.setPen(QPen(QColor(t["accent"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(body.adjusted(1, 1, -1, -1), 9, 9)
        color = t["accent"] if selected else t["muted"]
        dpr = self.devicePixelRatioF()
        icon_x = (self.width() - _ICON) // 2
        icon_y = 10
        painter.drawPixmap(icon_x, icon_y, pixmap(self._icon_name, color, _ICON, dpr))
        font = QFont(self.font())
        font.setPointSizeF(max(8.0, font.pointSizeF() - 0.5))
        font.setBold(selected)
        painter.setFont(font)
        painter.setPen(QColor(color))
        text_rect = QRectF(4, icon_y + _ICON + 6, self.width() - 8, 20)
        elided = QFontMetrics(font).elidedText(self._title, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), elided)
        if self._badge is not None:
            self._paint_badge(painter, self._badge, icon_x + _ICON, icon_y)
        painter.end()

    def _paint_badge(self, painter: QPainter, badge: Badge, anchor_x: int, anchor_y: int) -> None:
        t = current_tokens()
        dpr = self.devicePixelRatioF()
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 2))
        font.setBold(True)
        width = _BADGE_H
        if badge.text:
            width = max(_BADGE_H, QFontMetrics(font).horizontalAdvance(badge.text) + 10)
        rect = QRectF(anchor_x - width / 2 - 2, anchor_y - 6, width, _BADGE_H)
        painter.setPen(QPen(QColor(t["surface"]), 1.5))
        painter.setBrush(QColor(t[badge.tone]))
        painter.drawRoundedRect(rect, _BADGE_H / 2, _BADGE_H / 2)
        ink = t["accent_text"]
        if badge.glyph:
            glyph = pixmap(badge.glyph, ink, _GLYPH, dpr)
            painter.drawPixmap(round(rect.center().x() - _GLYPH / 2), round(rect.center().y() - _GLYPH / 2), glyph)
        else:
            painter.setFont(font)
            painter.setPen(QColor(ink))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), badge.text)


class QaTabBar(QWidget):
    """Karoların tek seferde bir tanesi seçili olduğu çubuk; seçim `index_selected` ile bildirilir."""

    index_selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._tiles: list[TabTile] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.index_selected)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self._lay.addStretch(1)

    def add_tile(self, title: str, icon_name: str) -> TabTile:
        tile = TabTile(title, icon_name)
        self._group.addButton(tile, len(self._tiles))
        self._lay.insertWidget(len(self._tiles), tile)
        self._tiles.append(tile)
        return tile

    def tile(self, index: int) -> TabTile:
        return self._tiles[index]

    def tiles(self) -> list[TabTile]:
        return list(self._tiles)

    def set_current(self, index: int) -> None:
        """Dışarıdan (kodla) seçim; `index_selected` yayılmaz."""
        if 0 <= index < len(self._tiles):
            self._tiles[index].setChecked(True)
