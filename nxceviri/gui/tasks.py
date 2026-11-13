"""Uzun işlemleri arka plan iş parçacığında çalıştırma (ilerleme + iptal)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from nxceviri.core.errors import NxError, OperationCancelled
from nxceviri.core.progress import TaskContext

log = logging.getLogger(__name__)

#: İlerleme sinyalleri en fazla bu sıklıkta gönderilir (arayüzü boğmamak için).
_PROGRESS_INTERVAL_S = 0.05


def release_thread(thread: QThread) -> None:
    """Biten iş parçacığını güvenle bırakır: `finished` yayıldığında iş parçacığı henüz tamamen durmamış olabilir;
    önce durması beklenir (anlık), sonra C++ nesnesi olay döngüsünde silinir. Beklemeden bırakılan nesne çöp
    toplayıcıda yok edilirse Qt "çalışırken yok edildi" diye uygulamayı sonlandırır."""
    thread.wait()
    thread.deleteLater()


class Task(QThread):
    """`fn(ctx)`'i ayrı iş parçacığında çalıştırır; sonuçları sinyallerle bildirir."""

    progress = Signal(int, int, str)
    #: Ara sonuç (ör. çevrilmiş bir parti); ana iş parçacığında işlenir.
    partial = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: Callable[[TaskContext], object], description: str) -> None:
        super().__init__()
        self._fn = fn
        self.description = description
        self._last_emit = 0.0
        self.ctx = TaskContext(self._on_progress, publish=self.partial.emit)

    def _on_progress(self, done: int, total: int, message: str) -> None:
        now = time.monotonic()
        if now - self._last_emit >= _PROGRESS_INTERVAL_S or (total and done >= total):
            self._last_emit = now
            self.progress.emit(done, total, message)

    def cancel(self) -> None:
        self.ctx.token.cancel()

    def run(self) -> None:
        try:
            result = self._fn(self.ctx)
        except OperationCancelled:
            log.info("İşlem iptal edildi: %s", self.description)
            self.cancelled.emit()
        except NxError as exc:
            log.warning("İşlem başarısız (%s): %s", self.description, exc.message)
            self.failed.emit(exc.user_text())
        except Exception:
            # Beklenmeyen hata: ayrıntı log dosyasına yazılır, kullanıcıya anlaşılır mesaj gösterilir.
            log.exception("Beklenmeyen hata: %s", self.description)
            self.failed.emit(
                "Beklenmeyen bir hata oluştu.\n\n"
                "Ayrıntılar hata kaydı dosyasına yazıldı (Yardım → Hata Kayıtları Klasörünü Aç). "
                "Sorun sürerse bu dosyayı geliştiriciyle paylaşabilirsiniz; anahtar bilgisi içermez."
            )
        else:
            self.succeeded.emit(result)
