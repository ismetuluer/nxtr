"""Biçim eklentilerinin metinden bağımsız ürettiği dosyalar (yazı tipi yaması, resimler).

Eklenti isteğe bağlı olarak `derived_files(read, files, game_dir) -> Derived` sunar: dışa aktarma bunları moda ekler.
`read(yol)` oyun dosyasını (`arşiv>üye` biçimiyle arşiv üyesini) okur, `files` oyunun RomFS dosya adlarıdır,
`game_dir` kullanıcının oyun dosyalarının klasörüdür (grafik klasörü için; bilinmiyorsa None).
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Derived:
    files: dict[str, bytes] = field(default_factory=dict)  # RomFS yolu → yeni dosya (mod klasörüne serbest dosya)
    members: dict[str, bytes] = field(default_factory=dict)  # "arşiv>üye" → yeni içerik (arşiv yeniden kurulur)
    font_notes: list[str] = field(default_factory=list)  # "ad: eklenen harfler" satırları
    notes: list[str] = field(default_factory=list)  # bilgi dosyasına yazılan diğer satırlar
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: Derived) -> None:
        self.files.update(other.files)
        self.members.update(other.members)
        self.font_notes += [n for n in other.font_notes if n not in self.font_notes]
        self.notes += [n for n in other.notes if n not in self.notes]
        self.warnings += [w for w in other.warnings if w not in self.warnings]


#: Resim çevirisinde sayılan dosya türleri.
_IMAGE_SUFFIXES = (".png", ".dds")


@dataclass(frozen=True)
class GraphicsSupport:
    """Resim çevirisi desteği (Dışa Aktar → Görseller). Eklenti `graphics = GraphicsSupport(...)` sunar.

    Klasör düzeni: `<oyun dosyalarının klasörü>/<folder_name>/orijinal/` (uygulama çıkarır) ve `temiz/` (kullanıcı aynı
    adla Türkçe resmini koyar). `export(okuyucu, RomFS dosyaları, klasör)` özgünleri `orijinal/`e yazar ve adlarını
    döndürür; okuyucu `archives.access.MemberReader`dır. Hazır resimler dışa aktarmada `derived_files` ile moda girer.
    """

    folder_name: str
    export: Callable[[Any, Collection[str], Path], list[str]]


def graphics_status(folder: Path) -> tuple[int, int]:
    """(özgün resim sayısı, hazırlanmış Türkçe resim sayısı)."""

    def count(sub: str) -> int:
        target = folder / sub
        if not target.is_dir():
            return 0
        return sum(1 for f in target.iterdir() if f.suffix.lower() in _IMAGE_SUFFIXES)

    return count("orijinal"), count("temiz")
