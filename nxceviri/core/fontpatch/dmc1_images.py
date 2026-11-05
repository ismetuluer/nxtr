"""Devil May Cry (Switch) oyun resimlerindeki İngilizce yazıları Türkçeleştirme (eşya, silah, düşman adları …).

Bu yazılar metin değil, dokulara çizilmiş resimlerdir ve `status/`, `etc/`, `pack_e/` … altındaki birçok farklı
kapsayıcıda (`.itm`, `.dat`, `.tm2`, `.t32`, `.pack`) durur. Kapsayıcıların yapısına dokunmamak için her dosyadaki DDS
sayfaları başlıklarından bulunur, çözülür, içerik özetiyle (`page_key`) tanınır ve değiştirilen sayfa **aynı biçimde,
aynı boyda ve yerinde** geri yazılır: BC7 sayfalarda yalnızca değişen 4×4 bloklar yeniden kodlanır, sıkıştırılmamış
(BGRA) sayfalar doğrudan yazılır. Böylece dosyanın boyu ve geri kalan her baytı aynı kalır.

Hangi sayfada hangi yazının nerede olduğu `dmc1_images_data.PAGES` tablosundadır (sayfa özeti → etiketler). Aynı resim
dosyalarda birçok kez geçebilir; özet aynı olduğu için hepsi değiştirilir. Oyunun başka bir sürümünde resim farklıysa
özet eşleşmez ve sayfaya dokunulmaz.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from nxceviri.core.fontpatch import bc1, bc7
from nxceviri.core.fontpatch.dmc1_images_data import FILES, PAGES
from nxceviri.core.fontpatch.labels import Label, draw_label, find_font

_DDS = 128
_DX10 = 148
_BC7 = 98

__all__ = ["FILES", "PAGES", "Page", "iter_pages", "page_key", "translate_file"]


@dataclass(frozen=True)
class Page:
    offset: int  # DDS başlığının dosyadaki konumu
    data_offset: int  # piksel verisinin başlangıcı
    width: int
    height: int
    format: str  # "bc7", "bc1" (DXT1) veya "bgra" (sıkıştırılmamış)
    image: Image.Image

    @property
    def compressed(self) -> bool:
        return self.format != "bgra"

    @property
    def size(self) -> int:
        return {"bc7": self.width * self.height, "bc1": self.width * self.height // 2}.get(
            self.format, self.width * self.height * 4
        )


def iter_pages(data: bytes) -> Iterator[Page]:
    """Dosyadaki çözülebilen DDS sayfaları (BC7, DXT1 veya 32 bit BGRA); başka biçimler ve bozuk başlıklar atlanır."""
    pos = data.find(b"DDS |")
    while pos >= 0:
        height, width = struct.unpack_from("<II", data, pos + 12)
        fourcc = data[pos + 84 : pos + 88]
        page: Page | None = None
        if 4 <= width <= 4096 and 4 <= height <= 4096 and width % 4 == 0 and height % 4 == 0:
            if fourcc == b"DX10" and struct.unpack_from("<I", data, pos + _DDS)[0] == _BC7:
                start, size = pos + _DX10, width * height
                if start + size <= len(data):
                    image = bc7.decode(data[start : start + size], width, height)
                    page = Page(pos, start, width, height, "bc7", image)
            elif fourcc == b"DXT1":
                start, size = pos + _DDS, width * height // 2
                if start + size <= len(data):
                    page = Page(pos, start, width, height, "bc1", bc1.decode(data[start : start + size], width, height))
            elif fourcc == b"\0\0\0\0" and struct.unpack_from("<I", data, pos + 88)[0] == 32:
                start, size = pos + _DDS, width * height * 4
                if start + size <= len(data):
                    image = Image.frombytes("RGBA", (width, height), data[start : start + size], "raw", "BGRA")
                    page = Page(pos, start, width, height, "bgra", image)
        if page is not None:
            yield page
        pos = data.find(b"DDS |", pos + 4)


def page_key(image: Image.Image) -> str:
    """Sayfanın içerik özeti (çözülmüş RGBA piksellerinin SHA-1'inin ilk 16 hanesi)."""
    return hashlib.sha1(image.tobytes()).hexdigest()[:16]


def _encode(page: Page, original: bytes, image: Image.Image) -> bytes:
    if page.format == "bc7":
        return bc7.reencode(original, page.image, image)
    if page.format == "bc1":
        return bc1.reencode(original, page.image, image)
    return image.tobytes("raw", "BGRA")


def translate_file(
    data: bytes,
    pages: dict[str, tuple[Label, ...]] | None = None,
    replacements: dict[str, Image.Image] | None = None,
) -> bytes:
    """Dosyadaki tanınan sayfaları Türkçeleştirir; dosyanın boyu ve yapısı değişmez.

    `replacements` (özgün sayfa özeti → hazır sayfa) varsa o sayfa olduğu gibi yazılır; yoksa etiketler çizilir."""
    table = PAGES if pages is None else pages
    ready = replacements or {}
    out = bytearray(data)
    fonts: dict[str, Path] = {}
    done: dict[bytes, bytes] = {}  # aynı sayfa dosyada defalarca geçer: özgün veri → yeni veri
    for page in iter_pages(data):
        key = page_key(page.image)
        new = ready.get(key)
        if new is not None and new.size != page.image.size:
            new = None
        labels = table.get(key)
        if new is None and not labels:
            continue
        original = data[page.data_offset : page.data_offset + page.size]
        digest = hashlib.sha1(original).digest()
        if digest not in done:
            image = new if new is not None else page.image
            for label in () if new is not None else labels or ():
                if label.style not in fonts:
                    fonts[label.style] = find_font(label.style)
                image = draw_label(image, label, fonts[label.style], reference=page.image)
            done[digest] = _encode(page, original, image)
        out[page.data_offset : page.data_offset + page.size] = done[digest]
    return bytes(out)
