"""Maskot: logodaki iki Joy-Con; çubukları göz olur.

Dururken gözler logodaki yerindedir (sol üst, sağ alt). Bir şey olunca (çalışıyor, bitti, hata, uyku) sol göz aşağı
düşüp yerden seker, sağ göz yukarı zıplayıp tavandan seker; ortada buluşup yüz kurarlar ve ağız belirir. Boşa dönünce
aynı yoldan (sol yerden, sağ tavandan sekerek) yerlerine dönerler. Boşta arada göz kırpar, çalışırken bakınır, bitince
sevinip hoplar, hatada kaşları endişeyle kalkar, uzun boşta uyur.

Çizim tamamen `QPainter` ile (vektör; 16 px'ten 128 px'e her boyutta net). Windows "animasyonları azalt" açıksa
geçişler anında olur. Ayarlar → Görünüm → "Maskotu göster" kapalıyken bütün maskotlar gizlenir (`set_mascot_enabled`).
"""

from __future__ import annotations

import math
import weakref
from dataclasses import dataclass

from PySide6.QtCore import QElapsedTimer, QPointF, QRandomGenerator, QRectF, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid

from nxceviri.gui.motion import animations_enabled

MOOD_IDLE = "idle"
MOOD_WORKING = "working"
MOOD_DONE = "done"
MOOD_ERROR = "error"
MOOD_SLEEP = "sleep"
#: Yüz kurulan hâller (boşta gözler logodaki yerindedir).
FACE_MOODS = frozenset({MOOD_WORKING, MOOD_DONE, MOOD_ERROR, MOOD_SLEEP})
MOOD_NAMES = {
    MOOD_IDLE: "Hazır",
    MOOD_WORKING: "Çalışıyor…",
    MOOD_DONE: "Bitti",
    MOOD_ERROR: "Bir sorun var",
    MOOD_SLEEP: "Uyuyor",
}

#: Ayar anahtarı (uygulama ayarı): maskot görünsün mü.
KEY_MASCOT = "appearance/mascot"

BLUE = QColor("#00B4E6")
RED = QColor("#FF3C28")
INK = QColor("#1E1E1E")

#: Çizim 256 × 256 birimlik kutuda yapılır (logodaki küçük simgenin ölçüleri).
_BOX = 256.0
_EYE_R = 30.0
_LEFT_REST = QPointF(65.68, 78.32)
_RIGHT_REST = QPointF(190.32, 182.0)
_LEFT_FACE = QPointF(68.0, 104.0)
_RIGHT_FACE = QPointF(188.0, 104.0)
_MOUTH = QPointF(128.0, 178.0)
#: Gözün sekeceği yer (sol) ve tavan (sağ): gövdenin iç kenarı.
_FLOOR = 236.0 - _EYE_R - 6
_CEILING = 20.0 + _EYE_R + 6

TRAVEL_MS = 800
HOP_MS = 450
BLINK_MS = 140
FRAME_MS = 33
#: Geçişin ilk bölümü: duvara (yer/tavan) varış; kalanı sekip hedefe çıkış.
_FALL = 0.45


def _ease_in(u: float) -> float:
    return u * u


def _ease_out_back(u: float) -> float:
    c1 = 1.4
    c3 = c1 + 1
    return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2


def bounce_point(start: QPointF, end: QPointF, wall: float, t: float) -> QPointF:
    """Duvardan (yer ya da tavan) sekerek `start`tan `end`e giden noktanın `t` ∈ [0, 1] anındaki yeri."""
    t = min(1.0, max(0.0, t))
    x = start.x() + (end.x() - start.x()) * t
    if t < _FALL:
        u = _ease_in(t / _FALL)
        y = start.y() + (wall - start.y()) * u
    else:
        u = _ease_out_back((t - _FALL) / (1 - _FALL))
        y = wall + (end.y() - wall) * u
    return QPointF(x, y)


