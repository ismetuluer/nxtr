"""Animasyon izni: Windows "animasyonları azalt" (istemci alanı animasyonları) ya da Qt efektleri kapalıysa anında."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

#: `SystemParametersInfo` seçeneği: pencere içi animasyonlar açık mı (Ayarlar > Erişilebilirlik > Görsel efektler).
_SPI_GETCLIENTAREAANIMATION = 0x1042


class _LastInputInfo(ctypes.Structure):
    _fields_ = (("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD))


def idle_seconds() -> float:
    """Kullanıcının (herhangi bir uygulamada) tuşa ya da fareye en son dokunmasından beri geçen saniye.

    Windows dışında ya da okunamazsa 0 (hep etkin sayılır). Uygulama içi olay süzgeci yerine bu kullanılır: her Qt
    olayında Python'a girmek hem yavaştı hem de PySide6'da çökmelere yol açıyordu.
    """
    if os.name != "nt":
        return 0.0
    info = _LastInputInfo(ctypes.sizeof(_LastInputInfo), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return float((now - info.dwTime) & 0xFFFFFFFF) / 1000.0


def animations_enabled() -> bool:
    """Kısa arayüz animasyonları çalıştırılabilir mi; testlerde değiştirilebilir."""
    if not QApplication.isEffectEnabled(Qt.UIEffect.UI_General):
        return False
    if os.name != "nt":
        return True
    flag = ctypes.c_int(1)
    ok = ctypes.windll.user32.SystemParametersInfoW(_SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(flag), 0)
    return bool(flag.value) if ok else True
