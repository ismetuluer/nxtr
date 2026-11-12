"""Yay (spring) animasyonu: designbookmark.com/motion paylaşılan çözücüsünün (`shared/motion.js`) birebir taşınması.

Çözücü yarı örtük Euler'dir, kütle 1: `a = -k·(x - hedef) - c·v; v += a·dt; x += v·dt`. Kare başına en çok 1/30 s
ilerlenir ve bu süre 4 alt adıma bölünür (sitedeki `sub = 4`). Yay değerleri `tokens.css`ten, "sertlik sönüm" biçiminde.
Süre yoktur: hareket yay dengeye gelince biter; az sönümlü yaylar hedefi hafif aşıp döner (yay hissi bundan gelir).

`animations_enabled()` kapalıysa (Windows "animasyonları azalt") çağıran animasyonu hiç başlatmaz, değer anında atlar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QElapsedTimer, QObject, QTimer

#: tokens.css `--spring-soft`: paneller ve bütün bileşen hareketleri (kenar çubuğu genişliği).
SPRING_SOFT = (260.0, 24.0)
#: tokens.css `--spring-fade`: solma, saydamlık.
SPRING_FADE = (420.0, 32.0)

#: Bir kareden en çok ilerlenen süre (s) ve alt adım sayısı (motion.js: `Math.min(dt, 1/30)`, `sub = 4`).
MAX_DT = 1 / 30
SUBSTEPS = 4
#: Denge sayılan konum farkı ve hız (birim/s); altına inince hedefe oturur ve animasyon biter.
_REST_DISTANCE = 0.4
_REST_SPEED = 8.0
_FRAME_MS = 16


@dataclass
class Spring:
    x: float
    v: float
    target: float
    k: float
    c: float

    def step(self, dt: float) -> None:
        a = -self.k * (self.x - self.target) - self.c * self.v
        self.v += a * dt
        self.x += self.v * dt

    @property
    def at_rest(self) -> bool:
        return abs(self.x - self.target) < _REST_DISTANCE and abs(self.v) < _REST_SPEED


def integrate(spring: Spring, dt: float) -> None:
    """Bir kare ilerletir: süre 1/30 s'ye kırpılır, 4 alt adıma bölünür."""
    dt = min(dt, MAX_DT)
    for _ in range(SUBSTEPS):
        spring.step(dt / SUBSTEPS)


class SpringAnimator(QObject):
    """Bir değeri yayla hedefe götürür: her karede `on_value(değer)`, dengeye gelince tam hedefle son bir kez
    `on_value` ve `on_done`. `stop()` sessizdir (`on_done` çağrılmaz)."""

    def __init__(
        self,
        parent: QObject | None,
        start: float,
        target: float,
        stiffness: float,
        damping: float,
        *,
        on_value: Callable[[float], None],
        on_done: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.spring = Spring(start, 0.0, target, stiffness, damping)
        self._on_value = on_value
        self._on_done = on_done
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._frame)

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        self._clock.start()
        self._timer.start()

    def retarget(self, target: float) -> None:
        """Hedefi değiştirir; hız korunur, hareket sıçramadan yön değiştirir."""
        self.spring.target = target

    def stop(self) -> None:
        self._timer.stop()

    def _frame(self) -> None:
        dt = self._clock.restart() / 1000.0
        integrate(self.spring, dt)
        if self.spring.at_rest:
            self._timer.stop()
            self.spring.x = self.spring.target
            self.spring.v = 0.0
            self._on_value(self.spring.x)
            self._on_done()
            return
        self._on_value(self.spring.x)
