"""Standart kütüphanenin paketlenecek modül listesi (NXTR.spec kullanır; PyInstaller gerektirmez).

Kullanıcı eklentileri pakette yalnızca düz kaynak dosyasıdır; içe aktaracakları standart kütüphane
modülleri PyInstaller'ın çözümlemesinde görünmez. `sys.stdlib_module_names` yalnızca üst düzey adları verir
(`xml` var, `xml.etree.ElementTree` yok), bu yüzden paketlerin alt modülleri de dosya sisteminden listelenir.

Hiçbir modül İÇE AKTARILMAZ: bazı modüllerin içe aktarılması yan etki doğurur (`antigravity` tarayıcı açar).
"""

from __future__ import annotations

import os
import pkgutil
import sys
from importlib import util

#: Pakete girmeyecek üst düzey modüller (arayüz kütüphanesi, test/örnek kodları, kurulum araçları).
EXCLUDED_TOP_LEVEL = frozenset(
    {
        "test",
        "idlelib",
        "turtledemo",
        "lib2to3",
        "ensurepip",
        "venv",
        "tkinter",
        "turtle",
        "antigravity",
        "this",
        "curses",
    }
)
#: Windows'ta bulunmayan (yalnızca POSIX) alt modüller: listeye girerse PyInstaller "bulunamadı" hatası basar.
POSIX_ONLY = frozenset(
    {
        "asyncio.unix_events",
        "multiprocessing.popen_fork",
        "multiprocessing.popen_forkserver",
        "multiprocessing.popen_spawn_posix",
        "multiprocessing.forkserver",
    }
)
_SKIPPED_PARTS = frozenset({"test", "tests", "__main__"})


def _submodules(directory: str, prefix: str) -> list[str]:
    names: list[str] = []
    for finder, name, is_pkg in pkgutil.iter_modules([directory], prefix):
        short = name.rsplit(".", 1)[-1]
        if short in _SKIPPED_PARTS or name in POSIX_ONLY:
            continue
        names.append(name)
        if is_pkg:
            names.extend(_submodules(os.path.join(str(getattr(finder, "path", directory)), short), name + "."))
    return names


def stdlib_hidden_imports() -> list[str]:
    """Paketlenecek tüm standart kütüphane modül adları (paketlerin alt modülleri dahil), sıralı."""
    found: set[str] = set()
    for name in sys.stdlib_module_names:
        if name.startswith("_") or name in EXCLUDED_TOP_LEVEL:
            continue
        spec = util.find_spec(name)  # üst düzey adı bulur, çalıştırmaz
        if spec is None:
            continue
        found.add(name)
        for location in spec.submodule_search_locations or ():
            found.update(_submodules(location, name + "."))
    return sorted(found)
