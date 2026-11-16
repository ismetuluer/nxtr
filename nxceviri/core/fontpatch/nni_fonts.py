"""Ys Origin'in Latin yazı tiplerine eksik Türkçe harfleri ekleme (`ğ Ğ ş Ş ı İ`).

Oyunun metinleri `extension/font/` altındaki BMFont çiftleriyle (`*.fnt` + `*.png`) çizilir. Latin metin için kullanılan
beş yazı tipi `ç ö ü` içerir, bu altı harfi içermez: `arial` (diyalog ve menü açıklamaları), `ysfont`, `linuxwhite`,
`linuxshadow`, `linuxwhitesmall` (Linux Libertine; adlar, sayılar, altyazı). Harfler yazı tipinin kendi glifleriyle
türetilir (`fontpatch/bmfont.py`). `arialuni_*` (ç ö ü bile yok), `jejugothic_*`, `msgothic` (altı harf de var),
`yso_pro_*.fnt` (Korece/Çince altyazı) yamalanmaz.

Çıktı, değişen `.fnt` ve `.png` dosyalarıdır (RomFS yolları aynı kalır); mod klasörüne serbest dosya olarak konur.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Collection

from PIL import Image

from nxceviri.core.fontpatch.bmfont import BmFont, BmFontError, add_missing

FONT_DIR = "ys_data/data/extension/font/"
FONTS = ("arial", "ysfont", "linuxwhite", "linuxshadow", "linuxwhitesmall")
LETTERS = "ğĞşŞıİ"


def _find(files: Collection[str], wanted: str) -> str | None:
    return next((f for f in files if f.lower() == wanted), None)


def patch_fonts(read: Callable[[str], bytes], files: Collection[str]) -> tuple[dict[str, bytes], list[str], list[str]]:
    """(yeni dosyalar {RomFS yolu → bayt}, eklenen harfleri anlatan satırlar, uyarılar)."""
    out: dict[str, bytes] = {}
    notes: list[str] = []
    warnings: list[str] = []
    for name in FONTS:
        fnt_path = _find(files, f"{FONT_DIR}{name}.fnt")
        png_path = _find(files, f"{FONT_DIR}{name}.png")
        if fnt_path is None or png_path is None:
            warnings.append(f"Yazı tipi {name} oyunda bulunamadı; Türkçe harfler eklenmedi.")
            continue
        try:
            font = BmFont(read(fnt_path), Image.open(io.BytesIO(read(png_path))))
            before = font.scale_h
            added = add_missing(font, LETTERS)
        except (BmFontError, OSError) as exc:
            warnings.append(f"Yazı tipi {name} yamalanamadı: {getattr(exc, 'message', exc)}")
            continue
        if not added:
            continue
        out[fnt_path] = font.serialize()
        out[png_path] = font.atlas_png()
        grown = f" (atlas {font.scale_w}×{before} → {font.scale_w}×{font.scale_h})" if font.scale_h != before else ""
        notes.append(f"{name}: {' '.join(added)}{grown}")
    return out, notes, warnings
