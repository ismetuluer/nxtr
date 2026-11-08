"""Animasyon izni: Windows "animasyonları azalt" (istemci alanı animasyonları) ya da Qt efektleri kapalıysa anında."""

from __future__ import annotations

import ctypes
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

#: `SystemParametersInfo` seçeneği: pencere içi animasyonlar açık mı (Ayarlar > Erişilebilirlik > Görsel efektler).
_SPI_GETCLIENTAREAANIMATION = 0x1042


def animations_enabled() -> bool:
    """Kısa arayüz animasyonları çalıştırılabilir mi; testlerde değiştirilebilir."""
    if not QApplication.isEffectEnabled(Qt.UIEffect.UI_General):
        return False
    if os.name != "nt":
        return True
    flag = ctypes.c_int(1)
    ok = ctypes.windll.user32.SystemParametersInfoW(_SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(flag), 0)
    return bool(flag.value) if ok else True
