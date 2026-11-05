"""Uygulama simgesi: dosyalar pakette, pencere simgesi kurulu."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

from nxceviri.gui.app import APP_ICON_DIR, app_icon

ROOT = Path(__file__).resolve().parent.parent


def test_ico_has_small_and_large_sizes() -> None:
    with Image.open(APP_ICON_DIR / "nxtr.ico") as ico:
        sizes = ico.info["sizes"]
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes


def test_app_icon_loads(qapp: QApplication) -> None:
    icon = app_icon()
    assert not icon.isNull()
    sizes = {(s.width(), s.height()) for s in icon.availableSizes()}
    assert {(16, 16), (256, 256)} <= sizes


def test_spec_uses_app_icon() -> None:
    spec = (ROOT / "packaging" / "NXTR.spec").read_text(encoding="utf-8")
    assert 'icon="../nxceviri/gui/appicon/nxtr.ico"' in spec
