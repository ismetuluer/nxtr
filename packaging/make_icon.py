"""Uygulama simgesini SVG kaynaklarından üretir: Windows .ico (16–256 piksel) ve pencere için .png.

    python packaging/make_icon.py

Simge tasarımı değişince bir kez çalıştırılır; çıktılar depoya eklenir. 24 px ve altında "NX" harfleri
okunmadığından sadeleştirilmiş nxtr-kucuk.svg, daha büyük boyutlarda nxtr.svg kullanılır.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "nxceviri" / "gui" / "appicon"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SMALL_MAX = 24  # bu boyuta kadar (dahil) sadeleştirilmiş simge


def render(renderer: QSvgRenderer, size: int) -> Image.Image:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(data.data()))).convert("RGBA")


def main() -> int:
    QGuiApplication(sys.argv)
    full = QSvgRenderer(str(ICON_DIR / "nxtr.svg"))
    small = QSvgRenderer(str(ICON_DIR / "nxtr-kucuk.svg"))
    if not (full.isValid() and small.isValid()):
        print("SVG okunamadı", file=sys.stderr)
        return 1
    images = [render(small if size <= SMALL_MAX else full, size) for size in SIZES]
    images[-1].save(ICON_DIR / "nxtr.png")
    images[-1].save(ICON_DIR / "nxtr.ico", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(f"Yazıldı: {ICON_DIR / 'nxtr.ico'}, {ICON_DIR / 'nxtr.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
