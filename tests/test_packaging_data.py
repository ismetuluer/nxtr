"""Paket verisi: `pip install .` yalnızca pyproject'te bildirilen veri dosyalarını kurar; sürüm paketi (PyInstaller)
bunu kurarak derlenir. Bildirilmeyen bir klasör kaynak koddan çalışırken bulunur ama .exe'de yoktur (0.55.0'da
Yardım konuları böyle kayboldu)."""

from __future__ import annotations

import tomllib
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "nxceviri"
#: Kaynakta durup pakete girmesi gerekmeyen dosyalar.
_IGNORED_SUFFIXES = {".py", ".pyc"}


def _declared() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data["tool"]["setuptools"]["package-data"]["nxceviri"])


def test_every_data_file_is_declared_as_package_data() -> None:
    patterns = _declared()
    missing = []
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or path.suffix in _IGNORED_SUFFIXES or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(PACKAGE).as_posix()
        if not any(fnmatch(rel, pattern) for pattern in patterns):
            missing.append(rel)
    assert not missing, f"pyproject.toml package-data'da bildirilmemiş veri dosyaları: {missing[:5]}"
