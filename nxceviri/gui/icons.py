"""Simge sistemi: Lucide SVG dosyalarından, temaya uyan ve yüksek DPI'da keskin `QIcon` üretir.

Simgeler `icons/<ad>.svg` dosyalarıdır (Lucide, ISC lisansı; sürüm ve kaynak `icons/README.md`'de).
SVG'lerdeki `currentColor` istenen renkle değiştirilip `QtSvg` ile çizilir; yeni bir bağımlılık yoktur.
Uygulama çalışırken hiçbir şey indirilmez.

- `icon(ad)`: normal hâl temanın metin rengiyle, devre dışı hâl soluk renkle çizilir.
- `bind_icon(hedef, ad)`: düğme/eylemin simgesini kurar ve kaydeder; tema değişince `refresh_icons()` yeniler.
- Eksik veya bozuk dosya uygulamayı durdurmaz: boş simge döner ve uyarı günlüğe yazılır
  (düğmenin metni zaten vardır).
"""

from __future__ import annotations

import logging
import weakref
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QLabel

from nxceviri.gui.theme import current_tokens

log = logging.getLogger(__name__)

ICON_DIR = Path(__file__).parent / "icons"
#: Dizindeki simge adları (dosya adı, uzantısız).
KNOWN_ICONS: frozenset[str] = frozenset(p.stem for p in ICON_DIR.glob("*.svg"))

DEFAULT_SIZE = 18

_cache: dict[tuple[str, str, int, float], QPixmap] = {}
_Target = QAbstractButton | QAction | QLabel
_bound: weakref.WeakKeyDictionary[_Target, tuple[str, int]] = weakref.WeakKeyDictionary()


def clear_cache() -> None:
    _cache.clear()


def _device_ratio() -> float:
    screen = QGuiApplication.primaryScreen()
    return float(screen.devicePixelRatio()) if screen is not None else 1.0


def _render(name: str, color: str, size: int, dpr: float) -> QPixmap:
    path = ICON_DIR / f"{name}.svg"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("Simge okunamadı (%s): %s", name, exc)
        return QPixmap()
    renderer = QSvgRenderer(QByteArray(text.replace("currentColor", color).encode("utf-8")))
    if not renderer.isValid():
        log.warning("Simge dosyası bozuk (%s)", name)
        return QPixmap()
    side = max(1, round(size * dpr))
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, side, side))
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def pixmap(name: str, color: str, size: int = DEFAULT_SIZE, dpr: float = 1.0) -> QPixmap:
    """Verilen renk, boyut ve DPR için önbellekli piksel haritası (hata varsa boş)."""
    key = (name, color, size, dpr)
    if key not in _cache:
        _cache[key] = _render(name, color, size, dpr)
    return _cache[key]


def icon(name: str, color: str | None = None, size: int = DEFAULT_SIZE) -> QIcon:
    tokens = current_tokens()
    dpr = _device_ratio()
    normal = pixmap(name, color or tokens["text"], size, dpr)
    if normal.isNull():
        return QIcon()
    result = QIcon()
    result.addPixmap(normal, QIcon.Mode.Normal)
    result.addPixmap(pixmap(name, tokens["muted"], size, dpr), QIcon.Mode.Disabled)
    return result


def _apply(target: _Target, name: str, size: int) -> None:
    result = icon(name, size=size)
    if isinstance(target, QLabel):
        target.setPixmap(result.pixmap(size, size))
    else:
        target.setIcon(result)


def bind_icon(target: _Target, name: str, size: int = DEFAULT_SIZE) -> None:
    """Hedefin (düğme, eylem ya da etiket) simgesini kurar ve tema değişince yenilenmek üzere kaydeder."""
    _bound[target] = (name, size)
    _apply(target, name, size)


def refresh_icons() -> None:
    """Kayıtlı hedeflerin simgesini geçerli tema renkleriyle yeniden üretir."""
    for target, (name, size) in list(_bound.items()):
        try:
            _apply(target, name, size)
        except RuntimeError:
            # Python sarmalayıcısı yaşıyor ama Qt nesnesi silinmiş: kaydı at.
            _bound.pop(target, None)