@dataclass(frozen=True)
class Pose:
    """Bir karede çizilecek hâl: gözlerin yeri, ifade, bakış (−1 sol … 1 sağ), göz kırpma (0 açık … 1 kapalı),
    hoplama (birim cinsinden yukarı) ve ifadenin görünürlüğü (0 … 1; yüz kurulurken ağız belirir)."""

    left: QPointF
    right: QPointF
    mood: str
    look: float = 0.0
    blink: float = 0.0
    hop: float = 0.0
    expression: float = 1.0
    zz: float = 0.0


def rest_pose(mood: str = MOOD_IDLE) -> Pose:
    if mood in FACE_MOODS:
        return Pose(_LEFT_FACE, _RIGHT_FACE, mood)
    return Pose(_LEFT_REST, _RIGHT_REST, MOOD_IDLE)


def _halves(p: QPainter) -> None:
    r2 = 136.0
    left = QPainterPath()
    left.moveTo(124, 20)
    left.lineTo(84, 20)
    left.arcTo(QRectF(16, 20, r2, r2), 90, 90)
    left.lineTo(16, 168)
    left.arcTo(QRectF(16, 100, r2, r2), 180, 90)
    left.lineTo(124, 236)
    left.closeSubpath()
    right = QPainterPath()
    right.moveTo(132, 20)
    right.lineTo(172, 20)
    right.arcTo(QRectF(104, 20, r2, r2), 90, -90)
    right.lineTo(240, 168)
    right.arcTo(QRectF(104, 100, r2, r2), 0, -90)
    right.lineTo(132, 236)
    right.closeSubpath()
    p.fillPath(left, BLUE)
    p.fillPath(right, RED)


