"""Süre testleri için ortak ölçüm yardımcısı: tek ölçüme değil, en iyi ölçüme bakar.

Yük gürültüsü her tekrarı birden yavaşlatmaz; gerçek bir gerileme ise hepsini yavaşlatır. Bu yüzden eşik, birkaç
denemenin en küçüğüne uygulanır. Eşiğin altına inen ilk denemede durulur, yani makine boştayken ek süre harcanmaz."""

from __future__ import annotations

import time
from collections.abc import Callable


def best_time(prepare: Callable[[], Callable[[], object]], *, under: float | None = None, attempts: int = 3) -> float:
    """`prepare()` her denemede taze kurulum yapıp ölçülecek işi döndürür; yalnızca o iş süre alınır.

    Dönen değer denemelerin en küçüğüdür. `under` verilmişse, bir deneme bu eşiğin altına inince diğerleri koşulmaz."""
    best = float("inf")
    for _ in range(attempts):
        action = prepare()
        start = time.perf_counter()
        action()
        best = min(best, time.perf_counter() - start)
        if under is not None and best < under:
            break
    return best
