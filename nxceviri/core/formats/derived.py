"""Biçim eklentilerinin metinden bağımsız ürettiği dosyalar (yazı tipi yaması, resimler).

Eklenti isteğe bağlı olarak `derived_files(read, files, game_dir) -> Derived` sunar: dışa aktarma bunları moda ekler.
`read(yol)` oyun dosyasını (`arşiv>üye` biçimiyle arşiv üyesini) okur, `files` oyunun RomFS dosya adlarıdır,
`game_dir` kullanıcının oyun dosyalarının klasörüdür (grafik klasörü için; bilinmiyorsa None).
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
