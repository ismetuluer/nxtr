"""Taşınan oyun dosyalarını yeniden bulma (Qt'siz, yalnızca dosya sistemini okur).

Projede oyun dosyaları mutlak yolla durur; kullanıcı klasörü taşıyınca yollar boşa çıkar. Burada kayıtlı adı ve boyutu
aynı olan dosya verilen klasörlerde aranır. Hiçbir dosyaya yazılmaz; çeviriler ve tarama raporu bu modülün işi değildir.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from pathlib import Path

from nxceviri.core.project.store import SourceRecord


def _subfolders(folder: Path) -> list[Path]:
    try:
        return sorted(p for p in folder.iterdir() if p.is_dir())
    except OSError:
        return []


def _candidates(name: str, folders: Iterable[Path]) -> list[Path]:
    """Her klasörde ve bir alt düzeyinde aynı adlı dosyalar (sıra: verilen klasör sırası, önce klasörün kendisi)."""
    found: list[Path] = []
    seen: set[Path] = set()
    for folder in folders:
        for place in (folder, *_subfolders(folder)):
            path = place / name
            try:
                ok = path.is_file()
                key = path.resolve()
            except OSError:
                continue
            if ok and key not in seen:
                seen.add(key)
                found.append(path)
    return found


def find_moved(sources: Sequence[SourceRecord], folders: Iterable[Path]) -> dict[int, Path]:
    """Bulunamayan her kaynak için yeni yolu döndürür (sıra numarası → yol).

    Ad ve kayıtlı boyut aynı olmalıdır; boyut farklı dosya asla eşleşmez. Kayıtlı boyut bilinmiyorsa (0) yalnızca tek
    aday varsa kabul edilir. Zaten var olan kaynaklara dokunulmaz; başka bir kaynağın yolu da aday sayılmaz."""
    folder_list = [f for f in folders if f.is_dir()]
    taken: set[Path] = set()
    for s in sources:
        try:
            if s.path.is_file():
                taken.add(s.path.resolve())
        except OSError:
            continue
    moved: dict[int, Path] = {}
    for index, source in enumerate(sources):
        if source.path.is_file():
            continue
        found = [p for p in _candidates(source.path.name, folder_list) if p.resolve() not in taken]
        if source.file_size > 0:
            found = [p for p in found if p.stat().st_size == source.file_size]
            chosen = found[0] if found else None
        else:
            chosen = found[0] if len(found) == 1 else None
        if chosen is not None:
            moved[index] = chosen
            taken.add(chosen.resolve())
    return moved


def apply_moved(sources: Sequence[SourceRecord], moved: dict[int, Path]) -> list[SourceRecord]:
    """Yalnızca yolu değişen kayıtlarla yeni liste (diğer alanlar ve sıra korunur)."""
    return [replace(s, path=moved[i]) if i in moved else s for i, s in enumerate(sources)]
