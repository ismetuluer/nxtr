"""Python'un döngü çöp toplayıcısını ana olay döngüsünden, güvenli bir noktada çalıştırır.

Otomatik toplama, bellek ayrılan herhangi bir satırda (Qt'nin çağırdığı bir Python işlevinin ortasında ya da bir iş
parçacığında) tetiklenir. Toplanan döngülerde Qt nesnelerinin Python sarmalayıcıları varsa bunların C++ tarafı o
anda yok edilir; Qt bu sırada tutarsız durumdaysa uygulama sert çöker (0.55.x: çeviri başlarken "Garbage-collecting"
sırasında abort / erişim ihlali). Bu yüzden otomatik toplama kapatılır ve aynı eşiklerle, ana iş parçacığında, olay
döngüsünün en üstünden (zamanlayıcıyla) yapılır. Yaklaşım pyqtgraph'ın `GarbageCollector`ıyla aynıdır.
"""

from __future__ import annotations

import gc
import logging

from PySide6.QtCore import QObject, QTimer

log = logging.getLogger(__name__)

#: Kuşak sayaçlarına bakma aralığı (ms); sayaç eşiği aşmadıysa hiçbir şey yapılmaz (ucuz).
INTERVAL_MS = 500


class GarbageCollector(QObject):
    def __init__(self, parent: QObject | None = None, interval_ms: int = INTERVAL_MS) -> None:
        super().__init__(parent)
        self._was_enabled = gc.isenabled()
        self.collected = 0
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.check)
        gc.disable()
        self._timer.start()

    @property
    def active(self) -> bool:
        return self._timer.isActive()

    def check(self) -> None:
        """Kuşak sayaçları eşiği aştıysa yalnızca o kuşağı toplar (otomatik toplayıcının kuralıyla aynı)."""
        low, mid, high = gc.get_count()
        t0, t1, t2 = gc.get_threshold()
        if low > t0:
            generation = 2 if high > t2 else 1 if mid > t1 else 0
            self.collected += gc.collect(generation)

    def stop(self) -> None:
        """Denetimi bırakır; otomatik toplayıcı eskisi gibiyse yeniden açılır."""
        self._timer.stop()
        if self._was_enabled:
            gc.enable()
