"""Yatay logo ve kare simgenin önizleme sayfasını üretir (256/64/32/16 px; açık ve koyu zemin).

    python docs/tasarim/logo/uret.py && python docs/tasarim/logo/onizleme.py

32 px ve üstünde kare logo (nxtr.svg), 16 px'te sadeleştirilmiş simge (nxtr-kucuk.svg) kullanılır.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

DIR = Path(__file__).resolve().parent
ICON_DIR = DIR.parent.parent.parent / "nxceviri" / "gui" / "appicon"
BACKGROUNDS = (("nxtr-logo.svg", "#FFFFFF"), ("nxtr-logo-koyu.svg", "#1E1E1E"))
ICONS = (
    (256, "nxtr.svg"),
    (64, "nxtr.svg"),
    (32, "nxtr.svg"),
    (16, "nxtr-kucuk.svg"),
)
CELL_W = 660
CELL_H = 600


def main() -> int:
    QGuiApplication(sys.argv)
    image = QImage(CELL_W * 2, CELL_H, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for col, (logo_name, bg) in enumerate(BACKGROUNDS):
        left = col * CELL_W
        painter.fillRect(left, 0, CELL_W, CELL_H, QColor(bg))
        logo = QSvgRenderer(str(DIR / logo_name))
        if not logo.isValid():
            return 1
        size = logo.defaultSize()
        logo.render(painter, QRectF(left + 20, 20, size.width(), size.height()))
        x = left + 20
        for px, name in ICONS:
            icon = QSvgRenderer(str(ICON_DIR / name))
            if not icon.isValid():
                return 1
            icon.render(painter, QRectF(x, 330, px, px))
            x += px + 20
    painter.end()
    image.save(str(DIR / "onizleme.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
