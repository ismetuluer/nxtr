"""Rastgele erişimli, salt okunur veri kaynakları.

Konteyner katmanının tamamı bu soyutlama üzerine kuruludur: bir NSP dosyası,
içindeki bir NCA, NCA'nın çözülmüş bir bölümü veya RomFS içindeki bir dosya hep
bir `Storage`'dır. Kullanıcının dosyaları yalnızca `"rb"` kipinde açılır.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType

from nxceviri.core.errors import ContainerError

_TRUNCATED_HINT = "Dosya eksik indirilmiş veya bozulmuş olabilir. Dosyayı kendi konsolunuzdan yeniden çıkarın."


class Storage(ABC):
    """Boyutu bilinen, ofsetle okunabilen veri."""

    @property
    @abstractmethod
    def size(self) -> int: ...

    @abstractmethod
    def _read(self, offset: int, size: int) -> bytes:
        """Sınır denetimi yapılmış okuma; tam olarak `size` bayt döndürmelidir."""

    def read(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > self.size:
            raise ContainerError(
                f"Dosya yapısı tutarsız: {offset:#x} ofsetinden {size:#x} bayt okunmak istendi "
                f"ama veri {self.size:#x} bayt.",
                _TRUNCATED_HINT,
            )
        if size == 0:
            return b""
        data = self._read(offset, size)
        if len(data) != size:
            raise ContainerError("Dosya beklenenden kısa.", _TRUNCATED_HINT)
        return data

    def read_all(self) -> bytes:
        return self.read(0, self.size)

    def iter_chunks(self, chunk_size: int = 4 * 1024 * 1024) -> Iterator[bytes]:
        offset = 0
        while offset < self.size:
            n = min(chunk_size, self.size - offset)
            yield self.read(offset, n)
            offset += n


class MemoryStorage(Storage):
    def __init__(self, data: bytes) -> None:
        self._data = data

    @property
    def size(self) -> int:
        return len(self._data)

    def _read(self, offset: int, size: int) -> bytes:
        return self._data[offset : offset + size]


class FileStorage(Storage):
    """Diskteki bir dosya; yalnızca okuma kipinde açılır ve iş parçacığı güvenlidir."""

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            self._fh = open(path, "rb")  # noqa: SIM115 - ömrü close() ile yönetiliyor
        except OSError as exc:
            raise ContainerError(
                f"Dosya açılamadı: {path}",
                f"Dosyanın var olduğundan ve başka bir programda açık olmadığından emin olun. ({exc.strerror})",
            ) from None
        self._size = path.stat().st_size
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return self._size

    def _read(self, offset: int, size: int) -> bytes:
        with self._lock:
            self._fh.seek(offset)
            return self._fh.read(size)

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> FileStorage:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class SubStorage(Storage):
    """Başka bir kaynağın bir dilimi."""

    def __init__(self, base: Storage, offset: int, size: int) -> None:
        if offset < 0 or size < 0 or offset + size > base.size:
            raise ContainerError(
                f"Dosya yapısı tutarsız: alt bölüm ({offset:#x}+{size:#x}) kapsayıcının dışına taşıyor.",
                _TRUNCATED_HINT,
            )
        self._base = base
        self._offset = offset
        self._size = size

    @property
    def size(self) -> int:
        return self._size

    def _read(self, offset: int, size: int) -> bytes:
        return self._base.read(self._offset + offset, size)
