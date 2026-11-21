"""Adım listesinin işaretleri: tema simge yerine daire, küp, düğüm ya da metin imleci isteyebilir.

Her çizici, işaretin merkezini ve renkleri alır; durum `done` (tamamlandı), `current` (seçili adım) ya da `pending`
(bekliyor) olur. `icon` türü simgeyi çizen `step_nav` içinde kalır; burada yalnızca diğer dört tür vardır.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF

from nxceviri.gui.theme_style import ThemeStyle

DONE = "done"
CURRENT = "current"
PENDING = "pending"

#: İşaret türü → işaretin yatay payı (piksel); `icon` için simge boyudur. Düğümde numara payı ayrıca eklenir.
_SLOTS = {"icon": 18, "knob": 24, "cube": 20, "node": 12, "cursor": 18}
KNOB_SIZE = 24
NODE_SIZE = 12
_NODE_GAP = 8
_NUMBER_PX = 11


def _number_font(style: ThemeStyle) -> QFont:
    font = QFont(style.mono_font) if style.mono_font else QFont()
    font.setPixelSize(_NUMBER_PX)
    return font


def number_text(number: int) -> str:
    """Düğümün yanındaki iki haneli numara: 1 → "01"."""
    return f"{number:02d}"


def marker_slot(style: ThemeStyle) -> int:
    """İşaretin ad ile arasındaki yatay payı: kare düğümde yanındaki "01" numarası da dahildir."""
    slot = _SLOTS[style.step_marker]
    if style.step_marker == "node":
        slot += _NODE_GAP + QFontMetrics(_number_font(style)).horizontalAdvance("00")
    return slot


def _knob(
    painter: QPainter,
    center: QPoint,
    state: str,
    *,
    number: int,
    done: bool,
    ink: QColor,
    ground: QColor,
    font: QFont,
) -> None:
    radius = KNOB_SIZE / 2
    circle = QRectF(center.x() - radius, center.y() - radius, KNOB_SIZE, KNOB_SIZE)
    painter.setFont(font)
    if state == PENDING:
        painter.setPen(QPen(ink, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(circle.adjusted(1, 1, -1, -1))
        painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, str(number))
        return
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    painter.drawEllipse(circle)
    painter.setPen(QPen(ground, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if done:
        cx, cy = center.x(), center.y()
        painter.drawPolyline([QPointF(cx - 5, cy), QPointF(cx - 1.5, cy + 3.5), QPointF(cx + 5, cy - 3.5)])
    else:
        painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, str(number))


def _cube_points(center: QPoint, half: float) -> tuple[QPolygonF, QPolygonF, QPolygonF]:
    cx, cy = center.x(), center.y()
    rise = half / 2
    top = QPolygonF(
        [QPointF(cx, cy - half), QPointF(cx + half, cy - rise), QPointF(cx, cy), QPointF(cx - half, cy - rise)]
    )
    left = QPolygonF(
        [QPointF(cx - half, cy - rise), QPointF(cx, cy), QPointF(cx, cy + half), QPointF(cx - half, cy + rise)]
    )
    right = QPolygonF(
        [QPointF(cx, cy), QPointF(cx + half, cy - rise), QPointF(cx + half, cy + rise), QPointF(cx, cy + half)]
    )
    return top, left, right


def _cube(painter: QPainter, center: QPoint, state: str, accent: QColor, muted: QColor) -> None:
    top, left, right = _cube_points(center, 9.0)
    if state == PENDING:
        painter.setPen(QPen(muted, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for face in (top, left, right):
            painter.drawPolygon(face)
        return
    painter.setPen(Qt.PenStyle.NoPen)
    for face, shade in ((top, accent), (left, accent.darker(135)), (right, accent.darker(185))):
        painter.setBrush(shade)
        painter.drawPolygon(face)


def _node(
    painter: QPainter,
    center: QPoint,
    state: str,
    *,
    number: int,
    accent: QColor,
    muted: QColor,
    style: ThemeStyle,
) -> None:
    half = NODE_SIZE // 2
    square = QRect(center.x() - half, center.y() - half, NODE_SIZE, NODE_SIZE)
    if state == CURRENT:  # hafif ışıma: arkada büyük, yarı saydam kare
        glow = QColor(accent)
        glow.setAlpha(55)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRect(square.adjusted(-4, -4, 4, 4))
        painter.setPen(QPen(accent, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(square.adjusted(1, 1, -1, -1))
    elif state == DONE:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRect(square)
    else:
        painter.setPen(QPen(muted, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(square.adjusted(1, 1, -1, -1))
    font = _number_font(style)
    painter.setFont(font)
    painter.setPen(accent if state == CURRENT else muted)
    text_left = square.right() + _NODE_GAP
    painter.drawText(
        QRect(text_left, square.top() - 4, QFontMetrics(font).horizontalAdvance("00") + 4, NODE_SIZE + 8),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        number_text(number),
    )


def _cursor(painter: QPainter, center: QPoint, state: str, ink: QColor, font: QFont) -> None:
    glyph = {CURRENT: "▶", DONE: "✓"}.get(state, "·")
    font = QFont(font)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(ink)
    box = QRect(center.x() - 9, center.y() - 12, 18, 24)
    painter.drawText(box, Qt.AlignmentFlag.AlignCenter, glyph)


def paint_marker(
    painter: QPainter,
    style: ThemeStyle,
    center: QPoint,
    state: str,
    number: int,
    *,
    done: bool,
    ink: QColor,
    ground: QColor,
    accent: QColor,
    muted: QColor,
    font: QFont,
) -> None:
    """`style.step_marker` türündeki işareti `center` merkezli çizer.

    `done` adımın tamamlandığını söyler (seçili adımda da onay işareti çizilir). `ink` işaretin yazı rengi
    (seçili satırda seçili yazı rengi), `ground` işaretin arkasındaki zemin (daire içindeki onay/numara bu renkle
    çizilir), `accent` vurgu, `muted` soluk renktir. Kare düğümde `center` karenin merkezidir; numara sağına çizilir.
    """
    kind = style.step_marker
    if kind == "knob":
        _knob(painter, center, state, number=number, done=done, ink=ink, ground=ground, font=font)
    elif kind == "cube":
        _cube(painter, center, state, accent, muted)
    elif kind == "node":
        _node(painter, center, state, number=number, accent=accent, muted=muted, style=style)
    elif kind == "cursor":
        _cursor(painter, center, state, ink, font)
