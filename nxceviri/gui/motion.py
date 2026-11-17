"""Animasyon izni: Windows "animasyonları azalt" (istemci alanı animasyonları) ya da Qt efektleri kapalıysa anında."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget

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


#: Kısa açılış animasyonunun süresi (ms): amaçlı ama göze batmayan, 150 ms'nin altında.
FADE_MS = 140


def animations_enabled() -> bool:
    """Kısa arayüz animasyonları çalıştırılabilir mi; testlerde değiştirilebilir.

    Ekransız çalışmada (`offscreen`, testler ve ekran görüntüsü araçları) hiçbir animasyon beklenmez.
    """
    if QGuiApplication.platformName() == "offscreen":
        return False
    if not QApplication.isEffectEnabled(Qt.UIEffect.UI_General):
        return False
    if os.name != "nt":
        return True
    flag = ctypes.c_int(1)
    ok = ctypes.windll.user32.SystemParametersInfoW(_SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(flag), 0)
    return bool(flag.value) if ok else True


def fade_in(widget: QWidget, ms: int = FADE_MS) -> QPropertyAnimation | None:
    """Parçayı `ms` içinde saydamdan opak hâle getirir; animasyon kapalıysa hiçbir şey yapmaz (`None`).

    Efekt bitince kaldırılır (metin düzenleyici gibi yoğun parçalar sonra normal çizilir). Parça henüz
    görünmüyorsa da çağrılabilir: animasyon, parça gösterilince oynar.
    """
    if not animations_enabled():
        return None
    old = widget.graphicsEffect()
    if old is not None:
        widget.setGraphicsEffect(None)  # type: ignore[arg-type]  # PySide6 saplaması None kabul etmez; Qt eder
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", effect)  # efektle birlikte silinir
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    # Efekt, animasyonun `finished` sinyali içinde silinmesin: kaldırma bir sonraki olay turuna bırakılır.
    anim.finished.connect(lambda: QTimer.singleShot(0, widget, lambda: _remove_effect(widget, effect)))
    anim.start()
    return anim


def _remove_effect(widget: QWidget, effect: QGraphicsOpacityEffect) -> None:
    """Efekt hâlâ bizimse kaldırılır (başka bir `fade_in` onu değiştirmişse dokunulmaz)."""
    if widget.graphicsEffect() is effect:
        widget.setGraphicsEffect(None)  # type: ignore[arg-type]  # PySide6 saplaması None kabul etmez; Qt eder
