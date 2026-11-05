"""Biçim eklentilerinin metinden bağımsız ürettiği dosyalar ve arşiv üyeleri (Ys Origin: yazı tipleri, resimler).

Eklenti `derived_files(read, files, game_dir) -> Derived` sunarsa (`formats/derived.py`) dışa aktarma, o oyunun
dosyalarını okuyup sonucu moda ekler. Aynı kancayı kullanan birden çok eklenti (Ys metni ve altyazısı) oyun başına
bir kez çalıştırılır.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from nxceviri.core.archives import nested
from nxceviri.core.archives.access import MemberReader
from nxceviri.core.container.view import ContentTree
from nxceviri.core.errors import NxError
from nxceviri.core.formats.derived import Derived
from nxceviri.core.formats.registry import plugin_for_kind


def collect(
    formats: Iterable[tuple[str, str]], trees: Mapping[str, ContentTree], game_dir: Path | None
) -> dict[str, Derived]:
    """TitleID → o oyun için eklentilerin ürettikleri; `formats`, dışa aktarılan (TitleID, tür) çiftleridir."""
    out: dict[str, Derived] = {}
    done: set[tuple[str, object]] = set()
    for title_id, kind in sorted(set(formats)):
        provider = getattr(plugin_for_kind(kind, title_id), "derived_files", None)
        tree = trees.get(title_id)
        if provider is None or tree is None or (title_id, provider) in done:
            continue
        done.add((title_id, provider))
        reader = MemberReader(tree.view, tree.code)

        def read(path: str, _tree: ContentTree = tree, _reader: MemberReader = reader) -> bytes:
            if ">" in path:
                return _reader.read(path)
            return _tree.view.open(path).read_all()

        try:
            derived = provider(read, tree.view.files, game_dir)
        except NxError as exc:
            out.setdefault(title_id, Derived()).warnings.append(f"Ek dosyalar üretilemedi: {exc.message}")
            continue
        out.setdefault(title_id, Derived()).merge(derived)
    return out


def split_members(derived: Derived) -> dict[str, dict[str, bytes]]:
    """Arşiv üyelerini arşive göre gruplar: {üst dosya → {üye → bayt}}."""
    grouped: dict[str, dict[str, bytes]] = {}
    for path, data in derived.members.items():
        parts = nested.split(path)
        grouped.setdefault(parts[0], {})[parts[1]] = data
    return grouped
