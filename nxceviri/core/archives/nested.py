"""İç içe arşiv yolları: "dış.sarc.zs>dış.sarc>Msg/a.msbt" gibi yolları açma ve geri kapama.

Yol parçaları tarayıcının (`formats.scanner`) ürettiği biçimdedir: ilk parça RomFS
yoludur; sonraki her parça, bir önceki verinin içindeki dosyadır. Sıkıştırılmış tek
dosyalarda (Yaz0, ZSTD) parça yalnızca okunabilirlik içindir; veri doğrudan açılır.
"""

from __future__ import annotations

from collections.abc import Callable

from nxceviri.core.archives import sarc, yaz0, zstd
from nxceviri.core.errors import ArchiveError

SEPARATOR = ">"
MAX_OUTPUT = 256 * 1024 * 1024


def split(path: str) -> list[str]:
    return path.split(SEPARATOR)


def _kind(data: bytes) -> str:
    if data.startswith(sarc.MAGIC):
        return "sarc"
    if data.startswith(yaz0.MAGIC):
        return "yaz0"
    if data.startswith(zstd.MAGIC):
        return "zstd"
    return ""


def open_inner(data: bytes, parts: list[str]) -> bytes:
    """`data` (en dıştaki dosyanın içeriği) içinden `parts` yolundaki iç dosyayı döndürür."""
    for part in parts:
        kind = _kind(data)
        if kind == "sarc":
            data = sarc.read(data).get(part)
        elif kind == "yaz0":
            data = yaz0.decompress(data, MAX_OUTPUT)
        elif kind == "zstd":
            data = zstd.decompress(data, MAX_OUTPUT)
        else:
            raise ArchiveError(f"'{part}' açılamadı: üstteki dosya bir arşiv değil.")
    return data


def replace_inner(data: bytes, parts: list[str], transform: Callable[[bytes], bytes]) -> bytes:
    """İç dosyayı `transform` ile değiştirir ve tüm üst arşivleri yeniden kapatır."""
    if not parts:
        return transform(data)
    kind = _kind(data)
    head, rest = parts[0], parts[1:]
    if kind == "sarc":
        arc = sarc.read(data)
        old = arc.get(head)
        new = replace_inner(old, rest, transform)
        if new == old:
            return data
        arc.replace(head, new)
        return sarc.build(arc)
    if kind == "yaz0":
        old = yaz0.decompress(data, MAX_OUTPUT)
        new = replace_inner(old, rest, transform)
        return data if new == old else yaz0.compress(new, yaz0.header_alignment(data))
    if kind == "zstd":
        old = zstd.decompress(data, MAX_OUTPUT)
        new = replace_inner(old, rest, transform)
        return data if new == old else zstd.compress(new)
    raise ArchiveError(f"'{head}' yazılamadı: üstteki dosya bir arşiv değil.")
