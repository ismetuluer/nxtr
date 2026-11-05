"""Kalıcı kullanıcı sözlüğü: "Sözlüğe ekle" ile kabul edilen sözcükler, tüm projeler için geçerli.

Dosya, `%LOCALAPPDATA%/NXCeviri/yazim-sozlugu.txt`: satır başına bir sözcük (küçük harf, UTF-8). Okunamayan dosya boş
sayılır (denetim çalışmaya devam eder); yazma hatası çağırana `OSError` olarak gider.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from pathlib import Path

from nxceviri.core.spell.checker import turkish_lower

log = logging.getLogger(__name__)


def default_user_dictionary_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NXCeviri" / "yazim-sozlugu.txt"


class UserDictionary:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._words = self._read()

    def _read(self) -> set[str]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return set()
        except (OSError, UnicodeDecodeError) as exc:
            log.warning("Yazım sözlüğü okunamadı, boş sayılıyor: %s", exc)
            return set()
        return {turkish_lower(line.strip()) for line in text.splitlines() if line.strip()}

    def words(self) -> frozenset[str]:
        return frozenset(self._words)

    def add(self, words: Iterable[str]) -> int:
        """Sözlüğe ekler; yeni eklenen sözcük sayısını döndürür."""
        new = {turkish_lower(w.strip()) for w in words if w.strip()} - self._words
        if new:
            self._words |= new
            self._write()
        return len(new)

    def remove(self, words: Iterable[str]) -> int:
        gone = {turkish_lower(w.strip()) for w in words} & self._words
        if gone:
            self._words -= gone
            self._write()
        return len(gone)

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text("\n".join(sorted(self._words)) + "\n", encoding="utf-8")
        tmp.replace(self.path)
