"""Ys Origin'in metinden bağımsız ek dosyaları: Türkçe harfli yazı tipleri ve kullanıcının çevirdiği resimler.

`YsOriginPlugin` ve `SrtPlugin` (giriş altyazısı) aynı kancayı kullanır; dışa aktarma aynı oyun için bir kez çağırır.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from pathlib import Path

from nxceviri.core.fontpatch import ys_fonts, ys_graphics
from nxceviri.core.formats.derived import Derived


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
