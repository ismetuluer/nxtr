"""Kaydedilmemiş projeler için kurtarma dosyası.

Yeni bir proje kaydedilene kadar bellekte durur; çökme veya elektrik kesintisinde tarama ve çeviriler
kaybolmasın diye değiştikçe belirli aralıklarla `%LOCALAPPDATA%/NXCeviri/kurtarma` altına bir kopyası
yazılır. Proje kaydedilince, bilerek kapatılınca veya kullanıcı vazgeçince kopya silinir. Açılışta
kalmış bir kopya bulunursa kurtarılması önerilir.

Her pencere kendi dosyasını bir kilit dosyasıyla tutar (`QLockFile`); başka bir açık pencerenin
dosyası "kalmış" sayılmaz. Kilidi tutan süreç çöktüyse kilit bayat sayılır ve dosya önerilir.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile

from nxceviri.core.errors import NxError
from nxceviri.core.project import PROJECT_SUFFIX, Project

log = logging.getLogger(__name__)

_PREFIX = "kurtarma_"


def default_recovery_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NXCeviri" / "kurtarma"


@dataclass(frozen=True)
class RecoveryFile:
    path: Path
    saved_at: datetime
    game_name: str
    rows: int
    translated: int

    def describe(self) -> str:
        name = self.game_name or "Adsız proje"
        when = self.saved_at.strftime("%d.%m.%Y %H:%M")
        return f"{name} — {when} ({self.translated} / {self.rows} satır çevrilmiş)"


def _lock(path: Path) -> QLockFile:
    return QLockFile(str(path.with_name(path.name + ".kilit")))


def _read_info(path: Path) -> RecoveryFile | None:
    """Kurtarma dosyasının özeti; okunamıyorsa None (dosya bozuksa önerilmez)."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            game = conn.execute("SELECT game_name FROM project").fetchone()[0]
            rows, translated = conn.execute(
                "SELECT COUNT(*), COUNT(NULLIF(translation, '')) FROM text_entries"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        log.warning("Kurtarma dosyası okunamadı: %s", path.name)
        return None
    return RecoveryFile(path, datetime.fromtimestamp(path.stat().st_mtime), str(game), int(rows), int(translated))


def leftover_files(folder: Path) -> list[RecoveryFile]:
    """Önceki oturumlardan kalmış (başka bir açık pencerenin kullanmadığı) kurtarma dosyaları, yeniden eskiye."""
    if not folder.is_dir():
        return []
    found = []
    for path in folder.glob(f"{_PREFIX}*{PROJECT_SUFFIX}"):
        lock = _lock(path)
        lock.setStaleLockTime(0)  # yalnızca sahibi ölmüş kilitler bayat sayılır
        if not lock.tryLock(0):
            continue  # başka bir pencere kullanıyor
        lock.unlock()
        info = _read_info(path)
        if info is not None:
            found.append(info)
    return sorted(found, key=lambda f: f.saved_at, reverse=True)


def discard(path: Path) -> None:
    for p in (path, path.with_name(path.name + ".kilit")):
        try:
            p.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Kurtarma dosyası silinemedi: %s (%s)", p.name, exc)


class RecoveryKeeper:
    """Bu pencerenin kurtarma dosyası: `write` kopyayı yeniler, `clear` siler."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.path = folder / f"{_PREFIX}{uuid.uuid4().hex[:12]}{PROJECT_SUFFIX}"
        self._lock: QLockFile | None = None

    def write(self, project: Project) -> bool:
        """Kopyayı yazar; yazılamazsa (disk dolu, izin yok) günlüğe yazıp False döner, iş kesilmez."""
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            if self._lock is None:
                lock = _lock(self.path)
                lock.setStaleLockTime(0)
                if lock.tryLock(0):
                    self._lock = lock
            project.write_copy(self.path)
        except (OSError, NxError) as exc:
            log.warning("Kurtarma kopyası yazılamadı: %s", exc)
            return False
        return True

    def clear(self) -> None:
        if self._lock is not None:
            self._lock.unlock()
            self._lock = None
        discard(self.path)
