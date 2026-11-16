"""`.fsd`/`.msg` biçimli oyunun menü başlığı resimlerini Türkçeleştirme: `status_e/st_init.dat` dokuları.

Durum (pause) menüsünün başlıkları metin değil, `st_init.dat` dosyasının
1–4. bölümlerindeki T32 dokularına çizilmiş resimlerdir (docs/formats/fsd-msg.md). Switch dokuları BC7 (DX10 DDS)
sayfalarıdır; her sayfa okunur, İngilizce sözcüğün bulunduğu pencere silinir ve Türkçe karşılığı aynı yükseklikte,
aynı taban çizgisinde, özgün renk ve parıltıyla çizilir. Dokular PC sürümünün (ve oyunun yazı dokusunun, cihazda
doğrulandı) kullandığı sıkıştırılmamış biçimde geri yazılır: 0xC0 baytlık T32 başlığı + sayfa başına DDS.

Oyun dokuları toplamsal karıştırmayla çizer: siyah görünmez, alfa her yerde 255'tir. Hangi dokuda hangi sözcüğün
nerede olduğu (doku kimliği → etiketler) uygulamayla gelmez; kullanıcının `resim_yazilari.json` dosyasının `menuler`
bölümünden okunur (`fsdmsg_userdata`). Pencereler her sayfada (normal ve seçili) aynıdır.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping

from PIL import Image

from nxceviri.core.fontpatch.fsdmsg import FontError
from nxceviri.core.fontpatch.labels import Label, draw_label, find_font

T32_HEADER = 0xC0
_DDS = 128
_DX10 = 148
#: BC7_UNORM (DXGI_FORMAT 98).
_BC7 = 98


def texture_id(t32: bytes) -> int:
    return struct.unpack_from("<I", t32, 0x14)[0] if len(t32) >= 0x18 and t32[1:4] == b"2MT" else 0


def read_pages(t32: bytes) -> list[Image.Image]:
    """T32 dokusunun sayfaları (BC7 veya sıkıştırılmamış BGRA DDS) RGBA resim olarak."""
    pages = []
    pos = struct.unpack_from("<I", t32, 8)[0]
    for _ in range(struct.unpack_from("<I", t32, 4)[0]):
        if t32[pos : pos + 4] != b"DDS ":
            raise FontError("Menü dokusunun yapısı beklenenden farklı.")
        height, width = struct.unpack_from("<II", t32, pos + 12)
        if t32[pos + 84 : pos + 88] == b"DX10":
            if struct.unpack_from("<I", t32, pos + _DDS)[0] != _BC7:
                raise FontError("Menü dokusu bilinmeyen bir sıkıştırma kullanıyor.")
            size = width * height
            pages.append(Image.frombytes("RGBA", (width, height), t32[pos + _DX10 : pos + _DX10 + size], "bcn", 7))
            pos += _DX10 + size
        else:
            size = width * height * 4
            pages.append(Image.frombytes("RGBA", (width, height), t32[pos + _DDS : pos + _DDS + size], "raw", "BGRA"))
            pos += _DDS + size
    return pages


def _dds_header(width: int, height: int) -> bytes:
    """Sıkıştırılmamış A8R8G8B8 DDS başlığı (PC sürümünün menü dokularıyla aynı alanlar)."""
    head = bytearray(_DDS)
    head[0:4] = b"DDS "
    struct.pack_into("<7I", head, 4, 124, 0x81007, height, width, width * height * 4, 0, 0)
    struct.pack_into("<I", head, 36, _DDS + width * height * 4)
    struct.pack_into("<8I", head, 76, 32, 0x41, 0, 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000)
    struct.pack_into("<I", head, 108, 0x1000)
    return bytes(head)


def write_t32(original: bytes, pages: list[Image.Image]) -> bytes:
    """Özgün başlığı koruyup sayfaları sıkıştırılmamış yazar (başlık boyu 0xC0, 0x3C = bir sayfanın boyu)."""
    head = bytearray(original[:T32_HEADER])
    struct.pack_into("<I", head, 8, T32_HEADER)
    struct.pack_into("<I", head, 0x3C, _DDS + pages[0].width * pages[0].height * 4)
    body = b"".join(_dds_header(p.width, p.height) + p.tobytes("raw", "BGRA") for p in pages)
    return bytes(head) + body


def translate_texture(t32: bytes, table: Mapping[int, tuple[Label, ...]]) -> bytes | None:
    """`table`daki (doku kimliği → sözcükler) bir menü dokusuysa Türkçe başlıklı hâlini döndürür; değilse None."""
    words = table.get(texture_id(t32))
    if words is None:
        return None
    fonts = {style: find_font(style) for style in {word.style for word in words}}
    pages = read_pages(t32)
    for i in range(len(pages)):
        for word in words:
            pages[i] = draw_label(pages[i], word, fonts[word.style])
    return write_t32(t32, pages)
