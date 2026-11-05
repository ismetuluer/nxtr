"""Uzun işlemler için ilerleme bildirimi ve iptal desteği.

Çekirdek kod arayüzü bilmez; yalnızca `TaskContext` üzerinden ilerleme bildirir ve
iptal isteğini düzenli aralıklarla kontrol eder.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from nxceviri.core.errors import OperationCancelled

#: (tamamlanan, toplam, açıklama) — toplam bilinmiyorsa 0 verilir.
ProgressCallback = Callable[[int, int, str], None]


class CancelToken:
    """İş parçacıkları arasında paylaşılan iptal bayrağı."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, seconds: float) -> bool:
        """En fazla `seconds` bekler; iptal edilirse hemen döner. İptal edildiyse True."""
        return self._event.wait(seconds)


class TaskContext:
    """Bir işlemin ilerleme geri çağrısı ve iptal bayrağı."""

    def __init__(
        self,
        progress: ProgressCallback | None = None,
        token: CancelToken | None = None,
        publish: Callable[[object], None] | None = None,
    ) -> None:
        self._progress = progress
        self.token = token or CancelToken()
        #: Uzun işlemin ara sonuçlarını (ör. çevrilen bir parti) çağırana iletir. Arayüz bunu
        #: ana iş parçacığına aktarır; böylece sonuçlar iş bitmeden kaydedilebilir.
        self.publish = publish

    def report(self, done: int, total: int, message: str) -> None:
        self.check()
        if self._progress is not None:
            self._progress(done, total, message)

    def check(self) -> None:
        """İptal istenmişse `OperationCancelled` fırlatır."""
        if self.token.cancelled:
            raise OperationCancelled()
