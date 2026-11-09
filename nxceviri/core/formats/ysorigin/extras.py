"""Ys Origin'in metinden bağımsız ek dosyaları: Türkçe harfli yazı tipleri ve kullanıcının çevirdiği resimler.

`YsOriginPlugin` ve `SrtPlugin` (giriş altyazısı) aynı kancayı kullanır; dışa aktarma aynı oyun için bir kez çağırır.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any

from nxceviri.core.fontpatch import ys_fonts, ys_graphics
from nxceviri.core.formats.derived import Derived, GraphicsSupport


def derived_files(read: Callable[[str], bytes], files: Collection[str], game_dir: Path | None) -> Derived:
    out = Derived()
    fonts, font_notes, warnings = ys_fonts.patch_fonts(read, files)
    out.files.update(fonts)
    out.font_notes += font_notes
    out.warnings += warnings
    folder = ys_graphics.folder_for(game_dir)
    if folder is not None:
        images, notes, problems = ys_graphics.replacements(read, files, folder)
        for path, data in images.items():
            if ">" in path:
                out.members[path] = data
            else:
                out.files[path] = data
        if notes:
            out.notes.append(f"Grafik çevirisi ({len(notes)} resim): {', '.join(notes)}")
        out.warnings += problems
    return out


def export_graphics(reader: Any, files: Collection[str], folder: Path) -> list[str]:
    """Dışa Aktar → Görseller: çevrilebilir resimlerin özgünlerini `orijinal/`e PNG olarak yazar."""
    archive = reader.nni(ys_graphics.ARCHIVE)
    present = [path for path in ys_graphics.LOOSE.values() if path in files]
    return ys_graphics.export_originals(reader.read, list(archive.entries), folder, present)


GRAPHICS = GraphicsSupport(ys_graphics.FOLDER, export_graphics)