def _stroke(p: QPainter, width: float) -> None:
    p.setPen(QPen(INK, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)


def _eye(p: QPainter, c: QPointF, pose: Pose, face: bool) -> None:
    r = _EYE_R
    shaped = face and pose.expression > 0.5
    if shaped and pose.mood == MOOD_DONE:  # ^ ^
        _stroke(p, 9)
        path = QPainterPath()
        path.moveTo(c.x() - r * 0.8, c.y() + r * 0.3)
        path.quadTo(c.x(), c.y() - r, c.x() + r * 0.8, c.y() + r * 0.3)
        p.drawPath(path)
        return
    if (shaped and pose.mood == MOOD_SLEEP) or pose.blink >= 0.95:  # kapalı göz
        _stroke(p, 9)
        path = QPainterPath()
        path.moveTo(c.x() - r * 0.8, c.y())
        path.quadTo(c.x(), c.y() + r * 0.7, c.x() + r * 0.8, c.y())
        p.drawPath(path)
        return
    squash = 1.0 - pose.blink
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(INK)
    p.drawEllipse(c, r, r * squash)
    pupil = r * (0.32 if shaped and pose.mood == MOOD_ERROR else 0.45)
    pc = QPointF(c.x() + pose.look * r * 0.38, c.y() - r * 0.15 * squash)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(pc, pupil, pupil * squash)


def _brows(p: QPainter, pose: Pose) -> None:
    """Endişeli kaşlar: iç uçları yukarıda."""
    _stroke(p, 8)
    for c, inner in ((pose.left, 1), (pose.right, -1)):
        y = c.y() - 48
        p.drawLine(QPointF(c.x() - inner * 26, y + 6), QPointF(c.x() + inner * 22, y - 8))


def _mouth(p: QPainter, mood: str) -> None:
    c = _MOUTH
    w = 26.0
    _stroke(p, 8)
    path = QPainterPath()
    if mood == MOOD_DONE:
        p.setBrush(INK)
        path.moveTo(c.x() - w, c.y() - 6)
        path.quadTo(c.x(), c.y() + 34, c.x() + w, c.y() - 6)
        path.closeSubpath()
    elif mood == MOOD_ERROR:
        path.moveTo(c.x() - w, c.y() + 6)
        path.cubicTo(c.x() - w / 2, c.y() - 8, c.x() + w / 2, c.y() + 14, c.x() + w, c.y())
    elif mood == MOOD_SLEEP:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(INK)
        p.drawEllipse(c, 7, 9)
        return
    else:
        path.moveTo(c.x() - w * 0.7, c.y())
        path.quadTo(c.x(), c.y() + 16, c.x() + w * 0.7, c.y())
    p.drawPath(path)


def _zz(p: QPainter, phase: float, color: QColor) -> None:
    font = QFont()
    font.setBold(True)
    for i, (size, x, y) in enumerate(((44.0, 196.0, 52.0), (30.0, 230.0, 18.0))):
        drift = math.sin(phase * 2 * math.pi + i) * 4
        font.setPixelSize(int(size))
        p.setFont(font)
        p.setPen(color)
        p.drawText(QPointF(x, y + drift), "z")


def paint_mascot(p: QPainter, rect: QRectF, pose: Pose, text_color: QColor | None = None) -> None:
    """Maskotu `rect`e (kareye sığdırarak) çizer."""
    side = min(rect.width(), rect.height())
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(rect.center().x() - side / 2, rect.center().y() - side / 2)
    p.scale(side / _BOX, side / _BOX)
    p.translate(0, -pose.hop)
    _halves(p)
    face = pose.mood in FACE_MOODS
    _eye(p, pose.left, pose, face)
    _eye(p, pose.right, pose, face)
    if face and pose.expression > 0:
        p.setOpacity(pose.expression)
        if pose.mood == MOOD_ERROR:
            _brows(p, pose)
        _mouth(p, pose.mood)
        p.setOpacity(1.0)
    if pose.mood == MOOD_SLEEP and pose.expression > 0.5 and side >= 20:
        _zz(p, pose.zz, text_color or INK)
    p.restore()


_live: weakref.WeakSet[MascotWidget] = weakref.WeakSet()
#: Maskotlar görünsün mü (tek ayar, bütün maskotlar için).
_switch = {"enabled": True}


def mascot_enabled() -> bool:
    return _switch["enabled"]


def mascot_setting(settings: QSettings) -> bool:
    return str(settings.value(KEY_MASCOT, "true")).lower() == "true"


def save_mascot_setting(settings: QSettings, on: bool) -> None:
    settings.setValue(KEY_MASCOT, "true" if on else "false")
    set_mascot_enabled(on)


def set_mascot_enabled(on: bool) -> None:
    """Bütün maskotları gösterir ya da gizler (Ayarlar → Görünüm)."""
    _switch["enabled"] = on
    for widget in list(_live):
        if not isValid(widget):  # Qt tarafı silinmiş (Python sarmalayıcısı henüz toplanmamış)
            _live.discard(widget)
            continue
        if widget.parentWidget() is not None or not on:  # üstsüz bileşen gösterilirse ayrı pencere açılırdı
            QWidget.setVisible(widget, on and widget.wanted_visible)


class MascotWidget(QWidget):
    """Kare maskot. `set_mood` hâli değiştirir; yüz kurulup bozulurken gözler sekerek yer değiştirir."""

    def __init__(self, size: int = 24, mood: str = MOOD_IDLE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(QSize(size, size))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.wanted_visible = True
        self.mood = mood
        self._pose = rest_pose(mood)
        self._from = self._pose
        self._travel = False
        self._clock = QElapsedTimer()
        self._clock.start()
        self._started = 0
        self._hop_started: int | None = None
        self._blink_started: int | None = None
        self._frame = QTimer(self)
        self._frame.setInterval(FRAME_MS)
        self._frame.timeout.connect(self._tick)
        self._blinker = QTimer(self)
        self._blinker.setSingleShot(True)
        self._blinker.timeout.connect(self._blink)
        self._schedule_blink()
        self.setToolTip(MOOD_NAMES[mood])
        _live.add(self)
        if not mascot_enabled():
            super().setVisible(False)  # açıkça gizli: üst bileşen gösterilince de görünmez

    # --- dışarıdan --------------------------------------------------------------------------

    def setVisible(self, visible: bool) -> None:
        self.wanted_visible = visible
        super().setVisible(visible and mascot_enabled())

    def set_mood(self, mood: str) -> None:
        if mood == self.mood:
            return
        before = self.mood
        self.mood = mood
        self.setToolTip(MOOD_NAMES.get(mood, ""))
        travels = (before in FACE_MOODS) != (mood in FACE_MOODS)
        if not animations_enabled():
            self._pose = rest_pose(mood)
            self._travel = False
            self._frame.stop()
            self.update()
            return
        now = self._clock.elapsed()
        if travels:
            self._from = Pose(self._pose.left, self._pose.right, before)
            self._travel = True
            self._started = now
        if mood == MOOD_DONE:
            self._hop_started = now + (TRAVEL_MS if travels else 0)
        self._frame.start()
        self._tick()

    @property
    def pose(self) -> Pose:
        return self._pose

    @property
    def animating(self) -> bool:
        return self._frame.isActive()

    # --- animasyon ---------------------------------------------------------------------------

    def _schedule_blink(self) -> None:
        self._blinker.start(QRandomGenerator.global_().bounded(4000, 8000))

    def _blink(self) -> None:
        if self.isVisible() and self.mood in (MOOD_IDLE, MOOD_WORKING) and animations_enabled():
            self._blink_started = self._clock.elapsed()
            self._frame.start()
        self._schedule_blink()

    def _tick(self) -> None:
        now = self._clock.elapsed()
        target = rest_pose(self.mood)
        if not self.isVisible():  # görünmeyen maskot için kare çizilmez; görününce son hâlinden başlar
            self._frame.stop()
            self._travel = False
            self._hop_started = self._blink_started = None
            self._pose = target
            return
        left, right, expression = target.left, target.right, 1.0
        busy = False
        if self._travel:
            t = (now - self._started) / TRAVEL_MS
            if t >= 1:
                self._travel = False
            else:
                busy = True
                left = bounce_point(self._from.left, target.left, _FLOOR, t)
                right = bounce_point(self._from.right, target.right, _CEILING, t)
                # Yüz kurulurken ifade sona doğru belirir; bozulurken hemen kalkar.
                expression = max(0.0, (t - 0.8) / 0.2) if self.mood in FACE_MOODS else 0.0
        hop = 0.0
        if self._hop_started is not None:
            u = (now - self._hop_started) / HOP_MS
            if u >= 1:
                self._hop_started = None
            else:
                busy = True
                hop = math.sin(math.pi * max(0.0, u)) * 18
        blink = 0.0
        if self._blink_started is not None:
            u = (now - self._blink_started) / BLINK_MS
            if u >= 1:
                self._blink_started = None
            else:
                busy = True
                blink = math.sin(math.pi * u)
        look = 0.0
        zz = 0.0
        if self.mood == MOOD_WORKING and not self._travel:
            busy = True
            look = math.sin(now / 1000 * 2 * math.pi * 0.5)
        if self.mood == MOOD_SLEEP and not self._travel:
            busy = True
            zz = (now % 2000) / 2000
        self._pose = Pose(left, right, self.mood, look, blink, hop, expression, zz)
        if not busy:
            self._frame.stop()
        self.update()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self.mood in (MOOD_WORKING, MOOD_SLEEP) and animations_enabled():
            self._frame.start()  # gizliyken duran sürekli hâl (bakınma, uyku) yeniden canlanır

    def paintEvent(self, _event: QPaintEvent) -> None:
        p = QPainter(self)
        paint_mascot(p, QRectF(self.rect()), self._pose, self.palette().windowText().color())
        p.end()
