"""Sağlayıcı durumunu arka planda, seyrek ve önbellekli sorgular (durum çubuğu ipucu için).

Sorgu yalnızca ipucu açılırken yapılır ve aynı sağlayıcı için en çok `TTL_S` saniyede bir yenilenir; arayüzü
dondurmaz (ayrı iş parçacığı, kısa zaman aşımı çağıranın verdiği istemcidedir).
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx
from PySide6.QtCore import QObject, Signal

from nxceviri.gui.tasks import Task

#: Aynı sağlayıcı için iki sorgu arasındaki en kısa süre (saniye).
TTL_S = 30.0
#: Sorgu başarısız olursa ipucunda görünen tek satır.
FAILED_LINE = "Durum alınamadı."

Fetch = Callable[[httpx.Client], list[str]]


class ProviderProbe(QObject):
    """`request(anahtar, getir)`: önbellek tazeyse hemen, değilse arka planda sorgulayıp `fetched` yayar."""

    #: Güncel sorgunun ipucu satırları (ana iş parçacığında).
    fetched = Signal(list)

    def __init__(
        self,
        parent: QObject,
        client_factory: Callable[[], httpx.Client],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(parent)
        self._client_factory = client_factory
        self._clock = clock
        self._cache: tuple[object, float, list[str]] | None = None
        self._wanted: object = None
        self._task: Task | None = None

    def lines_for(self, key: object) -> list[str] | None:
        """Bu anahtar için son bilinen satırlar (eskimiş olabilir); yoksa None."""
        return self._cache[2] if self._cache is not None and self._cache[0] == key else None

    def request(self, key: object, fetch: Fetch) -> None:
        self._wanted = key
        if self._cache is not None and self._cache[0] == key and self._clock() - self._cache[1] < TTL_S:
            self.fetched.emit(self._cache[2])
            return
        if self._task is not None:
            return

        def work(_ctx: object) -> list[str]:
            client = self._client_factory()
            try:
                return fetch(client)
            finally:
                client.close()

        task = Task(work, "Sağlayıcı durumu")
        task.succeeded.connect(lambda lines: self._done(key, list(lines)))
        task.failed.connect(lambda _message: self._done(key, [FAILED_LINE]))
        task.finished.connect(self._release)
        self._task = task
        task.start()

    def _done(self, key: object, lines: list[str]) -> None:
        self._cache = (key, self._clock(), lines)
        if key == self._wanted:
            self.fetched.emit(lines)

    def _release(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.deleteLater()

    def close(self) -> None:
        """Pencere kapanırken süren sorgunun bitmesini bekler (zaman aşımı kısa olduğundan en çok birkaç saniye)."""
        if self._task is not None:
            self._task.wait(5000)
